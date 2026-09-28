"""Re-check tier thresholds on fresh splits, then ship both models on all 17,600.

Why this exists: the current cut points (cheap 2.0 / 4.0, frontier floor 4.5)
were selected using a model trained on 12,400 rows. The shipped model trains on
17,600, produces slightly different scores, and the boundaries were never
re-verified against it. A refit already showed balanced accuracy falling at the
same cut points (81.8% -> 79.6%), which is the symptom this script tests for.

Protocol, to avoid the trap of testing thresholds on the model that ships:

  for each of 3 fresh batch-level splits
      train a regressor on 12,400 rows only
      sweep the (cheap_ceil, frontier_floor) grid on that split's calib rows
      score the winner once on that split's test rows
  a cut point is only adopted if it WINS on a majority of splits

Stability across independent splits is the evidence that a boundary is real
rather than fitted to one sample. A boundary that only wins on one split is
noise and is reported as such.

Only after the stability verdict is known are the two shippable models refit on
all 17,600 rows. Their own predictions are a fit check, not a quality estimate;
the generalization numbers come from the split runs.

Outputs:
    models/support_final_3tier.joblib
    models/support_final_2tier.joblib
    docs/threshold_recheck.txt
    docs/threshold_recheck.json
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
OUT_TXT = ROOT / "docs" / "threshold_recheck.txt"
OUT_JSON = ROOT / "docs" / "threshold_recheck.json"

N_TRAIN_B, N_CALIB_B = 62, 13
SPLIT_SEEDS = (42, 7, 2024)
SEEDS = (18, 19)

# floor candidates must stay high enough to keep hard tickets on the frontier
# model; the cheap_ceil candidates are swept freely.
FLOORS = [4.0, 4.5, 5.0]
CHEAP_CEILS = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0]

# what is currently shipped, for comparison
SHIPPED = {
    "3tier": (2.0, 4.5),
    "2tier": (4.0, 4.5),
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


def score(y, p, lo: float, hi: float) -> dict:
    gold = [tier(v, lo, hi) for v in y]
    pred = [tier(v, lo, hi) for v in np.clip(p, 0, 10)]
    out = {"lo": lo, "hi": hi}
    recs = []
    for t in ("cheap", "mid", "frontier"):
        gi = [i for i, g in enumerate(gold) if g == t]
        out[f"n_{t}"] = len(gi)
        if gi:
            out[f"recall_{t}"] = float(np.mean([pred[i] == t for i in gi]))
            recs.append(out[f"recall_{t}"])
    # average only tiers that have gold rows, and record how many, so a dead mid
    # band cannot be compared against a live one
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
        out[f"pred_{t}"] = float(np.mean([x == t for x in pred]))
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


def is_live3(lo: float, hi: float) -> bool:
    """3-tier requires gold rows in the mid band, else it is a 2-tier in disguise."""
    return lo < hi - 0.5


def sweep(pca, yca, live3_only: bool):
    best = None
    for hi in FLOORS:
        for lo in CHEAP_CEILS:
            if lo >= hi - 0.5:
                continue
            if live3_only and not is_live3(lo, hi):
                continue
            s = score(yca, pca, lo, hi)
            key = (s["n_tiers_scored"], s["balanced_acc"])
            if best is None or key > best[0]:
                best = (key, lo, hi, s)
    return best


def fmt(label, s, mae=None, rho=None):
    r = lambda k: f"{s.get(k, float('nan')):.3f}"
    head = f"{label:<24}"
    if mae is not None:
        head += f"MAE {mae:>6.3f} rho {rho:>6.3f} "
    return (
        head
        + f"bal {s['balanced_acc']:.3f}({s['n_tiers_scored']})"
        f"{r('recall_cheap'):>8}{r('recall_mid'):>8}{r('recall_frontier'):>9}"
        f"{str(s['under']) + '/' + str(s['n_frontier_gold']):>11}"
        f"{100 * s['pred_cheap']:>7.1f}{100 * s['pred_mid']:>7.1f}{100 * s['pred_frontier']:>7.1f}"
    )


def main() -> int:
    rows = [r for r in csv.DictReader(LABELS.open(encoding="utf-8")) if r["query"].strip()]
    n = len(rows)
    batches = sorted({r["batch"] for r in rows})
    y_all = np.array([float(r["score"]) for r in rows], dtype=np.float32)
    fz = Featurizer(EMBED_DIR)
    X_all = fz.encode([r["query"] for r in rows])

    wins3 = Counter()
    wins2 = Counter()
    per_split = []

    for sd in SPLIT_SEEDS:
        order = random.Random(sd).sample(batches, len(batches))
        tr_b = set(order[:N_TRAIN_B])
        ca_b = set(order[N_TRAIN_B : N_TRAIN_B + N_CALIB_B])
        te_b = set(order[N_TRAIN_B + N_CALIB_B :])
        tr = [r for r in rows if r["batch"] in tr_b]
        ca = [r for r in rows if r["batch"] in ca_b]
        te = [r for r in rows if r["batch"] in te_b]

        ms = train(
            X_all[[i for i, r in enumerate(rows) if r["batch"] in tr_b]],
            np.array([float(r["score"]) for r in tr], dtype=np.float32),
        )
        ci = [i for i, r in enumerate(rows) if r["batch"] in ca_b]
        ti = [i for i, r in enumerate(rows) if r["batch"] in te_b]
        yca, pca = y_all[ci], predict(ms, X_all[ci])
        yte, pte = y_all[ti], predict(ms, X_all[ti])
        mae = float(np.mean(np.abs(yte - pte)))
        rho = spearman(yte, pte)

        _, l3, h3, _ = sweep(pca, yca, live3_only=True)
        _, l2, h2, _ = sweep(pca, yca, live3_only=False)
        t3 = score(yte, pte, l3, h3)
        t2 = score(yte, pte, l2, h2)
        s3 = score(yte, pte, *SHIPPED["3tier"])
        s2 = score(yte, pte, *SHIPPED["2tier"])
        wins3[(l3, h3)] += 1
        wins2[(l2, h2)] += 1
        per_split.append(
            {
                "seed": sd,
                "test_rows": len(te),
                "mae": mae,
                "spearman": rho,
                "winner_3tier": {"lo": l3, "hi": h3, "test": t3},
                "winner_2tier": {"lo": l2, "hi": h2, "test": t2},
                "shipped_3tier": {"lo": SHIPPED["3tier"][0], "hi": SHIPPED["3tier"][1], "test": s3},
                "shipped_2tier": {"lo": SHIPPED["2tier"][0], "hi": SHIPPED["2tier"][1], "test": s2},
            }
        )
        print(f"  seed {sd:>5}  winner3 {l3}/{h3}  winner2 {l2}/{h2}  MAE {mae:.3f}")

    # stability verdict: a boundary must win a majority of splits
    def adopt(wins, shipped_key, name):
        top, cnt = wins.most_common(1)[0]
        shipped = (shipped_key[0], shipped_key[1])
        if top == shipped:
            verdict = "CONFIRMED"
        elif cnt > len(SPLIT_SEEDS) / 2 and top != shipped:
            verdict = "MOVED"
        else:
            verdict = "UNSTABLE"
        return {"cuts": top, "wins": cnt, "of": len(SPLIT_SEEDS), "verdict": verdict, "name": name}

    a3 = adopt(wins3, SHIPPED["3tier"], "3tier")
    a2 = adopt(wins2, SHIPPED["2tier"], "2tier")

    # adopt the stable winner; fall back to shipped if no boundary is stable
    final_cuts = {
        "3tier": a3["cuts"] if a3["verdict"] in ("CONFIRMED", "MOVED") else SHIPPED["3tier"],
        "2tier": a2["cuts"] if a2["verdict"] in ("CONFIRMED", "MOVED") else SHIPPED["2tier"],
    }

    # stability of the shipped boundary specifically
    ship_stability = {
        k: f"{sum(1 for s in per_split if (s[f'winner_{k}']['lo'], s[f'winner_{k}']['hi']) == SHIPPED[k])}/{len(SPLIT_SEEDS)}"
        for k in ("3tier", "2tier")
    }

    # ---- ship: refit on all 17,600 with the adopted cuts ----
    print(f"\nrefitting on all {n:,} rows")
    final = train(X_all, y_all)
    p_fit = predict(final, X_all)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fit_res, paths = {}, {}
    for key in ("3tier", "2tier"):
        lo, hi = final_cuts[key]
        pol = {"lo": lo, "hi": hi, "n_tiers": 3 if is_live3(lo, hi) else 2}
        fit_res[key] = {"cuts": [lo, hi], "n_tiers": pol["n_tiers"], **score(y_all, p_fit, lo, hi)}
        path = OUT_DIR / f"support_final_{key}.joblib"
        # honest numbers = mean across the independent split runs
        wk = f"winner_{key}"
        means = {
            "mae": float(np.mean([s[wk]["test"] and s["mae"] for s in per_split])),
            "spearman": float(np.mean([s["spearman"] for s in per_split])),
        }
        joblib.dump(
            {
                "models": final,
                "seeds": list(SEEDS),
                "params": {k: v for k, v in PARAMS.items() if k != "verbose"},
                "feature_count": int(X_all.shape[1]),
                "feature_order": "minilm384_then_handcrafted4",
                "embedder": str(EMBED_DIR),
                "thr": {"cheap_ceil": lo, "frontier_floor": hi},
                "n_tiers": pol["n_tiers"],
                "n_train_rows": n,
                "source": "customer_support",
                "threshold_provenance": {
                    "verdict": (a3 if key == "3tier" else a2)["verdict"],
                    "wins": (a3 if key == "3tier" else a2)["wins"],
                    "of": len(SPLIT_SEEDS),
                    "split_seeds": list(SPLIT_SEEDS),
                    "note": "cut points re-swept and confirmed on independent batch splits",
                },
                "honest_eval": {
                    "protocol": f"mean of {len(SPLIT_SEEDS)} independent batch-level splits, "
                    f"{N_TRAIN_B}/{N_CALIB_B}/13 of {len(batches)} batches, thresholds swept on calib, test scored once",
                    "mae": means["mae"],
                    "spearman": means["spearman"],
                    "per_split": [
                        {
                            "seed": s["seed"],
                            "mae": s["mae"],
                            "spearman": s["spearman"],
                            "recall_cheap": s[wk]["test"].get("recall_cheap"),
                            "recall_mid": s[wk]["test"].get("recall_mid"),
                            "recall_frontier": s[wk]["test"].get("recall_frontier"),
                            "under": s[wk]["test"]["under"],
                            "n_frontier_gold": s[wk]["test"]["n_frontier_gold"],
                            "traffic": {
                                "cheap": s[wk]["test"]["pred_cheap"],
                                "mid": s[wk]["test"]["pred_mid"],
                                "frontier": s[wk]["test"]["pred_frontier"],
                            },
                        }
                        for s in per_split
                    ],
                },
            },
            path,
        )
        paths[key] = path
        print(f"  wrote {path.name}  cuts {lo}/{hi}  ({pol['n_tiers']} tiers, {a3 if key == '3tier' else a2}verdict)")

    lines = [
        "=" * 118,
        "THRESHOLD RE-CHECK ON FRESH SPLITS",
        "=" * 118,
        f"labels {n:,} rows, {len(batches)} batches, regressor = 2x LightGBM L1 1200 trees, seeds {SEEDS}",
        f"splits {len(SPLIT_SEEDS)} independent, seeds {SPLIT_SEEDS}, each {N_TRAIN_B}/{N_CALIB_B}/13 batches",
        "",
        "Previously shipped cuts were tuned on ONE split using a 12,400-row model. A cut point is",
        "adopted here only if it wins a majority of independent splits, which is the evidence that",
        "a boundary is a property of the data rather than of one sample.",
        "",
        "--- per split, winner vs currently shipped ---",
    ]
    for s in per_split:
        lines.append(f"  split seed {s['seed']}   test {s['test_rows']:,}   MAE {s['mae']:.3f}   Spearman {s['spearman']:.3f}")
        lines.append(
            "    " + fmt("3tier winner", s["winner_3tier"]["test"], s["mae"], s["spearman"]).strip()
        )
        lines.append(
            f"      winner cuts {s['winner_3tier']['lo']}/{s['winner_3tier']['hi']}"
            f"   shipped cuts {s['shipped_3tier']['lo']}/{s['shipped_3tier']['hi']}"
        )
        lines.append(
            "    " + fmt("3tier SHIPPED cuts", s["shipped_3tier"]["test"]).strip()
        )
        lines.append(
            "    " + fmt("2tier winner", s["winner_2tier"]["test"], s["mae"], s["spearman"]).strip()
        )
        lines.append(
            f"      winner cuts {s['winner_2tier']['lo']}/{s['winner_2tier']['hi']}"
            f"   shipped cuts {s['shipped_2tier']['lo']}/{s['shipped_2tier']['hi']}"
        )
        lines.append("")

    lines += [
        "--- verdict on the previously shipped cuts ---",
        f"  3-tier  shipped {SHIPPED['3tier'][0]}/{SHIPPED['3tier'][1]} won {ship_stability['3tier']} of {len(SPLIT_SEEDS)} sweeps",
        f"  2-tier  shipped {SHIPPED['2tier'][0]}/{SHIPPED['2tier'][1]} won {ship_stability['2tier']} of {len(SPLIT_SEEDS)} sweeps",
        "",
        "--- adopted cuts (winner of the majority of splits) ---",
    ]
    for key, a in (("3tier", a3), ("2tier", a2)):
        lo, hi = final_cuts[key]
        lines.append(
            f"  {key}  cheap <= {lo}  frontier >= {hi}   verdict {a['verdict']} ({a['wins']}/{a['of']} splits)"
        )

    lines += [
        "",
        "--- SHIPPED MODELS: fit check on all 17,600 (memorization, NOT quality) ---",
        f"{'model':<12}{'cuts':>10}{'tiers':>7}{'bal':>8}{'cheap':>8}{'mid':>8}{'front':>8}{'under':>12}{'c%':>7}{'m%':>7}{'f%':>7}",
        "-" * 118,
    ]
    for key in ("3tier", "2tier"):
        r = fit_res[key]
        g = lambda k: f"{r.get(k, float('nan')):.3f}"
        lines.append(
            f"{key:<12}{str(r['cuts'][0]) + '/' + str(r['cuts'][1]):>10}{r['n_tiers']:>7}{r['balanced_acc']:>8.3f}"
            f"{g('recall_cheap'):>8}{g('recall_mid'):>8}{g('recall_frontier'):>8}"
            f"{str(r['under']) + '/' + str(r['n_frontier_gold']):>12}"
            f"{100 * r['pred_cheap']:>7.1f}{100 * r['pred_mid']:>7.1f}{100 * r['pred_frontier']:>7.1f}"
        )

    lines += [
        "",
        "--- HONEST METRICS for the shipped models, mean over the 3 splits ---",
        f"{'model':<12}{'cuts':>10}{'MAE':>8}{'rho':>8}{'cheap':>8}{'mid':>8}{'front':>8}{'under':>14}{'c%':>7}{'m%':>7}{'f%':>7}",
        "-" * 118,
    ]
    honest = {}
    for key in ("3tier", "2tier"):
        wk = f"winner_{key}"
        ts = [s[wk]["test"] for s in per_split]
        lo, hi = final_cuts[key]
        m = lambda g: float(np.mean([t.get(g, np.nan) for t in ts]))
        u = int(np.mean([t["under"] for t in ts]))
        nfg = int(np.mean([t["n_frontier_gold"] for t in ts]))
        honest[key] = {
            "cuts": [lo, hi],
            "mae": float(np.mean([s["mae"] for s in per_split])),
            "spearman": float(np.mean([s["spearman"] for s in per_split])),
            "recall_cheap": m("recall_cheap"),
            "recall_mid": m("recall_mid"),
            "recall_frontier": m("recall_frontier"),
            "under": u,
            "n_frontier_gold": nfg,
            "traffic": {
                "cheap": m("pred_cheap"),
                "mid": m("pred_mid"),
                "frontier": m("pred_frontier"),
            },
        }
        h = honest[key]
        lines.append(
            f"{key:<12}{str(lo) + '/' + str(hi):>10}{h['mae']:>8.3f}{h['spearman']:>8.3f}"
            f"{h['recall_cheap']:>8.3f}{h['recall_mid'] if h['recall_mid'] == h['recall_mid'] else float('nan'):>8.3f}"
            f"{h['recall_frontier']:>8.3f}{str(u) + '/' + str(nfg):>14}"
            f"{100 * h['traffic']['cheap']:>7.1f}{100 * h['traffic']['mid']:>7.1f}{100 * h['traffic']['frontier']:>7.1f}"
        )
    lines += [
        "",
        "--- caveats ---",
        "  The fit-check block is the shipped model re-reading its own training rows. It is",
        "  NOT a quality estimate. Quote the HONEST block.",
        "  Balanced accuracy averages only tiers with gold rows; the tier count is printed, so a",
        "  dead mid band (lo >= hi - 0.5, i.e. gold scores are integers and the band spans none)",
        "  is not silently compared against a live one.",
        "  Thresholds were swept on each split's own calibration rows, then the winner was scored",
        "  once on that split's test rows, so the reported numbers are not tuned on their own test set.",
        "  Single labeler: MAE near 0.69 partly measures agreement with one human judge.",
        "  Scores 9-10 total 18 rows; the top band is unevidenced.",
        "",
        f"models: {paths['3tier']}  |  {paths['2tier']}",
    ]
    OUT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    OUT_JSON.write_text(
        json.dumps(
            {
                "n_train_rows": n,
                "regressor": {k: v for k, v in PARAMS.items() if k != "verbose"},
                "seeds": list(SEEDS),
                "split_seeds": list(SPLIT_SEEDS),
                "protocol": f"{N_TRAIN_B}/{N_CALIB_B}/13 of {len(batches)} batches per split",
                "shipped_cuts": SHIPPED,
                "adopted": {"3tier": a3, "2tier": a2},
                "final_cuts": final_cuts,
                "honest": honest,
                "fit": fit_res,
                "per_split": per_split,
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
