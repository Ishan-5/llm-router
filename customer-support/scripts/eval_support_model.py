"""Evaluate the customer-support difficulty model on held-out SUPPORT tickets.

This replaces train_support_models.py, which compared the support model against
generic-domain gold (programming, writing, reasoning). That comparison was
meaningless: support mode is a separate model that only ever scores support
tickets, so it is evaluated on held-out support tickets.

Protocol
--------
Split by BATCH, not by row. DS2/DS3 contain near-duplicate tickets that survived
exact-normalized dedup, so a random row split leaks siblings across the
boundary and inflates the score. Batches are the unit here.

  train    60 batches   fit the regressors
  calib    14 batches   grid-search the tier thresholds
  test     14 batches   reported only; never touched during fitting or calibration

Reported on the test batches:
  MAE / Spearman / exact-tier accuracy
  per-tier recall, and under/over-routing counts
  the deployed generic model on the same rows, as a secondary reference for
  "would the current model have been better if we shipped nothing new?"
  score distribution vs the deployed 4.5 / 6.0 thresholds, because those were
  calibrated on generic data and are probably wrong here

Also reported: what the model predicts for the hardest support tickets, which is
the "customer asks for a system design in a support chatbot" risk.
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

REPO = Path(r"D:\llm-router")
CS = Path(__file__).resolve().parents[1]
LABELS = CS / "data" / "labeled" / "labeled_support.csv"
GENERIC = REPO / "backend" / "models" / "difficulty_regressor.joblib"
EMBED_DIR = REPO / "backend" / "models" / "minilm"
OUT = CS / "models"
REPORT = CS / "docs" / "support_eval_report.md"

DEPLOYED_THR = (4.5, 6.0)
SEED = 42
ENSEMBLE_SEEDS = (18, 19)

sys.path.insert(0, str(REPO / "backend" / "src"))


# ---------------------------------------------------------------- features
def handcrafted(query: str) -> list[float]:
    """Must stay byte-identical to predict_difficulty.py."""
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
def score_to_tier(score: float, thr: tuple[float, float]) -> str:
    if score <= thr[0]:
        return "cheap"
    if score >= thr[1]:
        return "frontier"
    return "mid"


def spearman(a, b) -> float:
    def rank(x):
        x = np.asarray(x, float)
        order = np.argsort(x, kind="mergesort")
        r = np.empty(len(x), dtype=np.float64)
        r[order] = np.arange(1, len(x) + 1)
        _, inv, cnt = np.unique(x, return_inverse=True, return_counts=True)
        sums = np.zeros(len(cnt), dtype=np.float64)
        np.add.at(sums, inv, r)
        return (sums / cnt)[inv]

    ra, rb = rank(a), rank(b)
    ra -= ra.mean()
    rb -= rb.mean()
    den = float(np.sqrt((ra**2).sum() * (rb**2).sum()))
    return float((ra * rb).sum() / den) if den else 0.0


def evaluate(y, p, thr) -> dict:
    y = np.asarray(y, float)
    p = np.clip(np.asarray(p, float), 0, 10)
    tt = [score_to_tier(v, thr) for v in y]
    tp = [score_to_tier(v, thr) for v in p]
    recall = {}
    for t in ("cheap", "mid", "frontier"):
        idx = [i for i, x in enumerate(tt) if x == t]
        if idx:
            recall[t] = (float(np.mean([tp[i] == t for i in idx])), len(idx))
    return {
        "mae": float(np.mean(np.abs(y - p))),
        "spearman": spearman(y, p),
        "tier_acc": float(np.mean([a == b for a, b in zip(tt, tp)])),
        "recall": recall,
        "under": int(sum(1 for a, b in zip(tt, tp) if a == "frontier" and b != "frontier")),
        "over": int(sum(1 for a, b in zip(tt, tp) if a != "frontier" and b == "frontier")),
        "n_frontier": tt.count("frontier"),
    }


# ---------------------------------------------------------------- data
def load() -> list[dict]:
    return [
        r
        for r in csv.DictReader(LABELS.open(encoding="utf-8"))
        if r["query"].strip() and r["score"].strip()
    ]


def train_ensemble(X, y) -> list:
    base = dict(
        objective="regression",
        n_estimators=400,
        learning_rate=0.05,
        num_leaves=31,
        colsample_bytree=0.8,
        subsample=0.8,
        verbose=-1,
    )
    ms = []
    for sd in ENSEMBLE_SEEDS:
        m = LGBMRegressor(random_state=sd, **base)
        m.fit(X, y)
        ms.append(m)
    return ms


def ens_predict(ms, X) -> np.ndarray:
    return np.clip(np.mean([m.predict(X) for m in ms], axis=0), 0, 10)


def calibrate(y, p, grid) -> tuple[tuple[float, float], float]:
    """Grid-search thresholds for exact-tier accuracy on the calibration batches."""
    best, best_acc = DEPLOYED_THR, -1.0
    for lo in grid:
        for hi in grid:
            if hi <= lo:
                continue
            acc = float(
                np.mean(
                    [
                        score_to_tier(a, (lo, hi)) == score_to_tier(b, (lo, hi))
                        for a, b in zip(y, p)
                    ]
                )
            )
            if acc > best_acc:
                best, best_acc = (lo, hi), acc
    return best, best_acc


# ---------------------------------------------------------------- main
def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = load()
    batches = sorted({r["batch"] for r in rows})
    rng = random.Random(SEED)
    order = rng.sample(batches, len(batches))
    n_tr, n_ca = 60, 14
    train_b, calib_b, test_b = set(order[:n_tr]), set(order[n_tr : n_tr + n_ca]), set(order[n_tr + n_ca :])

    def part(bs):
        sel = [r for r in rows if r["batch"] in bs]
        return (
            [r["query"] for r in sel],
            np.array([float(r["score"]) for r in sel], dtype=np.float32),
            sel,
        )

    qtr, ytr, _ = part(train_b)
    qca, yca, _ = part(calib_b)
    qte, yte, rte = part(test_b)

    print("== split by batch (near-duplicate leakage is contained) ==")
    print(f"  train {len(train_b):>3} batches {len(qtr):>6,} rows")
    print(f"  calib {len(calib_b):>3} batches {len(qca):>6,} rows")
    print(f"  test  {len(test_b):>3} batches {len(qte):>6,} rows")

    print("\n== training variants ==")
    fz = Featurizer(EMBED_DIR)
    Xca = fz.encode(qca)
    Xte = fz.encode(qte)

    def sub(bs, keep):
        return [r for r in rows if r["batch"] in bs and keep(r)]

    variants = {}
    for tag, keep, desc in [
        ("support_all", lambda r: True, "DS2 + DS3"),
        ("support_ds3", lambda r: r["source"] == "ds3_tobi_bueck", "real tickets only"),
    ]:
        rtr, rca, rte_v = sub(train_b, keep), sub(calib_b, keep), sub(test_b, keep)
        Xa = fz.encode([r["query"] for r in rtr])
        Xte_v = fz.encode([r["query"] for r in rte_v])
        ya = np.array([float(r["score"]) for r in rtr], dtype=np.float32)
        print(f"\n  {tag} ({desc}): {len(rtr):,} train rows")
        ms = train_ensemble(Xa, ya)
        pca = ens_predict(ms, Xca)
        pte = ens_predict(ms, Xte_v)
        thr, cal_acc = calibrate(yca, pca, [3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0])
        variants[tag] = {
            "models": ms,
            "thr": thr,
            "cal_acc": cal_acc,
            "n_train": len(rtr),
            "desc": desc,
            "p_test": pte,
            "y_test": np.array([float(r["score"]) for r in rte_v], dtype=np.float32),
            "rows_test": rte_v,
        }
        r_dep = evaluate(variants[tag]["y_test"], pte, DEPLOYED_THR)
        r_cal = evaluate(variants[tag]["y_test"], pte, thr)
        print(f"    calibrated thresholds: cheap<={thr[0]}  frontier>={thr[1]}  (calib tier acc {cal_acc:.1%})")
        print(f"    test @ deployed 4.5/6.0 : MAE {r_dep['mae']:.3f}  spearman {r_dep['spearman']:.3f}  tier {r_dep['tier_acc']:.1%}")
        print(f"    test @ calibrated      : MAE {r_cal['mae']:.3f}  spearman {r_cal['spearman']:.3f}  tier {r_cal['tier_acc']:.1%}")

    # secondary: the model that would run today if we shipped nothing
    print("\n== secondary reference: deployed generic model on these support rows ==")
    bundle = joblib.load(GENERIC)
    pg = np.clip(bundle["model"].predict(Xte), 0, 10)
    yg = np.array([float(r["score"]) for r in rte], dtype=np.float32)
    rg = evaluate(yg, pg, DEPLOYED_THR)
    print(f"  generic  : MAE {rg['mae']:.3f}  spearman {rg['spearman']:.3f}  tier {rg['tier_acc']:.1%}  under {rg['under']}/{rg['n_frontier']}")

    # ---- what happens to hard support queries ----
    print("\n== the 'system design asked in a support chatbot' check ==")
    ys = variants["support_all"]["y_test"]
    ps = variants["support_all"]["p_test"]
    thr = variants["support_all"]["thr"]
    hard = np.argsort(-ys)[:15]
    print(f"  15 hardest support tickets in the test batches (gold 8-10):")
    for i in hard:
        q = variants["support_all"]["rows_test"][int(i)]["query"]
        print(f"    gold {ys[i]:.0f} -> pred {ps[i]:5.2f}  {q[:72]!r}")

    # ---- report ----
    a = variants["support_all"]
    d = variants["support_ds3"]
    ra_dep = evaluate(a["y_test"], a["p_test"], DEPLOYED_THR)
    ra_cal = evaluate(a["y_test"], a["p_test"], a["thr"])
    rd_cal = evaluate(d["y_test"], d["p_test"], d["thr"])

    lines = [
        "# Customer-support difficulty model - held-out SUPPORT evaluation",
        "",
        f"Split is by batch ({len(train_b)}/{len(calib_b)}/{len(test_b)}) so near-duplicate "
        f"tickets cannot leak across the boundary. Thresholds calibrated on the calib batches only.",
        "",
        "## Test-batch results (support tickets only)",
        "",
        "| model | thresholds | MAE | Spearman | tier acc | frontier recall | under-routed |",
        "|---|---|---|---|---|---|---|",
        f"| support_all | deployed 4.5/6.0 | {ra_dep['mae']:.3f} | {ra_dep['spearman']:.3f} | {ra_dep['tier_acc']:.1%} | {ra_dep['recall'].get('frontier', (0,0))[0]:.1%} | {ra_dep['under']}/{ra_dep['n_frontier']} |",
        f"| support_all | calibrated {a['thr'][0]}/{a['thr'][1]} | {ra_cal['mae']:.3f} | {ra_cal['spearman']:.3f} | {ra_cal['tier_acc']:.1%} | {ra_cal['recall'].get('frontier', (0,0))[0]:.1%} | {ra_cal['under']}/{ra_cal['n_frontier']} |",
        f"| support_ds3 | calibrated {d['thr'][0]}/{d['thr'][1]} | {rd_cal['mae']:.3f} | {rd_cal['spearman']:.3f} | {rd_cal['tier_acc']:.1%} | {rd_cal['recall'].get('frontier', (0,0))[0]:.1%} | {rd_cal['under']}/{rd_cal['n_frontier']} |",
        f"| *generic (secondary)* | deployed 4.5/6.0 | {rg['mae']:.3f} | {rg['spearman']:.3f} | {rg['tier_acc']:.1%} | {rg['recall'].get('frontier', (0,0))[0]:.1%} | {rg['under']}/{rg['n_frontier']} |",
        "",
        "## Per-tier recall on test support tickets",
        "",
    ]
    for name, r, thr in [
        ("support_all (calibrated)", ra_cal, a["thr"]),
        ("support_ds3 (calibrated)", rd_cal, d["thr"]),
        ("generic (secondary)", rg, DEPLOYED_THR),
    ]:
        cells = "   ".join(
            f"{t} {r['recall'][t][0]:.1%} (n={r['recall'][t][1]})" for t in ("cheap", "mid", "frontier") if t in r["recall"]
        )
        lines.append(f"- **{name}**: {cells}")

    lines += [
        "",
        "## Score distribution on test support tickets",
        "",
        f"gold mean {float(np.mean(a['y_test'])):.2f}   predicted mean {float(np.mean(a['p_test'])):.2f}",
        "",
        "| gold score | rows | model predicts (mean) |",
        "|---|---|---|",
    ]
    for s in range(11):
        m = a["y_test"] == s
        if m.sum():
            lines.append(f"| {s} | {int(m.sum()):,} | {float(np.mean(a['p_test'][m])):.2f} |")

    lines += [
        "",
        "## Hardest test tickets (the 'system design in a support chatbot' risk)",
        "",
        "| gold | pred | tier | query |",
        "|---|---|---|---|",
    ]
    for i in hard:
        q = variants["support_all"]["rows_test"][int(i)]["query"].replace("|", "/")
        lines.append(f"| {ys[i]:.0f} | {ps[i]:.2f} | {score_to_tier(float(ps[i]), thr)} | {q[:80]} |")

    lines += [
        "",
        "## Reading this",
        "",
        "- Spearman and tier accuracy on these rows are the support model's real numbers. "
        "No cross-domain comparison is involved or meaningful.",
        "- The calibrated thresholds matter more than the model here: 4.5/6.0 were tuned on "
        "generic data, and the support score distribution is shifted well below it.",
        "- `support_ds3` vs `support_all` on the same split answers whether the DS2 synthetic "
        "rows help or dilute, on the data that actually matters.",
        "- Label noise sets a floor on MAE: an independent second labeler disagreed with Claude "
        "on 68% of 1,000 tickets (mean abs diff 1.34), so MAE below ~1.0 on this data is not "
        "attainable and should not be a target.",
        "",
        "## Not done",
        "",
        "- 2 of 90 reply files were rejected (batch_225 gave 209 lines, batch_238 gave 199), so "
        "400 of 18,000 labels are missing.",
        "- The remaining 148 batches are unlabeled. Whether to finish them is a separate call; "
        "this report does not assume it.",
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    for tag, v in variants.items():
        joblib.dump(
            {
                "models": v["models"],
                "seeds": list(ENSEMBLE_SEEDS),
                "feature_count": 388,
                "feature_order": "minilm384_then_handcrafted4",
                "embedder": str(EMBED_DIR),
                "thr": v["thr"],
                "calib_tier_acc": v["cal_acc"],
                "train_batches": sorted(train_b),
                "n_train": v["n_train"],
                "tag": tag,
                "source": "support",
            },
            OUT / f"{tag}.joblib",
        )
    print(f"\nwrote {REPORT}")
    print(f"wrote models to {OUT}")
    return 0


def _tr_rows(rows, bs):
    return [r for r in rows if r["batch"] in bs]


if __name__ == "__main__":
    raise SystemExit(main())
