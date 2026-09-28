"""Sweep LightGBM ensembles, hyperparameters and tier thresholds for the support model.

Answers three questions the earlier runs could not:

  1. Does averaging more LightGBM regressors help, or was the 2-model
     ensemble just habit carried over from the generic model?
  2. What are the actual tradeoffs across the threshold grid, including
     cheap<=3.5 / frontier>=6.5?
  3. Which (model, thresholds) pair should ship?

Selection rule, stated up front so the winner is not a surprise:

  A router is judged on not sending hard work to a small model. Maximizing
  tier accuracy is degenerate on this data, because the score distribution
  piles up on 6 and 7, so "predict cheap for everything" scores ~99% while
  under-routing every hard ticket. So the objective is:

      among all (model, thresholds) whose FRONTIER RECALL on the calibration
      batches clears --min-frontier-recall, take the one that routes the most
      traffic to the cheap tier.

  That is the cheapest router that does not under-route hard queries. Balanced
  accuracy and the cheap share are reported alongside, but not optimized.

Everything is selected on the calibration batches. The test batches are scored
once, after selection, and never influence the choice.

Split is by BATCH, not by row: near-duplicate tickets survive exact-normalized
dedup, so a row-level split leaks siblings across the boundary.

Outputs:
    docs/threshold_sweep.txt     full grid
    docs/best_config.json        the winner, for train_final_model.py to consume
"""

from __future__ import annotations

import csv
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

import joblib
import numpy as np
from lightgbm import LGBMRegressor

ROOT = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[2]
LABELS = ROOT / "data" / "labeled" / "labeled_support.csv"
EMBED_DIR = REPO / "backend" / "models" / "minilm"
OUT_TXT = ROOT / "docs" / "threshold_sweep.txt"
OUT_JSON = ROOT / "docs" / "best_config.json"

SEED = 42
N_TRAIN_B, N_CALIB_B = 62, 13
MIN_FRONTIER_RECALL = 0.70
USER_SUGGESTED = (3.5, 6.5)
GENERIC_THR = (4.5, 6.0)

GRID = [round(2.5 + 0.5 * i, 1) for i in range(12)]  # 2.5 .. 8.0


# ---------------------------------------------------------------- features
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


# ---------------------------------------------------------------- metrics
def score_to_tier(s: float, thr: tuple[float, float]) -> str:
    if s <= thr[0]:
        return "cheap"
    if s >= thr[1]:
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


def score_at(y, p, thr) -> dict:
    gold = [score_to_tier(v, thr) for v in y]
    pred = [score_to_tier(v, thr) for v in np.clip(p, 0, 10)]
    out = {}
    for t in ("cheap", "mid", "frontier"):
        gi = [i for i, g in enumerate(gold) if g == t]
        if gi:
            out[f"recall_{t}"] = float(np.mean([pred[i] == t for i in gi]))
            out[f"n_{t}"] = len(gi)
    present = [t for t in ("cheap", "mid", "frontier") if f"recall_{t}" in out]
    out["balanced_acc"] = float(np.mean([out[f"recall_{t}"] for t in present])) if present else 0.0
    out["tier_acc"] = float(np.mean([a == b for a, b in zip(gold, pred)]))
    out["pred_cheap_share"] = float(np.mean([x == "cheap" for x in pred]))
    out["pred_frontier_share"] = float(np.mean([x == "frontier" for x in pred]))
    f_idx = [i for i, g in enumerate(gold) if g == "frontier"]
    out["under"] = int(sum(1 for i in f_idx if pred[i] != "frontier"))
    out["over"] = int(
        sum(1 for i, g in enumerate(gold) if g != "frontier" and pred[i] == "frontier")
    )
    return out


def all_thresholds(y, p):
    res = []
    for lo in GRID:
        for hi in GRID:
            if hi <= lo:
                continue
            thr = (lo, hi)
            s = score_at(y, p, thr)
            s["cheap_ceil"] = lo
            s["frontier_floor"] = hi
            res.append(s)
    return res


# ---------------------------------------------------------------- configs
BASE = dict(
    objective="regression",
    n_estimators=400,
    learning_rate=0.05,
    num_leaves=31,
    colsample_bytree=0.8,
    subsample=0.8,
    verbose=-1,
)

