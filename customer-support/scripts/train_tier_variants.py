"""Train the 3-tier and 2-tier support models and report honest metrics.

Two threshold policies, both requested:

    3-tier   cheap <= 2.0 | mid 2.0-4.5 | frontier >= 4.5
    2-tier   cheap <= 4.0 | mid 4.0-4.5 | frontier >= 4.5

The 3-tier floor moves 5.0 -> 4.5 because a hard ticket being downgraded to a
cheaper model is the one routing error that matters; the cost of a wider
frontier band lands on mid and cheap, which is the acceptable direction.

Why the metrics are not taken from the shipped model's own predictions: the
shipped model is refit on all 17,600 rows, so scoring it on those rows
measures memorization. The fit numbers are printed too, but only to show the
gap. The generalization figures come from a batch-level 62/13/13 split
(thresholds fixed, not re-searched, scored once on test), which is the same
protocol as train_final_model.py so the numbers are comparable.

Split is by batch, not by row: exact-normalized dedup leaves near-duplicate
tickets, so a row-level split leaks siblings and inflates scores.

Outputs:
    models/support_final_3tier.joblib
    models/support_final_2tier.joblib
    docs/tier_comparison.txt
    docs/tier_comparison.json
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
OUT_TXT = ROOT / "docs" / "tier_comparison.txt"
OUT_JSON = ROOT / "docs" / "tier_comparison.json"

SEED = 42
N_TRAIN_B, N_CALIB_B = 62, 13
SEEDS = (18, 19)

POLICIES = {
    "3tier_2.0_4.5": {"lo": 2.0, "hi": 4.5, "n_tiers": 3},
    "2tier_4.0_4.5": {"lo": 4.0, "hi": 4.5, "n_tiers": 2},
}

PARAMS = dict(
    objective="regression_l1",
    n_estimators=1200,
    learning_rate=0.02,
    num_leaves=31,
    colsample_bytree=0.8,
    subsample=0.8,
    verbose=-1,
)


def handcrafted(query: str) -> list[float]:
    """Must stay byte-identical to predict_difficulty.py's inline version."""
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


def score(y, p, pol) -> dict:
    lo, hi = pol["lo"], pol["hi"]
    gold = [tier(v, lo, hi) for v in y]
    pred = [tier(v, lo, hi) for v in np.clip(p, 0, 10)]
    out = {"n_tiers": pol["n_tiers"]}
    recs = []
    for t in ("cheap", "mid", "frontier"):
        gi = [i for i, g in enumerate(gold) if g == t]
        out[f"n_{t}"] = len(gi)
        if gi:
            out[f"recall_{t}"] = float(np.mean([pred[i] == t for i in gi]))
            recs.append(out[f"recall_{t}"])
    # balanced accuracy averages only tiers that actually have gold rows; a
    # tier with zero gold rows must not be counted as 0 or as 1, either way the
    # number stops being comparable across policies.
    out["n_tiers_scored"] = len(recs)
    out["balanced_acc"] = float(np.mean(recs)) if recs else 0.0
    out["tier_acc"] = float(np.mean([a == b for a, b in zip(gold, pred)]))
    for t, key in (("cheap", "pred_cheap"), ("mid", "pred_mid"), ("frontier", "pred_frontier")):
        out[key] = float(np.mean([x == t for x in pred]))
    fi = [i for i, g in enumerate(gold) if g == "frontier"]
    out["under"] = int(sum(1 for i in fi if pred[i] != "frontier"))
    out["n_frontier_gold"] = len(fi)
    out["frontier_escape_rate"] = out["under"] / len(fi) if fi else float("nan")
    ci = [i for i, g in enumerate(gold) if g == "cheap"]
    out["cheap_escape"] = int(sum(1 for i in ci if pred[i] != "cheap"))
    out["n_cheap_gold"] = len(ci)
    return out


def train(X, y):
    ms = []
    for sd in SEEDS:
        m = LGBMRegressor(random_state=sd, **PARAMS)
        m.fit(X, y)
        ms.append(m)
    return ms


def predict(ms, X):
    return np.clip(np.mean([m.predict(X) for m in ms], axis=0), 0, 10)


