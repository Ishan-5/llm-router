"""What is the 4.0-4.5 band in the 2-tier policy, and can it be made useful?

The 2-tier policy is cheap <= 4.0, frontier >= 4.5. The band between them,
(4.0, 4.5), is where the 2-tier router is nominally 3-tier, but it is nearly
dead:

  gold scores are whole numbers, so no gold row can fall in (4.0, 4.5)
  predicted scores are continuous floats, so ~4% of predictions do land there

So the band receives traffic but has no gold rows to measure against. Its
recall is undefined, which is why the 2-tier balanced accuracy in
tier_comparison.txt averages only 2 tiers.

Two questions are answered here:

  1. what are the tickets that get predicted into 4.0-4.5? If their gold
     scores cluster at 4 they are gold-cheap tickets being pushed up; if they
     cluster at 5 they are gold-frontier tickets being held back.

  2. with the frontier floor pinned at 4.5 (the hard-ticket protection we
     bought), which cheap/mid split leaves a mid band that can actually be
     measured? Gold rows in (X, 4.5) exist only for whole scores above X, so
     the cheap/mid cut decides whether mid is measurable at all.

Both policies are evaluated on the same batch-level holdout as
train_tier_variants.py, thresholds fixed in advance, test scored once.

Outputs:
    docs/mid_band.txt
    docs/mid_band.json
"""

from __future__ import annotations

import csv
import json
import random
import re
from collections import Counter
from pathlib import Path

import numpy as np
from lightgbm import LGBMRegressor

ROOT = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[2]
LABELS = ROOT / "data" / "labeled" / "labeled_support.csv"
EMBED_DIR = REPO / "backend" / "models" / "minilm"
OUT_TXT = ROOT / "docs" / "mid_band.txt"
OUT_JSON = ROOT / "docs" / "mid_band.json"

SEED = 42
N_TRAIN_B, N_CALIB_B = 62, 13
FLOOR = 4.5  # pinned: the frontier floor that protects hard tickets

# cheap/mid cuts to compare, all with frontier floor fixed at 4.5
CUTS = [
    ("2-tier (dead mid)", 4.0),
    ("mid = score 4", 3.5),
    ("mid = score 4", 3.0),
    ("3-tier 2.0/4.5", 2.0),
    ("mid = 3 and 4", 2.0),
]

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


def tier(s: float, lo: float, hi: float = FLOOR) -> str:
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


def score(y, p, lo: float) -> dict:
    gold = [tier(v, lo) for v in y]
    pred = [tier(v, lo) for v in np.clip(p, 0, 10)]
    out = {"lo": lo, "hi": FLOOR}
    recs = []
    for t in ("cheap", "mid", "frontier"):
        gi = [i for i, g in enumerate(gold) if g == t]
        out[f"n_{t}"] = len(gi)
        if gi:
            out[f"recall_{t}"] = float(np.mean([pred[i] == t for i in gi]))
            recs.append(out[f"recall_{t}"])
        pi = [i for i, x in enumerate(pred) if x == t]
        out[f"predn_{t}"] = len(pi)
    out["n_tiers_scored"] = len(recs)
    out["balanced_acc"] = float(np.mean(recs)) if recs else 0.0
    out["tier_acc"] = float(np.mean([a == b for a, b in zip(gold, pred)]))
    fi = [i for i, g in enumerate(gold) if g == "frontier"]
    out["under"] = int(sum(1 for i in fi if pred[i] != "frontier"))
    out["n_frontier_gold"] = len(fi)
    ci = [i for i, g in enumerate(gold) if g == "cheap"]
    out["cheap_escape"] = int(sum(1 for i in ci if pred[i] != "cheap"))
    out["n_cheap_gold"] = len(ci)
    for t in ("cheap", "mid", "frontier"):
        out[f"pred_{t}"] = out[f"predn_{t}"] / len(y)
    return out