CONFIGS: list[tuple[str, list[dict]]] = [
    ("1x default", [dict(BASE)]),
    ("2x default (current)", [dict(BASE, random_state=18), dict(BASE, random_state=19)]),
    (
        "3x default",
        [dict(BASE, random_state=s) for s in (18, 19, 20)],
    ),
    (
        "4x default",
        [dict(BASE, regular_random_state=s) for s in (18, 19, 20, 21)],
    ),
    (
        "2x deeper",
        [dict(BASE, num_leaves=63, random_state=s) for s in (18, 19)],
    ),
    (
        "2x shallow",
        [dict(BASE, num_leaves=15, random_state=s) for s in (18, 19)],
    ),
    (
        "2x more trees",
        [dict(BASE, n_estimators=1200, learning_rate=0.02, random_state=s) for s in (18, 19)],
    ),
    (
        "2x L1 objective",
        [dict(BASE, objective="regression_l1", random_state=s) for s in (18, 19)],
    ),
    (
        "2x min_data_leaf=40",
        [dict(BASE, min_child_samples=40, random_state=s) for s in (18, 19)],
    ),
]


def fit_predict(param_list, Xtr, ytr, Xa, Xb):
    out = []
    for p in param_list:
        m = LGBMRegressor(**p)
        m.fit(Xtr, ytr)
        out.append((m.predict(Xa), m.predict(Xb)))
    return (
        np.clip(np.mean([o[0] for o in out], axis=0), 0, 10),
        np.clip(np.mean([o[1] for o in out], axis=0), 0, 10),
    )