def fmt(label: str, s: dict) -> str:
    r = lambda k: f"{s.get(k, float('nan')):.3f}"
    return (
        f"{label:<22}{s['balanced_acc']:>9.3f}  ({s['n_tiers_scored']} tiers)"
        f"{r('recall_cheap'):>8}{r('recall_mid'):>8}{r('recall_frontier'):>9}"
        f"{str(s['under']) + '/' + str(s['n_frontier_gold']):>11}"
        f"{s['tier_acc']:>9.3f}"
        f"{100 * s['pred_cheap']:>7.1f}{100 * s['pred_mid']:>7.1f}{100 * s['pred_frontier']:>7.1f}"
    )


def main() -> int:
    rows = [r for r in csv.DictReader(LABELS.open(encoding="utf-8")) if r["query"].strip()]
    n = len(rows)
    batches = sorted({r["batch"] for r in rows})
    order = random.Random(SEED).sample(batches, len(batches))
    tr_b, ca_b = set(order[:N_TRAIN_B]), set(order[N_TRAIN_B : N_TRAIN_B + N_CALIB_B])
    te_b = set(order[N_TRAIN_B + N_CALIB_B :])
    tr = [r for r in rows if r["batch"] in tr_b]
    ca = [r for r in rows if r["batch"] in ca_b]
    te = [r for r in rows if r["batch"] in te_b]

    print(f"eval split (batch-level, seed {SEED}):  train {len(tr):,}  calib {len(ca):,}  test {len(te):,}")
    fz = Featurizer(EMBED_DIR)
    ms = train(
        fz.encode([r["query"] for r in tr]),
        np.array([float(r["score"]) for r in tr], dtype=np.float32),
    )
    y_te = np.array([float(r["score"]) for r in te], dtype=np.float32)
    p_te = predict(ms, fz.encode([r["query"] for r in te]))
    mae = float(np.mean(np.abs(y_te - p_te)))
    rho = spearman(y_te, p_te)
    print(f"held-out MAE {mae:.3f}  Spearman {rho:.3f}  (same for both policies)\n")

    te_res = {k: score(y_te, p_te, v) for k, v in POLICIES.items()}

    # refit on everything, as requested, for the shippable artifacts
    print(f"refitting on all {n:,} rows")
    X_all = fz.encode([r["query"] for r in rows])
    y_all = np.array([float(r["score"]) for r in rows], dtype=np.float32)
    final = train(X_all, y_all)
    p_fit = predict(final, X_all)
    fit_res = {k: score(y_all, p_fit, v) for k, v in POLICIES.items()}

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    for key, pol in POLICIES.items():
        path = OUT_DIR / f"support_final_{key.split('_')[0]}.joblib"
        joblib.dump(
            {
                "models": final,
                "seeds": list(SEEDS),
                "params": {k: v for k, v in PARAMS.items() if k != "verbose"},
                "feature_count": int(X_all.shape[1]),
                "feature_order": "minilm384_then_handcrafted4",
                "embedder": str(EMBED_DIR),
                "thr": {"cheap_ceil": pol["lo"], "frontier_floor": pol["hi"]},
                "n_tiers": pol["n_tiers"],
                "n_train_rows": n,
                "source": "customer_support",
                "honest_eval": {
                    "protocol": "batch-level 62/13/13 of 88 batches, thresholds fixed, test scored once",
                    "test_rows": len(te),
                    "mae": mae,
                    "spearman": rho,
                    **{k: v for k, v in te_res[key].items()},
                },
            },
            path,
        )
        written.append(path)
        print(f"  wrote {path.name}")

    lines = [
        "=" * 108,
        "SUPPORT MODEL: 3-TIER vs 2-TIER, same regressor, same data",
        "=" * 108,
        f"regressor   2 LightGBM, regression_l1, 1200 trees @ lr 0.02, seeds {SEEDS[0]}/{SEEDS[1]}",
        f"features    388 = MiniLM-L6-v2 384 + 4 handcrafted",
        f"labels      {n:,} rows from 88 of 238 batches",
        "",
        "3-tier policy   cheap <= 2.0  |  mid 2.0-4.5  |  frontier >= 4.5",
        "2-tier policy   cheap <= 4.0  |  mid 4.0-4.5  |  frontier >= 4.5",
        "",
        "--- GENERALIZATION: batch-level holdout, thresholds fixed, test scored once ---",
        f"    test rows {len(te):,}   MAE {mae:.3f}   Spearman {rho:.3f}",
        "",
        f"{'policy':<22}{'bal_acc':>9}  {'tiers':<8}{'cheap':>8}{'mid':>8}{'frontier':>9}{'under':>11}{'tier_acc':>9}"
        f"{'c%':>7}{'m%':>7}{'f%':>7}",
        "-" * 108,
        fmt("3-tier 2.0/4.5", te_res["3tier_2.0_4.5"]),
        fmt("2-tier 4.0/4.5", te_res["2tier_4.0_4.5"]),
        "",
        "--- FIT CHECK on the 17,600 training rows: MEMORIZATION, NOT QUALITY ---",
        f"{'policy':<22}{'bal_acc':>9}  {'tiers':<8}{'cheap':>8}{'mid':>8}{'frontier':>9}{'under':>11}{'tier_acc':>9}"
        f"{'c%':>7}{'m%':>7}{'f%':>7}",
        "-" * 108,
        fmt("3-tier 2.0/4.5", fit_res["3tier_2.0_4.5"]),
        fmt("2-tier 4.0/4.5", fit_res["2tier_4.0_4.5"]),
        "",
        "--- the number that decides the policy ---",
        "  frontier escape rate = gold-frontier tickets NOT sent to the frontier model",
    ]
    for k, lab in [("3tier_2.0_4.5", "3-tier 2.0/4.5"), ("2tier_4.0_4.5", "2-tier 4.0/4.5")]:
        s = te_res[k]
        lines.append(
            f"    {lab:<20} frontier escape {s['frontier_escape_rate']:.1%}  ({s['under']}/{s['n_frontier_gold']})"
            f"   cheap escape {s['cheap_escape']}/{s['n_cheap_gold']} ({s['cheap_escape'] / s['n_cheap_gold']:.1%})"
        )
    a, b = te_res["3tier_2.0_4.5"], te_res["2tier_4.0_4.5"]
    lines += [
        "",
        "--- reading this table ---",
        f"  frontier recall  3-tier {a.get('recall_frontier', float('nan')):.1%}   "
        f"2-tier {b.get('recall_frontier', float('nan')):.1%}",
        f"  cheap recall     3-tier {a.get('recall_cheap', float('nan')):.1%}   "
        f"2-tier {b.get('recall_cheap', float('nan')):.1%}",
        f"  traffic cheap    3-tier {100 * a['pred_cheap']:.1f}%   2-tier {100 * b['pred_cheap']:.1f}%",
        "",
        "  Balanced accuracy is averaged over tiers that have gold rows, and the count is",
        "  printed. Comparing a 3-tier score against a 2-tier score is only fair when both",
        "  average the same number of tiers. A mid band that lands between integer scores",
        "  has zero gold rows and silently drops out, which flatters the result.",
        "",
        "--- caveats ---",
        "  Quote the GENERALIZATION block. The FIT block is the shipped model re-reading",
        "  its own training rows and is not a quality estimate.",
        "  Thresholds were fixed before this run and not re-searched, so neither policy is",
        "  tuned to this test split.",
        "  Both policies share one regressor. Only the cut points differ.",
        "  Single-labeler scores: MAE near 0.69 partly measures agreement with one judge.",
        "  Scores 9-10 are 18 rows total, so the top band is unevidenced.",
    ]
    OUT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    OUT_JSON.write_text(
        json.dumps(
            {
                "regressor": {k: v for k, v in PARAMS.items() if k != "verbose"},
                "seeds": list(SEEDS),
                "n_train_rows": n,
                "eval_protocol": f"batch-level {N_TRAIN_B}/{N_CALIB_B}/{len(te_b)} of {len(batches)} batches, seed {SEED}",
                "holdout": {"rows": len(te), "mae": mae, "spearman": rho},
                "policies": {
                    k: {
                        "thr": {"cheap_ceil": v["lo"], "frontier_floor": v["hi"]},
                        "n_tiers": v["n_tiers"],
                        "holdout": te_res[k],
                        "fit": fit_res[k],
                    }
                    for k, v in POLICIES.items()
                },
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
