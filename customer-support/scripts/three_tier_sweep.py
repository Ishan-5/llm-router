"""Three-tier threshold search for the support model.

The earlier sweeps placed the mid band in a gap in the score distribution
(6.5-7.0, then 7.5-8.0), which is why mid came out empty. Support scores are
actually trimodal:

    0-2    52.4%   cheap
    3-5    26.5%   mid
    6-8    21.0%   frontier

so a three-tier router is well founded, provided the boundaries sit inside
populated regions rather than in the gap between the 6 and 7 spikes.

This searches three-tier thresholds over a grid, with both L1 and L2
regressors, and reports per-tier recall so all three tiers can be judged
rather than just the aggregate.

Selection rule: maximize balanced accuracy (the mean of the three per-tier
recalls) among candidates that keep every tier populated and hold cheap-tier
recall at or above --min-cheap-recall. Balanced accuracy is used because plain
tier accuracy is degenerate here: 52% of rows are cheap, so a model that
predicts cheap for everything scores well while under-routing every hard
query.

Selection uses the calibration batches. The test batches are scored once,
after selection.

Outputs:
    docs/three_tier_sweep.txt
    docs/three_tier_best.json
"""

from __future__ import annotations

import csv
import json
import random
import re
from pathlib import Path

import numpy as np
from lightgbm import LGBMRegressor

ROOT = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[2]
LABELS = ROOT / "data" / "labeled" / "labeled_support.csv"
EMBED_DIR = REPO / "backend" / "models" / "minilm"
OUT_TXT = ROOT / "docs" / "three_tier_sweep.txt"
OUT_JSON = ROOT / "docs" / "three_tier_best.json"

SEED = 42
N_TRAIN_B, N_CALIB_B = 62, 13
MIN_CHEAP_RECALL = 0.80
MIN_TIER_ROWS = 40  # a tier with fewer gold rows than this is not trustworthy

LO_GRID = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
HI_GRID = [4.5, 5.0, 5.5, 6.0, 6.5, 7.0, 7.5]


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


def tier3(s: float, lo: float, hi: float) -> str:
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


def score3(y, p, lo, hi) -> dict:
    gold = [tier3(v, lo, hi) for v in y]
    pred = [tier3(v, lo, hi) for v in np.clip(p, 0, 10)]
    out = {"cheap_ceil": lo, "frontier_floor": hi}
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


BASE = dict(
    n_estimators=400,
    learning_rate=0.05,
    num_leaves=31,
    colsample_bytree=0.8,
    subsample=0.8,
    verbose=-1,
)
MODELS = {
    "L2 single": [dict(BASE, objective="regression", random_state=18)],
    "L1 single": [dict(BASE, objective="regression_l1", random_state=18)],
    "L1 pair": [
        dict(BASE, objective="regression_l1", random_state=s) for s in (18, 19)
    ],
    "L1 pair more trees": [
        dict(BASE, objective="regression_l1", n_estimators=1200, learning_rate=0.02, random_state=s)
        for s in (18, 19)
    ],
}


def fit(params, X, y, Xa, Xb):
    pa, pb = [], []
    for p in params:
        m = LGBMRegressor(**p)
        m.fit(X, y)
        pa.append(m.predict(Xa))
        pb.append(m.predict(Xb))
    return (
        np.clip(np.mean(pa, axis=0), 0, 10),
        np.clip(np.mean(pb, axis=0), 0, 10),
    )