# ---------------------------------------------------------------- main
def main() -> int:
    rows = [r for r in csv.DictReader(LABELS.open(encoding="utf-8")) if r["query"].strip()]
    batches = sorted({r["batch"] for r in rows})
    order = random.Random(SEED).sample(batches, len(batches))
    tr_b = set(order[:N_TRAIN_B])
    ca_b = set(order[N_TRAIN_B : N_TRAIN_B + N_CALIB_B])
    te_b = set(order[N_TRAIN_B + N_CALIB_B :])

    def part(bs):
        sel = [r for r in rows if r["batch"] in bs]
        return (
            [r["query"] for r in sel],
            np.array([float(r["score"]) for r in sel], dtype=np.float32),
        )

    qtr, ytr = part(tr_b)
    qca, yca = part(ca_b)
    qte, yte = part(te_b)
    print(f"train {len(qtr):,}  calib {len(qca):,}  test {len(qte):,}  (split by batch, seed {SEED})")

    fz = Featurizer(EMBED_DIR)
    Xtr, Xca, Xte = fz.encode(qtr), fz.encode(qca), fz.encode(qte)

    results = {}
    lines = [
        "SUPPORT MODEL SWEEP",
        "=" * 78,
        f"selection: frontier recall >= {MIN_FRONTIER_RECALL:.0%} on calib, then maximize",
        "           predicted cheap share. Selection uses calib only.",
        "",
        "=== regression quality (thresholds do not affect these) ===",
        f"{'config':<22}{'MAE_calib':>11}{'MAE_test':>10}{'Spearman':>10}",
        "-" * 78,
    ]

    for name, params in CONFIGS:
        pca, pte = fit_predict(params, Xtr, ytr, Xca, Xte)
        mae_c = float(np.mean(np.abs(yca - pca)))
        mae_t = float(np.mean(np.abs(yte - pte)))
        rho = spearman(yte, pte)
        results[name] = {"pca": pca, "pte": pte, "mae_calib": mae_c, "mae_test": mae_t, "spearman": rho, "params": params}
        lines.append(f"{name:<22}{mae_c:>11.3f}{mae_t:>10.3f}{rho:>10.3f}")
        print(f"  {name:<22} MAE {mae_t:.3f}  spearman {rho:.3f}")

    # ---- pick the best regression model on calib MAE ----
    best_reg = min(results, key=lambda k: results[k]["mae_calib"])
    print(f"\nbest regression quality on calib: {best_reg} (MAE {results[best_reg]['mae_calib']:.3f})")

    # ---- threshold selection across ALL models, on calib only ----
    print("\nselecting (model, thresholds) on calib ...")
    cands = []
    for name, r in results.items():
        for s in all_thresholds(yca, r["pca"]):
            s["config"] = name
            cands.append(s)
    safe = [c for c in cands if c.get("recall_frontier", 0) >= MIN_FRONTIER_RECALL]
    if safe:
        winner = max(safe, key=lambda c: c["pred_cheap_share"])
        note = f"cleared the {MIN_FRONTIER_RECALL:.0%} frontier-recall bar"
    else:
        best_rec = max(c.get("recall_frontier", 0) for c in cands)
        pool = [c for c in cands if abs(c.get("recall_frontier", 0) - best_rec) < 1e-9]
        winner = max(pool, key=lambda c: c["pred_cheap_share"])
        note = (
            f"NO pair reached {MIN_FRONTIER_RECALL:.0%} frontier recall; "
            f"best achievable was {best_rec:.1%}, so the winner maximises that instead"
        )

    print(f"  winner: {winner['config']}  cheap<={winner['cheap_ceil']}  frontier>={winner['frontier_floor']}")
    print(f"  {note}")

    # ---- score the winner once on test ----
    wr = results[winner["config"]]
    thr = (winner["cheap_ceil"], winner["frontier_floor"])
    test = score_at(yte, wr["pte"], thr)

    lines += [
        "",
        "=== threshold grid, best regression model, on CALIB batches ===",
        f"config: {best_reg}",
        f"{'cheap<=':>8}{'frontier>=':>11}{'f_recall':>10}{'c_recall':>10}"
        f"{'m_recall':>10}{'bal_acc':>9}{'pred_cheap%':>12}{'under':>7}",
        "-" * 78,
    ]
    grid_rows = [s for s in all_thresholds(yca, wr["pca"])]
    for s in grid_rows:
        lines.append(
            f"{s['cheap_ceil']:>8}{s['frontier_floor']:>11}"
            f"{s.get('recall_frontier', float('nan')):>10.3f}"
            f"{s.get('recall_cheap', float('nan')):>10.3f}"
            f"{s.get('recall_mid', float('nan')):>10.3f}"
            f"{s['balanced_acc']:>9.3f}"
            f"{100 * s['pred_cheap_share']:>11.1f}%{s['under']:>7}"
        )

    lines += [
        "",
        "=== points of interest ===",
    ]
    for label, t in [("user suggested", USER_SUGGESTED), ("generic model", GENERIC_THR), ("winner", thr)]:
        s = score_at(yca, wr["pca"], t)
        lines.append(
            f"  {label:<16} cheap<={t[0]:<5} frontier>={t[1]:<5} "
            f"f_recall {s.get('recall_frontier', float('nan')):.3f}  "
            f"bal_acc {s['balanced_acc']:.3f}  "
            f"pred_cheap {100 * s['pred_cheap_share']:.1f}%  under {s['under']}"
        )

    lines += [
        "",
        "=== WINNER, scored once on the TEST batches ===",
        f"  config                {winner['config']}",
        f"  thresholds            cheap <= {thr[0]}, frontier >= {thr[1]}",
        f"  test rows             {len(yte):,}",
        f"  MAE                   {wr['mae_test']:.3f}",
        f"  Spearman              {wr['spearman']:.3f}",
        f"  tier accuracy         {test['tier_acc']:.1%}",
        f"  balanced accuracy     {test['balanced_acc']:.1%}",
        f"  frontier recall       {test.get('recall_frontier', float('nan')):.1%}  (n={test.get('n_frontier', 0)})",
        f"  cheap recall          {test.get('recall_cheap', float('nan')):.1%}  (n={test.get('n_cheap', 0)})",
        f"  mid recall            {test.get('recall_mid', float('nan')):.1%}  (n={test.get('n_mid', 0)})",
        f"  under-routed          {test['under']} of {test.get('n_frontier', 0)} gold frontier",
        f"  over-routed           {test['over']}",
        f"  predicted cheap share {100 * test['pred_cheap_share']:.1f}%",
        f"  predicted mid share   {100 * (1 - test['pred_cheap_share'] - test['pred_frontier_share']):.1f}%",
        f"  predicted front share {100 * test['pred_frontier_share']:.1f}%",
    ]
    if not test.get("n_mid"):
        lines.append("  note: the mid band is empty at these thresholds, so this is a 2-tier router.")

    OUT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    OUT_JSON.write_text(
        json.dumps(
            {
                "config": winner["config"],
                "params": [{k: v for k, v in p.items() if k != "verbose"} for p in wr["params"]],
                "thr": list(thr),
                "test": {
                    "mae": wr["mae_test"],
                    "spearman": wr["spearman"],
                    "tier_acc": test["tier_acc"],
                    "balanced_acc": test["balanced_acc"],
                    "frontier_recall": test.get("recall_frontier"),
                    "under": test["under"],
                    "over": test["over"],
                },
                "selection": {
                    "rule": f"frontier recall >= {MIN_FRONTIER_RECALL} on calib, then max predicted cheap share",
                    "note": note,
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print()
    print("\n".join(lines[lines.index("=== WINNER, scored once on the TEST batches ===") :]))
    print(f"\nwrote {OUT_TXT}")
    print(f"wrote {OUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
