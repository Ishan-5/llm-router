"""Train the final customer-support difficulty model on all 17,600 labels.

Config comes from three_tier_sweep.py, which selected on a calibration split
and was scored once on a held-out test split:

    objective      regression_l1
    ensemble       2 LightGBM regressors, seeds 18 and 19
    estimators     1200 trees at learning rate 0.02
    features       MiniLM-L6-v2 384-dim THEN 4 handcrafted = 388
    thresholds     cheap <= 2.0, mid to 5.0, frontier >= 5.0

L1 beats L2 here (MAE 0.688 vs 0.756) because squared error under-predicts
the hard tail, which is the compression problem this model has.

Two phases, because "train on everything" and "know how good it is" are
different questions:

  1. Evaluation. Split 88 batches 62/13/13. Batches, not rows: near-duplicate
     tickets survive exact-normalized dedup, so a row-level split leaks
     siblings and inflates the score. Thresholds are fixed, not re-searched.
     This model is thrown away.

  2. Ship. Refit on all 17,600 rows with the config above and write
     models/support_final.joblib. Its own predictions are then scored on the
     training rows, which is a FIT check only, not a generalization estimate.
     The number to quote is the phase 1 test figure.

The 845 MB MiniLM embedder is loaded in place from backend/models/minilm; it
is never copied.

Outputs:
    models/support_final.joblib
    docs/final_model_report.txt
"""

from __future__ import annotations

import csv
import json
import random
import re
from collections import Counter
from pathlib import Path

import joblib
import numpy as np
from lightgbm import LGBMRegressor

ROOT = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[2]
LABELS = ROOT / "data" / "labeled" / "labeled_support.csv"
EMBED_DIR = REPO / "backend" / "models" / "minilm"
OUT_DIR = ROOT / "models"
REPORT = ROOT / "docs" / "final_model_report.txt"

SEED = 42
N_TRAIN_B, N_CALIB_B = 62, 13
CHEAP_CEIL = 2.0
FRONTIER_FLOOR = 5.0
ENSEMBLE_SEEDS = (18, 19)

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


def tier3(s: float, lo: float = CHEAP_CEIL, hi: float = FRONTIER_FLOOR) -> str:
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


def score3(y, p) -> dict:
    gold = [tier3(v) for v in y]
    pred = [tier3(v) for v in np.clip(p, 0, 10)]
    out = {}
    recs = []
    for t in ("cheap", "mid", "frontier"):
        gi = [i for i, g in enumerate(gold) if g == t]
        out[f"n_{t}"] = len(gi)
        if gi:
            out[f"recall_{t}"] = float(np.mean([pred[i] == t for i in gi]))
            recs.append(out[f"recall_{t}"])
    out["balanced_acc"] = float(np.mean(recs)) if recs else 0.0
    out["tier_acc"] = float(np.mean([a == b for a, b in zip(gold, pred)]))
    out["pred_cheap"] = float(np.mean([x == "cheap" for x in pred]))
    out["pred_mid"] = float(np.mean([x == "mid" for x in pred]))
    out["pred_front"] = float(np.mean([x == "frontier" for x in pred]))
    fi = [i for i, g in enumerate(gold) if g == "frontier"]
    out["under"] = int(sum(1 for i in fi if pred[i] != "frontier"))
    return out


def train(X, y) -> list:
    ms = []
    for sd in ENSEMBLE_SEEDS:
        m = LGBMRegressor(random_state=sd, **PARAMS)
        m.fit(X, y)
        ms.append(m)
    return ms


def predict(ms, X) -> np.ndarray:
    return np.clip(np.mean([m.predict(X) for m in ms], axis=0), 0, 10)


