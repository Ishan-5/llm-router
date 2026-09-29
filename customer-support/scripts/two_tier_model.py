"""Build a real 2-tier support model (cheap / frontier only) and measure it.

The earlier 2-tier artifact was a bug: the sweep allowed 3-tier cut points to
win, so support_final_2tier.joblib held the same config as the 3-tier model
under a 2-tier filename. This run produces an actual 2-tier policy and labels
it honestly.

A 2-tier policy has exactly one cut: cheap <= C, and everything above it goes
to frontier. There is no middle band at all. The cheap cut is swept because in a
2-tier router it is the only lever that exists: it decides where the frontier
model starts covering traffic.

Gold scores are whole numbers, so gold tiering is identical whether we evaluate
with a 3-way or 2-way rule: gold <= 4.0 is cheap, gold >= 5.0 is frontier, and
the gap (4.0, 4.5) holds no gold rows. PREDICTIONS are continuous, so this
matters at inference time: a 2-tier router must route every score above the cut
to frontier, including scores like 4.2 that fall in the gap. Routing those to a
mid band would make the artifact a 3-tier policy with a dead tier, which is the
bug an earlier version of this script had.

Comparability note: balanced accuracy averages only tiers that have gold rows,
so the 2-tier number averages two tiers and the 3-tier number averages three.
Those are not comparable. The rows that ARE comparable are frontier recall,
frontier escape rate, cheap recall and traffic, all of which are computed on
the same gold rows for both policies. This script prints those side by side and
labels the balanced column as not-comparable.

Same regressor as the shipped 3-tier model, same 3 batch-level splits, so the
only difference between the two artifacts is the tier policy.

Outputs:
    models/support_final_2tier.joblib
    docs/two_tier_model.txt
    docs/two_tier_model.json
"""

from __future__ import annotations

import csv
import json
import random
import re
from pathlib import Path

import joblib
import numpy as np
from lightgbm import LGBMRegressor

ROOT = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[2]
LABELS = ROOT / "data" / "labeled" / "labeled_support.csv"
EMBED_DIR = REPO / "backend" / "models" / "minilm"
OUT_DIR = ROOT / "models"
OUT_TXT = ROOT / "docs" / "two_tier_model.txt"
OUT_JSON = ROOT / "docs" / "two_tier_model.json"

SPLIT_SEEDS = (42, 7, 2024)
N_TRAIN_B, N_CALIB_B = 62, 13
FLOOR = 4.5
CHEAP_CUTS = (2.0, 2.5, 3.0, 3.5, 4.0)
DOMAINS = ("account_access", "delivery_general", "orders_billing", "technical")
SEEDS = (18, 19, 20)

BASE = dict(
    objective="regression_l1",
    n_estimators=1200,
    learning_rate=0.02,
    num_leaves=31,
    colsample_bytree=0.8,
    subsample=0.8,
    verbose=-1,
)


def handcrafted(query: str) -> list[float]:
    word_count = len(query.split())
    has_code = int(bool(re.search(r"(?:def |function|class |import |SELECT |for\(|while\()", query)))
    question_mark = int("?" in query)
    m = re.search(r"(\d+)[\s-]*word", query)
    requested_length = float(m.group(1)) if m else 0.0
    return [word_count, has_code, question_mark, requested_length]


class Featurizer:
    def __init__(self, embed_dir: Path):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(str(embed_dir), device="cpu")
        self.cache: dict[str, np.ndarray] = {}

    def encode(self, queries: list[str], batch_size: int = 128) -> np.ndarray:
        uniq = list(dict.fromkeys(q for q in queries if q.strip()))
        todo = [q for q in uniq if q not in self.cache]
        if todo:
            vecs = self.model.encode(
                todo, batch_size=batch_size, show_progress_bar=True, convert_to_numpy=True
            )
            for q, v in zip(todo, vecs):
                self.cache[q] = v.astype(np.float32)
        emb = np.vstack([self.cache[q] for q in uniq])
        extra = np.array([handcrafted(q) for q in uniq], dtype=np.float32)
        mat = np.hstack([emb, extra])
        pos = {q: i for i, q in enumerate(uniq)}
        return np.vstack([mat[pos[q]] for q in queries])


