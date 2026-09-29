"""Set the shipped frontier floor to 4.5 and measure it on the actual artifact.

Why: the shipped model uses frontier floor 5.0 and its measured frontier recall
is 72.5%, meaning 190 of 755 held-out hard tickets get a cheaper model than they
need. A floor of 4.5 moves borderline tickets up to the frontier model. Expected
gain is roughly 80%, from the 2-seed measurement, but that was a different
artifact, so this run measures the exact config being shipped.

The product decision behind the floor: the caller has accepted that some cheap
and mid traffic may be promoted to the expensive model, because a hard ticket
answered by a weak model is the failure that matters. This run confirms the
floor does what is expected, and reports what it costs in traffic and cheap
recall so the trade is visible rather than assumed.

Protocol, unchanged from threshold_recheck.py and regressor_upgrade.py:
each of 3 independent batch-level splits trains on 12,400 rows and scores once
on 2,600 held-out rows. Thresholds are fixed per candidate, not swept, so this
compares floors rather than fitting them. Mean and worst are both reported.

Outputs:
    models/support_final_3tier.joblib   (floor 4.5, refit on all 17,600)
    docs/floor_45.txt
    docs/floor_45.json
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
OUT_TXT = ROOT / "docs" / "floor_45.txt"
OUT_JSON = ROOT / "docs" / "floor_45.json"

SPLIT_SEEDS = (42, 7, 2024)
N_TRAIN_B, N_CALIB_B = 62, 13
CHEAP_CEIL = 2.0
FLOORS = (4.5, 5.0)
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


def tier(s: float, lo: float, hi: float) -> str:
    if s <= lo:
        return "cheap"
    if s >= hi:
        return "frontier"
    return "mid"


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


def score(y, p, hi: float) -> dict:
    gold = [tier(v, CHEAP_CEIL, hi) for v in y]
    pred = [tier(v, CHEAP_CEIL, hi) for v in np.clip(p, 0, 10)]
    out = {}
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
    for t in ("cheap", "mid", "frontier"):
        out[f"pred_{t}"] = float(np.mean([x == t for x in pred]))
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

    per = {hi: [] for hi in FLOORS}
    split_mae = []
    split_rho = []
    for sd in SPLIT_SEEDS:
        order = random.Random(sd).sample(batches, len(batches))
        tr_b = set(order[:N_TRAIN_B])
        te_b = set(order[N_TRAIN_B + N_CALIB_B :])
        tri = [i for i, r in enumerate(rows) if r["batch"] in tr_b]
        ti = [i for i, r in enumerate(rows) if r["batch"] in te_b]
        ms = train(X_all[tri], y_all[tri])
        p = predict(ms, X_all[ti])
        rec = {
            "seed": sd,
            "mae": float(np.mean(np.abs(y_all[ti] - p))),
            "spearman": spearman(y_all[ti], p),
        }
        split_mae.append(rec["mae"])
        split_rho.append(rec["spearman"])
        for hi in FLOORS:
            s = score(y_all[ti], p, hi)
            rec[f"floor_{hi}"] = s
            per[hi].append(s)
        print(
            f"  seed {sd:>5}  MAE {rec['mae']:.3f}  "
            f"front_rec 4.5 {rec['floor_4.5'].get('recall_frontier', float('nan')):.3f}"
            f"  5.0 {rec['floor_5.0'].get('recall_frontier', float('nan')):.3f}"
        )

    lines = [
        "=" * 118,
        "FRONTIER FLOOR 4.5 vs 5.0, measured on the shipped regressor",
        "=" * 118,
        f"regressor  3x LightGBM L1 1200 trees, seeds {SEEDS}, 391 features (MiniLM 384 + 4 + 3 domain)",
        f"labels     {n:,} rows, {len(batches)} batches",
        f"splits     {len(SPLIT_SEEDS)} independent, seeds {SPLIT_SEEDS}, {N_TRAIN_B}/{N_CALIB_B}/13 batches",
        f"cheap cut  fixed at {CHEAP_CEIL} so only the frontier floor varies",
        "",
        "MAE is identical across floors by construction: cut points change routing, not the",
        "regressor. What moves is which tickets reach the frontier model.",
        "",
        f"{'floor':<8}{'front_rec':>11}{'front_esc':>12}{'cheap_rec':>11}{'mid_rec':>10}"
        f"{'bal_acc':>10}{'traffic c/m/f':>20}{'MAE mean':>11}",
        "-" * 118,
    ]
    agg = {}
    for hi in FLOORS:
        s = per[hi]
        m = lambda g: float(np.mean([x.get(g, np.nan) for x in s]))
        tr = f"{100 * m('pred_cheap'):.0f}/{100 * m('pred_mid'):.0f}/{100 * m('pred_frontier'):.0f}"
        agg[hi] = {
            "recall_frontier": m("recall_frontier"),
            "frontier_escape_rate": m("frontier_escape_rate"),
            "under": int(np.mean([x["under"] for x in s])),
            "n_frontier_gold": int(np.mean([x["n_frontier_gold"] for x in s])),
            "recall_cheap": m("recall_cheap"),
            "recall_mid": m("recall_mid"),
            "balanced_acc": m("balanced_acc"),
            "traffic": {
                "cheap": m("pred_cheap"),
                "mid": m("pred_mid"),
                "frontier": m("pred_frontier"),
            },
        }
        mae = float(np.mean(split_mae))
        lines.append(
            f"{hi:<8.1f}{m('recall_frontier'):>11.3f}"
            f"{str(agg[hi]['under']) + '/' + str(agg[hi]['n_frontier_gold']):>12}"
            f"{m('recall_cheap'):>11.3f}{m('recall_mid'):>10.3f}{m('balanced_acc'):>10.3f}"
            f"{tr:>20}{mae:>11.3f}"
        )

    d_fr = agg[4.5]["recall_frontier"] - agg[5.0]["recall_frontier"]
    d_esc = agg[4.5]["frontier_escape_rate"] - agg[5.0]["frontier_escape_rate"]
    d_tr = agg[4.5]["traffic"]["frontier"] - agg[5.0]["traffic"]["frontier"]
    lines += [
        "",
        "--- what moving the floor 5.0 -> 4.5 buys and costs ---",
        f"  frontier recall   {agg[5.0]['recall_frontier']:.3f} -> {agg[4.5]['recall_frontier']:.3f}  ({d_fr:+.3f})",
        f"  frontier escape   {agg[5.0]['frontier_escape_rate']:.1%} -> {agg[4.5]['frontier_escape_rate']:.1%}  ({d_esc:+.1%})",
        f"  cheap recall      {agg[5.0]['recall_cheap']:.3f} -> {agg[4.5]['recall_cheap']:.3f}"
        f"  ({agg[4.5]['recall_cheap'] - agg[5.0]['recall_cheap']:+.3f})",
        f"  frontier traffic  {100 * agg[5.0]['traffic']['frontier']:.1f}% -> {100 * agg[4.5]['traffic']['frontier']:.1f}%"
        f"  ({100 * d_tr:+.1f} pts)",
        "",
        "  The escape rate is the number that matters operationally: it is the share of",
        "  genuinely hard tickets that get answered by a cheaper model than intended.",
    ]

    # ship floor 4.5, refit on all rows
    print(f"\nrefitting on all {n:,} rows with floor 4.5")
    ms = train(X_all, y_all)
    p_fit = predict(ms, X_all)
    fit = score(y_all, p_fit, 4.5)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / "support_final_3tier.joblib"
    joblib.dump(
        {
            "models": ms,
            "seeds": list(SEEDS),
            "params": {k: v for k, v in BASE.items() if k != "verbose"},
            "feature_count": int(X_all.shape[1]),
            "feature_order": "minilm384_then_handcrafted4_then_domain4",
            "domain_order": list(DOMAINS),
            "embedder": str(EMBED_DIR),
            "thr": {"cheap_ceil": CHEAP_CEIL, "frontier_floor": 4.5},
            "n_tiers": 3,
            "tier_rule": "tier3_two_cuts",
            "n_train_rows": n,
            "source": "customer_support",
            "honest_eval": {
                "protocol": f"mean of {len(SPLIT_SEEDS)} independent batch-level splits, "
                f"{N_TRAIN_B}/{N_CALIB_B}/13 of {len(batches)} batches, cheap cut fixed at {CHEAP_CEIL}",
                "mae_mean": float(np.mean(split_mae)),
                "mae_worst": float(max(split_mae)),
                "spearman_mean": float(np.mean(split_rho)),
                "recall_cheap": agg[4.5]["recall_cheap"],
                "recall_mid": agg[4.5]["recall_mid"],
                "recall_frontier": agg[4.5]["recall_frontier"],
                "frontier_escape_rate": agg[4.5]["frontier_escape_rate"],
                "traffic": agg[4.5]["traffic"],
                "per_split": [
                    {
                        "seed": SPLIT_SEEDS[i],
                        "mae": split_mae[i],
                        "spearman": split_rho[i],
                        "recall_frontier": per[4.5][i].get("recall_frontier"),
                        "under": per[4.5][i]["under"],
                    }
                    for i in range(len(SPLIT_SEEDS))
                ],
            },
            "slider_note": (
                "thr is the safe default. The backend route handler already accepts a "
                "per-request threshold override. Label mass thins above score 8 (18 rows at 9, "
                "0 at 10), so a slider driving the floor past 8 routes on unevidenced "
                "extrapolation and should be capped there."
            ),
        },
        path,
    )
    lines += [
        "",
        "--- shipped model: floor 4.5, all 17,600 rows ---",
        f"  file {path.name}",
        f"  thresholds cheap <= {CHEAP_CEIL}, frontier >= 4.5",
        f"  fit check MAE {float(np.mean(np.abs(y_all - p_fit))):.3f} (memorization, not quality)",
        f"  fit balanced {fit['balanced_acc']:.3f}",
        "",
        "--- honest metrics for the shipped model (mean of 3 splits) ---",
        f"  MAE                    {float(np.mean(split_mae)):.3f}",
        f"  MAE worst              {float(max(split_mae)):.3f}",
        f"  Spearman               {float(np.mean(split_rho)):.3f}",
        f"  cheap recall           {agg[4.5]['recall_cheap']:.3f}",
        f"  mid recall             {agg[4.5]['recall_mid']:.3f}",
        f"  frontier recall        {agg[4.5]['recall_frontier']:.3f}",
        f"  frontier escape rate   {agg[4.5]['frontier_escape_rate']:.1%}",
        f"  traffic                {100 * agg[4.5]['traffic']['cheap']:.0f}% cheap /"
        f" {100 * agg[4.5]['traffic']['mid']:.0f}% mid / {100 * agg[4.5]['traffic']['frontier']:.0f}% frontier",
        "",
        "--- slider guidance, if exposed later ---",
        "  The backend route handler already accepts a per-request threshold override, so a",
        "  slider needs no new plumbing. Three constraints come out of the label data:",
        "    1. the cheap cut matters more than the floor for most users, so expose both",
        "    2. default to the safe end, not the cheap end, so nobody gets weak answers by default",
        "    3. label mass thins above score 8 (18 rows at 9, none at 10); cap the floor at 8",
        "       or the slider routes on extrapolation rather than evidence",
        "",
        "--- caveats ---",
        "  Quote the mean and worst split, never a single split.",
        "  MAE is unaffected by the floor; only routing changes.",
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
                "cheap_ceil": CHEAP_CEIL,
                "regressor": {k: v for k, v in BASE.items() if k != "verbose"},
                "seeds": list(SEEDS),
                "by_floor": {str(k): v for k, v in agg.items()},
                "shipped_floor": 4.5,
                "fit_check": {"mae": float(np.mean(np.abs(y_all - p_fit)))},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print()
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