def main() -> int:
    rows = [r for r in csv.DictReader(LABELS.open(encoding="utf-8")) if r["query"].strip()]
    batches = sorted({r["batch"] for r in rows})
    order = random.Random(SEED).sample(batches, len(batches))
    tr_b = set(order[:N_TRAIN_B])
    te_b = set(order[N_TRAIN_B + N_CALIB_B :])
    tr = [r for r in rows if r["batch"] in tr_b]
    te = [r for r in rows if r["batch"] in te_b]

    fz = Featurizer(EMBED_DIR)
    ms = []
    for sd in (18, 19):
        m = LGBMRegressor(random_state=sd, **PARAMS)
        m.fit(
            fz.encode([r["query"] for r in tr]),
            np.array([float(r["score"]) for r in tr], dtype=np.float32),
        )
        ms.append(m)
    y = np.array([float(r["score"]) for r in te], dtype=np.float32)
    p = np.clip(
        np.mean([m.predict(fz.encode([r["query"] for r in te])) for m in ms], axis=0), 0, 10
    )
    print(f"test rows {len(te):,}  MAE {np.mean(np.abs(y - p)):.3f}  Spearman {spearman(y, p):.3f}\n")

    # ---- Q1: who lands in the dead 4.0-4.5 band? ----
    inband = (p > 4.0) & (p < FLOOR)
    lines = [
        "THE 4.0-4.5 BAND IN THE 2-TIER POLICY",
        "=" * 96,
        f"test rows            {len(te):,}",
        f"predicted into band  {int(inband.sum()):,}  ({100 * inband.mean():.1f}% of traffic)",
        "",
        "Gold scores of the tickets the model pushed into that band:",
        "",
    ]
    gc = Counter(int(y[i]) for i in np.where(inband)[0])
    tot = sum(gc.values()) or 1
    for k in sorted(gc):
        lines.append(f"  gold {k:>2}  {gc[k]:>5}  {100 * gc[k] / tot:5.1f}%  " + "#" * int(30 * gc[k] / tot))
    cheap_side = sum(v for k, v in gc.items() if k <= 4)
    front_side = sum(v for k, v in gc.items() if k >= 5)
    lines += [
        "",
        f"  gold <= 4 (truly easy)   {cheap_side:>5}  {100 * cheap_side / tot:5.1f}%",
        f"  gold >= 5 (truly hard)   {front_side:>5}  {100 * front_side / tot:5.1f}%",
        "",
        "Reading: the band holds tickets the model called borderline. A band made of",
        "gold-4 tickets is a real mid population being wasted on the cheap model; a band",
        "leaning gold-5 is hard tickets being held back from the frontier model.",
    ]

    # ---- Q2: cheap/mid cuts with the floor pinned at 4.5 ----
    lines += [
        "",
        "=" * 96,
        "CANDIDATE CUTS, frontier floor pinned at 4.5",
        f"{'label':<20}{'lo':>5}{'bal_acc':>9}{'tiers':>7}{'cheap':>8}{'mid':>8}{'front':>8}"
        f"{'f_esc':>8}{'c_esc':>8}{'c%':>7}{'m%':>7}{'f%':>7}{'gold_mid':>10}",
        "-" * 96,
    ]
    res = {}
    for lab, lo in CUTS:
        s = score(y, p, lo)
        res[lo] = {"label": lab, **s}
        r = lambda k: f"{s.get(k, float('nan')):.3f}"
        lines.append(
            f"{lab:<20}{lo:>5.1f}{s['balanced_acc']:>9.3f}{s['n_tiers_scored']:>7}"
            f"{r('recall_cheap'):>8}{r('recall_mid'):>8}{r('recall_frontier'):>8}"
            f"{s['under']:>4}/{s['n_frontier_gold']:<3}{s['cheap_escape']:>4}/{s['n_cheap_gold']:<3}"
            f"{100 * s['pred_cheap']:>7.1f}{100 * s['pred_mid']:>7.1f}{100 * s['pred_frontier']:>7.1f}"
            f"{s['n_mid']:>10}"
        )

    meas = [v for v in res.values() if v["n_mid"] > 0]
    best = max(meas, key=lambda v: v["balanced_acc"]) if meas else None
    lines += [
        "",
        "--- reading it ---",
        "  A cut of 4.0 leaves 0 gold mid rows, so the band cannot be measured and",
        "  balanced accuracy silently averages 2 tiers instead of 3. That is the",
        "  artefact flagged in tier_comparison.txt, not a real 2-tier advantage.",
        "",
    ]
    if best:
        lines += [
            f"  Best measurable cut: cheap <= {best['lo']}, mid to {FLOOR}, frontier >= {FLOOR}",
            f"    balanced accuracy {best['balanced_acc']:.3f} over {best['n_tiers_scored']} tiers",
            f"    frontier escape   {best['under']}/{best['n_frontier_gold']}"
            f"    cheap escape   {best['cheap_escape']}/{best['n_cheap_gold']}",
            f"    traffic          {100 * best['pred_cheap']:.1f}% cheap / {100 * best['pred_mid']:.1f}% mid"
            f" / {100 * best['pred_frontier']:.1f}% frontier",
            "",
            "  All candidates share the same frontier floor, so frontier escape is identical",
            "  across the table. The choice is purely about how much traffic to lift off the",
            "  cheap model and into a measurable mid band.",
        ]
    lines += [
        "",
        "--- caveats ---",
        "  Mid band measurability is a property of the labels, not the model: gold scores",
        "  are integers, so a band between two consecutive integers has no gold rows.",
        "  Thresholds were fixed before this run and not re-searched against the test split.",
        "  Nothing here shows the 120B mid model answers better than the 20B model; the",
        "  same harness question as before, still open.",
    ]

    OUT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    OUT_JSON.write_text(
        json.dumps(
            {
                "test_rows": len(te),
                "floor": FLOOR,
                "dead_band": {
                    "traffic_pct": float(100 * inband.mean()),
                    "gold_hist": {str(k): v for k, v in sorted(gc.items())},
                    "gold_easy": cheap_side,
                    "gold_hard": front_side,
                },
                "candidates": res,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