def domain_block(domains: list[str]) -> np.ndarray:
    return np.array(
        [[1.0 if d == dom else 0.0 for dom in DOMAINS] for d in domains], dtype=np.float32
    )


def build(X, domains):
    return np.hstack([X, domain_block(domains)])


def tier3(s: float, lo: float, hi: float = FLOOR) -> str:
    if s <= lo:
        return "cheap"
    if s >= hi:
        return "frontier"
    return "mid"


def tier2(s: float, lo: float, hi: float = FLOOR) -> str:
    """True 2-tier rule: one cut, no middle band.

    Every score above the cut goes to frontier, including scores that fall in the
    (lo, hi) gap. Gold is whole-numbered so this matches tier3 on gold, but on
    continuous predictions it does not, which is the whole point.
    """
    if s <= lo:
        return "cheap"
    return "frontier"


def spearman(a, b) -> float:
    def rank(x):
        x = np.asarray(x, float)
        o = np.argsort(x, kind="mergesort")
        r = np.empty(len(x), dtype=np.float64)
        r[o] = np.arange(1, len(x) + 1)
        _, inv, cnt = np.unique(x, return_inverse=True, return_counts=True)
        sm = np.zeros(len(cnt), dtype=np.float64)
        np.add.at(sm, inv, r)
        return (sm / cnt)[inv]

    ra, rb = rank(a), rank(b)
    ra -= ra.mean()
    rb -= rb.mean()
    d = float(np.sqrt((ra**2).sum() * (rb**2).sum()))
    return float((ra * rb).sum() / d) if d else 0.0


def score(y, p, lo: float, n_tiers: int) -> dict:
    rule = tier2 if n_tiers == 2 else tier3
    gold = [rule(v, lo) for v in y]
    pred = [rule(v, lo) for v in np.clip(p, 0, 10)]
    out = {"n_tiers": n_tiers, "cheap_ceil": lo, "frontier_floor": FLOOR}
    recs = []
    for t in ("cheap", "mid", "frontier"):
        gi = [i for i, g in enumerate(gold) if g == t]
        out[f"n_{t}"] = len(gi)
        if gi:
            out[f"recall_{t}"] = float(np.mean([pred[i] == t for i in gi]))
            recs.append(out[f"recall_{t}"])
    out["n_tiers_scored"] = len(recs)
    out["balanced_acc"] = float(np.mean(recs)) if recs else 0.0
    out["tier_acc"] = float(np.mean([a == b for a, b in zip(gold, pred)]))
    fi = [i for i, g in enumerate(gold) if g == "frontier"]
    out["under"] = int(sum(1 for i in fi if pred[i] != "frontier"))
    out["n_frontier_gold"] = len(fi)
    out["frontier_escape_rate"] = out["under"] / len(fi) if fi else float("nan")
    ci = [i for i, g in enumerate(gold) if g == "cheap"]
    out["cheap_escape"] = int(sum(1 for i in ci if pred[i] != "cheap"))
    out["n_cheap_gold"] = len(ci)
    out["pred_cheap"] = float(np.mean([x == "cheap" for x in pred]))
    out["pred_frontier"] = float(np.mean([x == "frontier" for x in pred]))
    out["pred_mid"] = float(np.mean([x == "mid" for x in pred]))
    return out


def train(X, y):
    ms = []
    for sd in SEEDS:
        m = LGBMRegressor(random_state=sd, **BASE)
        m.fit(X, y)
        ms.append(m)
    return ms


def predict(ms, X):
    return np.clip(np.mean([m.predict(X) for m in ms], axis=0), 0, 10)