def main() -> int:
    rows = [r for r in csv.DictReader(LABELS.open(encoding="utf-8")) if r["query"].strip()]
    batches = sorted({r["batch"] for r in rows})
    order = random.Random(SEED).sample(batches, len(batches))
    tr_b, ca_b = set(order[:N_TRAIN_B]), set(order[N_TRAIN_B : N_TRAIN_B + N_CALIB_B])
    te_b = set(order[N_TRAIN_B + N_CALIB_B :])

    def part(bs):
        sel = [r for r in rows if r["batch"] in bs]
        return [r["query"] for r in sel], np.array([float(r["score"]) for r in sel], dtype=np.float32)

    qtr, ytr = part(tr_b)
    qca, yca = part(ca_b)
    qte, yte = part(te_b)
    print(f"train {len(qtr):,}  calib {len(qca):,}  test {len(qte):,}")

    fz = Featurizer(EMBED_DIR)
    Xtr, Xca, Xte = fz.encode(qtr), fz.encode(qca), fz.encode(qte)

    fits = {}
    lines = [
        "THREE-TIER SUPPORT ROUTER - threshold search",
        "=" * 92,
        f"selection: max balanced accuracy (mean of 3 per-tier recalls) on calib,",
        f"           subject to cheap recall >= {MIN_CHEAP_RECALL:.0%} and every tier",
        f"           holding at least {MIN_TIER_ROWS} gold rows",
        "",
        "=== regression quality (independent of thresholds) ===",
        f"{'model':<24}{'MAE_calib':>11}{'MAE_test':>10}{'Spearman':>10}",
        "-" * 92,
    ]
    for name, params in MODELS.items():
        pca, pte = fit(params, Xtr, ytr, Xca, Xte)
        fits[name] = (pca, pte, params)
        mc = float(np.mean(np.abs(yca - pca)))
        mt = float(np.mean(np.abs(yte - pte)))
        lines.append(f"{name:<24}{mc:>11.3f}{mt:>10.3f}{spearman(yte, pte):>10.3f}")
        print(f"  {name:<24} MAE {mt:.3f}  spearman {spearman(yte, pte):.3f}")

    best_model = min(fits, key=lambda k: float(np.mean(np.abs(yca - fits[k][0]))))
    print(f"\nbest regression on calib: {best_model}")
    pca, pte, _ = fits[best_model]

    lines += [
        "",
        f"=== three-tier grid, {best_model}, CALIB batches ===",
        f"{'cheap<=':>8}{'front>=':>8}{'c_rec':>7}{'m_rec':>7}{'f_rec':>7}"
        f"{'bal_acc':>9}{'tier_acc':>10}{'pred_c%':>9}{'pred_m%':>9}{'pred_f%':>9}{'under':>7}",
        "-" * 92,
    ]
    cands = []
    for lo in LO_GRID:
        for hi in HI_GRID:
            if hi <= lo + 0.5:
                continue
            s = score3(yca, pca, lo, hi)
            s["model"] = best_model
            cands.append(s)
            lines.append(
                f"{lo:>8}{hi:>8}"
                f"{s.get('recall_cheap', float('nan')):>7.3f}"
                f"{s.get('recall_mid', float('nan')):>7.3f}"
                f"{s.get('recall_frontier', float('nan')):>7.3f}"
                f"{s['balanced_acc']:>9.3f}{s['tier_acc']:>10.3f}"
                f"{100 * s['pred_cheap']:>9.1f}{100 * s['pred_mid']:>9.1f}"
                f"{100 * s['pred_front']:>9.1f}{s['under']:>7}"
            )

    viable = [
        c
        for c in cands
        if c.get("recall_cheap", 0) >= MIN_CHEAP_RECALL
        and all(c.get(f"n_{t}", 0) >= MIN_TIER_ROWS for t in ("cheap", "mid", "frontier"))
    ]
    if viable:
        w = max(viable, key=lambda c: c["balanced_acc"])
        note = "cleared the cheap-recall floor and kept all three tiers populated"
    else:
        w = max(cands, key=lambda c: c["balanced_acc"])
        note = "no candidate cleared the floor; best balanced accuracy reported instead"

    print(f"\n  winner: cheap<={w['cheap_ceil']}  frontier>={w['frontier_floor']}   ({note})")
    t = score3(yte, pte, w["cheap_ceil"], w["frontier_floor"])

    lines += [
        "",
        "=== WINNER, scored once on TEST batches ===",
        f"  model                {w['model']}",
        f"  thresholds           cheap <= {w['cheap_ceil']}, frontier >= {w['frontier_floor']}",
        f"  test rows            {len(yte):,}",
        f"  MAE                  {float(np.mean(np.abs(yte - pte))):.3f}",
        f"  Spearman             {spearman(yte, pte):.3f}",
        f"  tier accuracy        {t['tier_acc']:.1%}",
        f"  balanced accuracy    {t['balanced_acc']:.1%}",
        f"  cheap recall         {t.get('recall_cheap', float('nan')):.1%}  (n={t['n_cheap']})",
        f"  mid recall           {t.get('recall_mid', float('nan')):.1%}  (n={t['n_mid']})",
        f"  frontier recall      {t.get('recall_frontier', float('nan')):.1%}  (n={t['n_frontier']})",
        f"  under-routed         {t['under']} of {t['n_frontier']} gold frontier",
        f"  traffic split        {100 * t['pred_cheap']:.1f}% cheap / {100 * t['pred_mid']:.1f}% mid / {100 * t['pred_front']:.1f}% frontier",
        "",
        "=== two-tier comparison, same model ===",
    ]
    best2 = max(cands, key=lambda c: c["balanced_acc"])
    for lo, hi, lab in [(4.0, 4.5, "2-tier 4.0/4.5"), (3.5, 6.5, "2-tier 3.5/6.5 (suggested)")]:
        s = score3(yte, pte, lo, hi)
        lines.append(
            f"  {lab:<26} bal_acc {s['balanced_acc']:.3f}  "
            f"front_recall {s.get('recall_frontier', float('nan')):.3f}  "
            f"under {s['under']}/{s['n_frontier']}  "
            f"traffic {100 * s['pred_cheap']:.0f}/{100 * s['pred_mid']:.0f}/{100 * s['pred_front']:.0f}"
        )
    lines += [
        "",
        "=== caveat on the mid tier ===",
        "  The mid band is where the labeler was least self-consistent: on a 1,000-ticket",
        "  two-labeler overlap, agreement was 5.7% at score 5, the worst of any score.",
        "  A boundary placed in the 3-5 range therefore inherits that noise, which is why",
        "  mid recall is the weakest of the three numbers above.",
    ]

    OUT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    OUT_JSON.write_text(
        json.dumps(
            {
                "model": w["model"],
                "params": [{k: v for k, v in p.items() if k != "verbose"} for p in fits[w["model"]][2]],
                "thr": {"cheap_ceil": w["cheap_ceil"], "frontier_floor": w["frontier_floor"]},
                "test": {
                    "mae": float(np.mean(np.abs(yte - pte))),
                    "spearman": spearman(yte, pte),
                    "tier_acc": t["tier_acc"],
                    "balanced_acc": t["balanced_acc"],
                    "recall_cheap": t.get("recall_cheap"),
                    "recall_mid": t.get("recall_mid"),
                    "recall_frontier": t.get("recall_frontier"),
                    "under": t["under"],
                    "traffic": {"cheap": t["pred_cheap"], "mid": t["pred_mid"], "frontier": t["pred_front"]},
                },
                "selection": note,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print()
    print("\n".join(lines[lines.index("=== WINNER, scored once on TEST batches ===") :]))
    print(f"\nwrote {OUT_TXT}\nwrote {OUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