def main() -> int:
    rows = [r for r in csv.DictReader(LABELS.open(encoding="utf-8")) if r["query"].strip()]
    n = len(rows)
    batches = sorted({r["batch"] for r in rows})
    y_all = np.array([float(r["score"]) for r in rows], dtype=np.float32)

    # ---------- phase 1: honest generalization estimate ----------
    order = random.Random(SEED).sample(batches, len(batches))
    tr_b, ca_b = set(order[:N_TRAIN_B]), set(order[N_TRAIN_B : N_TRAIN_B + N_CALIB_B])
    te_b = set(order[N_TRAIN_B + N_CALIB_B :])
    tr = [r for r in rows if r["batch"] in tr_b]
    ca = [r for r in rows if r["batch"] in ca_b]
    te = [r for r in rows if r["batch"] in te_b]

    print(f"phase 1: evaluation split  train {len(tr):,}  calib {len(ca):,}  test {len(te):,}")
    fz = Featurizer(EMBED_DIR)
    ms = train(
        fz.encode([r["query"] for r in tr]),
        np.array([float(r["score"]) for r in tr], dtype=np.float32),
    )
    y_te = np.array([float(r["score"]) for r in te], dtype=np.float32)
    p_te = predict(ms, fz.encode([r["query"] for r in te]))
    t_te = score3(y_te, p_te)
    mae_te = float(np.mean(np.abs(y_te - p_te)))
    rho_te = spearman(y_te, p_te)
    print(f"  MAE {mae_te:.3f}  Spearman {rho_te:.3f}  balanced {t_te['balanced_acc']:.1%}")
    print(f"  cheap {t_te.get('recall_cheap', 0):.1%}  mid {t_te.get('recall_mid', 0):.1%}  frontier {t_te.get('recall_frontier', 0):.1%}")

    # ---------- phase 2: ship on all rows ----------
    print(f"\nphase 2: refitting on all {n:,} rows")
    X_all = fz.encode([r["query"] for r in rows])
    final = train(X_all, y_all)
    p_fit = predict(final, X_all)
    t_fit = score3(y_all, p_fit)
    mae_fit = float(np.mean(np.abs(y_all - p_fit)))
    print(f"  fit check (NOT generalization): MAE {mae_fit:.3f}  Spearman {spearman(y_all, p_fit):.3f}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "support_final.joblib"
    joblib.dump(
        {
            "models": final,
            "seeds": list(ENSEMBLE_SEEDS),
            "params": {k: v for k, v in PARAMS.items() if k != "verbose"},
            "feature_count": int(X_all.shape[1]),
            "feature_order": "minilm384_then_handcrafted4",
            "embedder": str(EMBED_DIR),
            "thr": {"cheap_ceil": CHEAP_CEIL, "frontier_floor": FRONTIER_FLOOR},
            "n_train_rows": n,
            "source": "customer_support",
            "honest_eval": {
                "protocol": "batch-level split, 62/13/13 of 88 batches, thresholds fixed not tuned",
                "test_rows": len(te),
                "mae": mae_te,
                "spearman": rho_te,
                "tier_acc": t_te["tier_acc"],
                "balanced_acc": t_te["balanced_acc"],
                "recall_cheap": t_te.get("recall_cheap"),
                "recall_mid": t_te.get("recall_mid"),
                "recall_frontier": t_te.get("recall_frontier"),
                "under": t_te["under"],
            },
        },
        out_path,
    )

    dist = Counter(int(v) for v in y_all)
    gold_fit = Counter(tier3(v) for v in y_all)
    pred_fit = Counter(tier3(v) for v in p_fit)
    lines = [
        "=" * 70,
        "FINAL CUSTOMER-SUPPORT DIFFICULTY MODEL",
        "=" * 70,
        f"training rows        {n:,}   (88 of 238 batches labeled)",
        f"features             388   MiniLM-L6-v2 384 + 4 handcrafted, embedding first",
        f"regressors           2 LightGBM, objective regression_l1, 1200 trees @ lr 0.02",
        f"                     seeds {ENSEMBLE_SEEDS[0]} and {ENSEMBLE_SEEDS[1]}, averaged, clipped 0-10",
        f"tier thresholds      cheap <= {CHEAP_CEIL}, frontier >= {FRONTIER_FLOOR}",
        "",
        "--- GENERALIZATION: batch-level holdout, thresholds fixed, scored once ---",
        "    (this is the number to quote)",
        f"  test rows          {len(te):,}",
        f"  MAE                {mae_te:.3f}",
        f"  Spearman           {rho_te:.3f}",
        f"  tier accuracy      {t_te['tier_acc']:.1%}",
        f"  balanced accuracy  {t_te['balanced_acc']:.1%}",
        f"  cheap recall       {t_te.get('recall_cheap', 0):.1%}  (n={t_te['n_cheap']})",
        f"  mid recall         {t_te.get('recall_mid', 0):.1%}  (n={t_te['n_mid']})",
        f"  frontier recall    {t_te.get('recall_frontier', 0):.1%}  (n={t_te['n_frontier']})",
        f"  under-routed       {t_te['under']} of {t_te['n_frontier']} gold frontier",
        "",
        "--- FIT CHECK: same numbers on the training rows, for contrast only ---",
        f"  MAE                {mae_fit:.3f}",
        f"  balanced accuracy  {t_fit['balanced_acc']:.1%}",
        f"  gold tier mix      {dict(gold_fit)}",
        f"  pred tier mix      {dict(pred_fit)}",
        "",
        "--- training score distribution ---",
    ]
    for k in range(11):
        c = dist.get(k, 0)
        lines.append(f"  {k:>2}  {c:>6,}  {100 * c / n:5.1f}%  " + "#" * int(40 * c / n))
    lines += [f"  mean {y_all.mean():.2f}", "", "--- by domain ---"]
    for dom, c in Counter(r["domain"] for r in rows).most_common():
        sub = np.array([float(r["score"]) for r in rows if r["domain"] == dom])
        fr = float(np.mean([tier3(v) == "frontier" for v in sub]))
        lines.append(
            f"  {dom:<18} {c:>6,}  {100 * c / n:5.1f}%  mean {sub.mean():.2f}  frontier {100 * fr:5.1f}%"
        )
    lines += [
        "",
        "--- caveats ---",
        "  The fit-check MAE is much lower than the holdout MAE because the shipped model",
        "  has seen every row. Quote the holdout figure, never the fit figure.",
        "  Mid recall is the weakest tier and partly measures label noise: on a 1,000-ticket",
        "  two-labeler overlap, agreement at score 5 was 5.7%, the worst of any score.",
        "  Labels are from one labeler, so MAE near 0.69 is partly agreement with that judge.",
        "  Scores 9-10 are 18 rows across 17,600. The top band is unevidenced.",
        "  A 2-tier split scores higher on router metrics (balanced 0.887 vs 0.818) but sends",
        "  30% of traffic to frontier versus 26%. The 3-tier choice is a cost-vs-quality bet",
        "  that needs an answer-quality harness, not just router metrics, to justify.",
        "",
        f"wrote {out_path}",
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print()
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