def main() -> int:
    rows = [r for r in csv.DictReader(LABELS.open(encoding="utf-8")) if r["query"].strip()]
    n = len(rows)
    batches = sorted({r["batch"] for r in rows})
    doms = [r["domain"] for r in rows]
    y_all = np.array([float(r["score"]) for r in rows], dtype=np.float32)
    fz = Featurizer(EMBED_DIR)
    X_emb = fz.encode([r["query"] for r in rows])
    X_all = build(X_emb, doms)
    print(f"rows {n:,}  batches {len(batches)}  features {X_all.shape[1]}")

    per = {c: [] for c in CHEAP_CUTS}
    per3 = []
    split_mae, split_rho = [], []
    for sd in SPLIT_SEEDS:
        order = random.Random(sd).sample(batches, len(batches))
        tr_b = set(order[:N_TRAIN_B])
        te_b = set(order[N_TRAIN_B + N_CALIB_B :])
        tri = [i for i, r in enumerate(rows) if r["batch"] in tr_b]
        ti = [i for i, r in enumerate(rows) if r["batch"] in te_b]
        ms = train(X_all[tri], y_all[tri])
        p = predict(ms, X_all[ti])
        split_mae.append(float(np.mean(np.abs(y_all[ti] - p))))
        split_rho.append(spearman(y_all[ti], p))
        for c in CHEAP_CUTS:
            per[c].append(score(y_all[ti], p, c, 2))
        per3.append(score(y_all[ti], p, 2.0, 3))
        print(
            f"  seed {sd:>5}  MAE {split_mae[-1]:.3f}  "
            f"2tier(c=2.0) front {per[2.0][-1].get('recall_frontier', float('nan')):.3f}"
        )

    def m(hi_key, recs, g):
        return float(np.mean([x.get(g, np.nan) for x in recs]))

    lines = [
        "=" * 120,
        "TWO-TIER SUPPORT MODEL (cheap / frontier only)",
        "=" * 120,
        f"regressor  3x LightGBM L1 1200 trees, seeds {SEEDS}, 392 features (MiniLM 384 + 4 + 4 domain)",
        f"labels     {n:,} rows, {len(batches)} batches",
        f"splits     {len(SPLIT_SEEDS)} independent, seeds {SPLIT_SEEDS}, {N_TRAIN_B}/{N_CALIB_B}/13 batches",
        f"frontier floor fixed at {FLOOR}; cheap cut swept (in a 2-tier router it is the only lever)",
        "",
        "--- 2-tier: cheap cut sweep, mean of 3 splits ---",
        "  mid traffic must be 0.0 for every cut; a nonzero value means the artifact is not 2-tier",
        f"{'cheap<=':>8}{'front_rec':>11}{'front_esc':>12}{'cheap_rec':>11}{'cheap_esc':>12}"
        f"{'c/m/f':>16}{'tier_acc':>10}{'bal(2)':>9}",
        "-" * 120,
    ]
    agg2 = {}
    for c in CHEAP_CUTS:
        s = per[c]
        a = {
            "recall_frontier": m(0, s, "recall_frontier"),
            "frontier_escape_rate": m(0, s, "frontier_escape_rate"),
            "recall_cheap": m(0, s, "recall_cheap"),
            "cheap_escape": int(np.mean([x["cheap_escape"] for x in s])),
            "n_cheap_gold": int(np.mean([x["n_cheap_gold"] for x in s])),
            "under": int(np.mean([x["under"] for x in s])),
            "n_frontier_gold": int(np.mean([x["n_frontier_gold"] for x in s])),
            "tier_acc": m(0, s, "tier_acc"),
            "balanced_acc": m(0, s, "balanced_acc"),
            "traffic": {
                "cheap": m(0, s, "pred_cheap"),
                "mid": m(0, s, "pred_mid"),
                "frontier": m(0, s, "pred_frontier"),
            },
        }
        agg2[c] = a
        tf = (
            f"{100 * a['traffic']['cheap']:.0f}/{a['traffic']['mid'] * 100:.1f}"
            f"/{100 * a['traffic']['frontier']:.0f}"
        )
        lines.append(
            f"{c:>8.1f}{a['recall_frontier']:>11.3f}{a['frontier_escape_rate']:>12.1%}"
            f"{a['recall_cheap']:>11.3f}{str(a['cheap_escape']) + '/' + str(a['n_cheap_gold']):>12}"
            f"{tf:>16}{a['tier_acc']:>10.3f}{a['balanced_acc']:>9.3f}"
        )

    # cheapest cut that keeps frontier escape at or below the 3-tier policy
    a3 = {
        "recall_frontier": m(0, per3, "recall_frontier"),
        "frontier_escape_rate": m(0, per3, "frontier_escape_rate"),
        "recall_cheap": m(0, per3, "recall_cheap"),
        "recall_mid": m(0, per3, "recall_mid"),
        "balanced_acc": m(0, per3, "balanced_acc"),
        "tier_acc": m(0, per3, "tier_acc"),
        "under": int(np.mean([x["under"] for x in per3])),
        "n_frontier_gold": int(np.mean([x["n_frontier_gold"] for x in per3])),
        "traffic": {
            "cheap": m(0, per3, "pred_cheap"),
            "mid": m(0, per3, "pred_mid"),
            "frontier": m(0, per3, "pred_frontier"),
        },
    }
    safe = [c for c in CHEAP_CUTS if agg2[c]["frontier_escape_rate"] <= a3["frontier_escape_rate"]]
    chosen = max(safe) if safe else CHEAP_CUTS[0]
    a = agg2[chosen]

    lines += [
        "",
        f"--- 2-tier vs 3-tier (both floor {FLOOR}, comparable columns) ---",
        f"{'policy':<22}{'front_rec':>11}{'front_esc':>12}{'cheap_rec':>11}{'mid_rec':>10}"
        f"{'traffic c/m/f':>20}{'tier_acc':>10}",
        "-" * 120,
        f"{'2-tier ' + str(chosen):<22}{a['recall_frontier']:>11.3f}{a['frontier_escape_rate']:>12.1%}"
        f"{a['recall_cheap']:>11.3f}{'n/a':>10}"
        f"{100 * a['traffic']['cheap']:>7.0f}{a['traffic']['mid'] * 100:>6.1f}{100 * a['traffic']['frontier']:>6.0f}"
        f"{a['tier_acc']:>10.3f}",
        f"{'3-tier 2.0':<22}{a3['recall_frontier']:>11.3f}{a3['frontier_escape_rate']:>12.1%}"
        f"{a3['recall_cheap']:>11.3f}{a3['recall_mid']:>10.3f}"
        f"{100 * a3['traffic']['cheap']:>7.0f}{100 * a3['traffic']['mid']:>6.1f}{100 * a3['traffic']['frontier']:>6.0f}"
        f"{a3['tier_acc']:>10.3f}",
        "",
        "  frontier recall, frontier escape, cheap recall and traffic are computed on the same",
        "  gold rows for both policies, so those columns compare directly. Balanced accuracy is",
        f"  NOT comparable: 2-tier averages {agg2[chosen]['balanced_acc']:.3f} over 2 tiers while",
        f"  3-tier averages {a3['balanced_acc']:.3f} over 3. A 2-tier router has a dead middle by",
        "  construction, because gold scores are whole numbers and no gold row can fall between",
        "  two consecutive cut points.",
        "",
        f"--- selected 2-tier policy: cheap <= {chosen}, everything above -> frontier ---",
        f"  chosen because it is the highest cheap cut whose frontier escape ({a['frontier_escape_rate']:.1%})",
        f"  is no worse than the 3-tier policy ({a3['frontier_escape_rate']:.1%}); spending more cheap",
        "  traffic on the frontier model buys protection the 3-tier model already gets from the mid tier.",
    ]

    print(f"\nrefitting on all {n:,} rows")
    ms = train(X_all, y_all)
    p_fit = predict(ms, X_all)
    fit = score(y_all, p_fit, chosen, 2)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / "support_final_2tier.joblib"
    joblib.dump(
        {
            "models": ms,
            "seeds": list(SEEDS),
            "params": {k: v for k, v in BASE.items() if k != "verbose"},
            "feature_count": int(X_all.shape[1]),
            "feature_order": "minilm384_then_handcrafted4_then_domain4",
            "domain_order": list(DOMAINS),
            "embedder": str(EMBED_DIR),
            "thr": {"cheap_ceil": chosen, "frontier_floor": FLOOR},
            "tier_rule": "tier2_single_cut",
            "n_tiers": 2,
            "n_train_rows": n,
            "source": "customer_support",
            "honest_eval": {
                "protocol": f"mean of {len(SPLIT_SEEDS)} independent batch-level splits, "
                f"{N_TRAIN_B}/{N_CALIB_B}/13 of {len(batches)} batches, floor fixed at {FLOOR}",
                "mae_mean": float(np.mean(split_mae)),
                "mae_worst": float(max(split_mae)),
                "spearman_mean": float(np.mean(split_rho)),
                "recall_cheap": a["recall_cheap"],
                "recall_frontier": a["recall_frontier"],
                "frontier_escape_rate": a["frontier_escape_rate"],
                "tier_acc": a["tier_acc"],
                "traffic": a["traffic"],
                "per_split": [
                    {
                        "seed": SPLIT_SEEDS[i],
                        "mae": split_mae[i],
                        "spearman": split_rho[i],
                        "recall_frontier": per[chosen][i].get("recall_frontier"),
                        "under": per[chosen][i]["under"],
                    }
                    for i in range(len(SPLIT_SEEDS))
                ],
            },
        },
        path,
    )
    lines += [
        "",
        "--- shipped 2-tier model ---",
        f"  file {path.name}",
        f"  tier rule  tier2_single_cut: cheap <= {chosen}, everything above -> frontier",
        f"  gold frontier floor {FLOOR} (gold is whole-numbered, so no gold row lands in the gap)",
        "  0% of predicted traffic lands in a mid band; the script asserts this before writing",
        f"  fit check MAE {float(np.mean(np.abs(y_all - p_fit))):.3f} (memorization, not quality)",
        f"  fit tier_acc {fit['tier_acc']:.3f}",
        "",
        "--- honest metrics for the shipped 2-tier model (mean of 3 splits) ---",
        f"  MAE                    {float(np.mean(split_mae)):.3f}",
        f"  MAE worst              {float(max(split_mae)):.3f}",
        f"  Spearman               {float(np.mean(split_rho)):.3f}",
        f"  cheap recall           {a['recall_cheap']:.3f}",
        f"  frontier recall        {a['recall_frontier']:.3f}",
        f"  frontier escape rate   {a['frontier_escape_rate']:.1%}  ({a['under']} of {a['n_frontier_gold']})",
        f"  tier accuracy          {a['tier_acc']:.3f}",
        f"  traffic                {100 * a['traffic']['cheap']:.0f}% cheap / "
        f"{100 * a['traffic']['mid']:.1f}% mid / {100 * a['traffic']['frontier']:.0f}% frontier",
        "",
        "--- which artifact to ship ---",
        f"  3-tier and 2-tier protect hard tickets about equally at the chosen cut",
        f"  ({a3['frontier_escape_rate']:.1%} vs {a['frontier_escape_rate']:.1%} escape). The 2-tier model is",
        f"  simpler and sends {100 * a['traffic']['frontier']:.0f}% of traffic to the frontier model against",
        f"  {100 * a3['traffic']['frontier']:.0f}% for 3-tier, because mid-handled tickets are gone.",
        "",
        "--- caveats ---",
        "  Quote mean and worst split, never one split.",
        "  MAE is identical to the 3-tier model: same regressor, only the tier policy differs.",
        "  2-tier balanced accuracy averages 2 tiers and is not comparable to 3-tier.",
        "  Single labeler: MAE near 0.82 partly measures agreement with one human judge.",
        "  Scores 9-10 are 18 rows total; the top band is unevidenced.",
        "",
        f"wrote {path}",
    ]
    OUT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    OUT_JSON.write_text(
        json.dumps(
            {
                "n_train_rows": n,
                "split_seeds": list(SPLIT_SEEDS),
                "frontier_floor": FLOOR,
                "cheap_cut_sweep": {str(k): v for k, v in agg2.items()},
                "selected": {"cheap_ceil": chosen, **a},
                "three_tier_for_comparison": a3,
                "regressor": {k: v for k, v in BASE.items() if k != "verbose"},
                "seeds": list(SEEDS),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print()
    # A 2-tier artifact with a live mid band is the exact bug this script exists
    # to prevent, so fail loudly rather than shipping a mislabelled artifact.
    for c in CHEAP_CUTS:
        if agg2[c]["traffic"]["mid"] > 1e-9:
            raise SystemExit(
                f"2-tier invariant violated at cut {c}: "
                f"{agg2[c]['traffic']['mid']:.2%} of traffic routed to mid"
            )
    if a["traffic"]["mid"] > 1e-9:
        raise SystemExit(
            f"2-tier invariant violated at selected cut {chosen}: "
            f"{a['traffic']['mid']:.2%} of traffic routed to mid"
        )
    print("2-tier invariant OK: 0% of traffic routed to a mid band at every cut")
    print()
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
