"""Should domain move the cut points, or should it be added to the score?

Three candidate fixes for the same problem: technical tickets are harder than
billing tickets at the same predicted score.

  A. baseline        global thresholds 2.0 / 5.0, domain ignored
  B. score bump      add an offset to the predicted score for one domain,
                     then apply the same global thresholds (the user's idea)
  C. per-domain thr  same score, but each domain gets its own cut points

B is simpler to explain but distorts the score, and it can double-count: the
model already reads the ticket text, so domain may already be partly encoded
in the prediction. That is checked first.

C is more flexible but fits 8 numbers on the calibration batches, so it can
overfit. Everything is tuned on calib and scored once on test.

Outputs:
    docs/domain_thresholds.txt
    docs/domain_thresholds_best.json
"""

from __future__ import annotations

import csv
import json
import random
import re
from pathlib import Path

import joblib
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
LABELS = ROOT / "data" / "labeled" / "labeled_support.csv"
EMBED_DIR = Path(__file__).resolve().parents[2] / "backend" / "models" / "minilm"
OUT_TXT = ROOT / "docs" / "domain_thresholds.txt"
OUT_JSON = ROOT / "docs" / "domain_thresholds_best.json"

SEED = 42
N_TRAIN_B, N_CALIB_B = 62, 13
BASE_LO, BASE_HI = 2.0, 5.0
BUMP_GRID = [0.0, 0.5, 1.0, 1.5, 2.0, 3.0]
LO_GRID = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
HI_GRID = [4.0, 4.5, 5.0, 5.5, 6.0, 6.5]


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


def score(y, p, dom, cuts) -> dict:
    """cuts maps domain -> (lo, hi); a domain may also be absent for a uniform run."""
    def cut_for(d):
        return cuts.get(d, (BASE_LO, BASE_HI))

    gold = [tier(v, *cut_for(d)) for v, d in zip(y, dom)]
    pred = [tier(v, *cut_for(d)) for v, d in zip(np.clip(p, 0, 10), dom)]
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
    fi = [i for i, g in enumerate(gold) if g == "frontier"]
    out["under"] = int(sum(1 for i in fi if pred[i] != "frontier"))
    return out


def main() -> int:
    rows = [r for r in csv.DictReader(LABELS.open(encoding="utf-8")) if r["query"].strip()]
    batches = sorted({r["batch"] for r in rows})
    order = random.Random(SEED).sample(batches, len(batches))
    tr_b = set(order[:N_TRAIN_B])
    ca_b = set(order[N_TRAIN_B : N_TRAIN_B + N_CALIB_B])
    te_b = set(order[N_TRAIN_B + N_CALIB_B :])
    tr = [r for r in rows if r["batch"] in tr_b]
    ca = [r for r in rows if r["batch"] in ca_b]
    te = [r for r in rows if r["batch"] in te_b]

    # identical protocol to the final trainer so numbers are comparable
    params = dict(
        objective="regression_l1",
        n_estimators=1200,
        learning_rate=0.02,
        num_leaves=31,
        colsample_bytree=0.8,
        subsample=0.8,
        verbose=-1,
    )
    from lightgbm import LGBMRegressor

    fz = Featurizer(EMBED_DIR)
    Xtr = fz.encode([r["query"] for r in tr])
    ytr = np.array([float(r["score"]) for r in tr], dtype=np.float32)
    ms = []
    for sd in (18, 19):
        m = LGBMRegressor(random_state=sd, **params)
        m.fit(Xtr, ytr)
        ms.append(m)

    def pred_of(rs):
        return np.clip(np.mean([m.predict(fz.encode([r["query"] for r in rs])) for m in ms], axis=0), 0, 10)

    y_ca = np.array([float(r["score"]) for r in ca], dtype=np.float32)
    y_te = np.array([float(r["score"]) for r in te], dtype=np.float32)
    p_ca, p_te = pred_of(ca), pred_of(te)
    d_ca = [r["domain"] for r in ca]
    d_te = [r["domain"] for r in te]

    lines = [
        "DOMAIN-AWARE ROUTING: three fixes, one comparison",
        "=" * 92,
        "A  global thresholds 2.0 / 5.0, domain ignored",
        "B  add a per-domain offset to the score, same thresholds",
        "C  same score, per-domain thresholds",
        "",
        "--- does the model already know the domain? ---",
        "If mean predicted score already tracks mean gold score by domain, the",
        "text features have absorbed most of the signal and a bump double-counts it.",
        "",
        f"{'domain':<20}{'n':>7}{'gold_mean':>11}{'pred_mean':>11}{'gap':>8}",
        "-" * 92,
    ]
    doms = sorted(set(d_ca))
    for d in doms:
        idx = [i for i, x in enumerate(d_ca) if x == d]
        gm = float(np.mean(y_ca[idx]))
        pm = float(np.mean(p_ca[idx]))
        lines.append(f"{d:<20}{len(idx):>7}{gm:>11.2f}{pm:>11.2f}{pm - gm:>8.2f}")
    if hasattr(joblib, "__doc__") and (ROOT / "models" / "support_final.joblib").exists():
        lines.append("")

    # ---- B: score bump ----
    bump_ca, bump_te = [], []
    mask_ca = {d: np.array([x == d for x in d_ca]) for d in doms}
    mask_te = {d: np.array([x == d for x in d_te]) for d in doms}
    for bd in doms:
        best = None
        for b in BUMP_GRID:
            adj = p_ca + b * mask_ca[bd]
            s = score(y_ca, adj, d_ca, {})
            if best is None or s["balanced_acc"] > best[1]["balanced_acc"]:
                best = (b, s)
        bump_ca.append(best)
        bump_te.append(score(y_te, p_te + best[0] * mask_te[bd], d_te, {}))

    # ---- C: per-domain thresholds ----
    dom_ca, dom_te = [], []
    for d in doms:
        idx = np.array([i for i, x in enumerate(d_ca) if x == d])
        best = None
        for lo in LO_GRID:
            for hi in HI_GRID:
                if hi <= lo + 0.5:
                    continue
                s = score(y_ca[idx], p_ca[idx], [d] * len(idx), {d: (lo, hi)})
                if best is None or s["balanced_acc"] > best[2]["balanced_acc"]:
                    best = (lo, hi, s)
        dom_ca.append(best)
        tid = np.array([i for i, x in enumerate(d_te) if x == d])
        dom_te.append(score(y_te[tid], p_te[tid], [d] * len(tid), {d: (best[0], best[1])}))

    base_ca = score(y_ca, p_ca, d_ca, {})
    base_te = score(y_te, p_te, d_te, {})

    lines += [
        "",
        "--- A: global 2.0 / 5.0 (baseline) ---",
        f"  calib   balanced {base_ca['balanced_acc']:.3f}  cheap {base_ca.get('recall_cheap', 0):.3f}  mid {base_ca.get('recall_mid', 0):.3f}  front {base_ca.get('recall_frontier', 0):.3f}",
        f"  TEST    balanced {base_te['balanced_acc']:.3f}  cheap {base_te.get('recall_cheap', 0):.3f}  mid {base_te.get('recall_mid', 0):.3f}  front {base_te.get('recall_frontier', 0):.3f}   under {base_te['under']}/{base_te['n_frontier']}",
        "",
        "--- B: per-domain score bump (tuned on calib) ---",
    ]
    for (b, s), d in zip(bump_ca, doms):
        lines.append(f"  {d:<20} bump +{b:.1f}  calib balanced {s['balanced_acc']:.3f}")
    lines.append("")

    for d, s in zip(doms, bump_te):
        lines.append(
            f"  TEST {d:<20} cheap {s.get('recall_cheap', 0):.3f}  mid {s.get('recall_mid', 0):.3f}  front {s.get('recall_frontier', 0):.3f}  under {s['under']}/{s['n_frontier']}"
        )

    lines += ["", "--- C: per-domain thresholds (tuned on calib) ---"]
    for (lo, hi, _), d in zip(dom_ca, doms):
        lines.append(f"  {d:<20} cheap <= {lo}, frontier >= {hi}")
    lines.append("")
    for d, s in zip(doms, dom_te):
        lines.append(
            f"  TEST {d:<20} cheap {s.get('recall_cheap', 0):.3f}  mid {s.get('recall_mid', 0):.3f}  front {s.get('recall_frontier', 0):.3f}  under {s['under']}/{s['n_frontier']}"
        )

    # pooled B and C on the full test set
    bumps = {d: b for (b, _), d in zip(bump_ca, doms)}
    adj_ca = np.array([p_ca[i] + bumps.get(d_ca[i], 0.0) for i in range(len(p_ca))])
    adj_te = np.array([p_te[i] + bumps.get(d_te[i], 0.0) for i in range(len(p_te))])
    pool_b_ca = score(y_ca, adj_ca, d_ca, {})
    pool_b_te = score(y_te, adj_te, d_te, {})
    cuts = {d: (lo, hi) for (lo, hi, _), d in zip(dom_ca, doms)}
    pool_c_ca = score(y_ca, p_ca, d_ca, cuts)
    pool_c_te = score(y_te, p_te, d_te, cuts)

    lines += [
        "",
        "--- POOLED on all test rows (the comparison that matters) ---",
        f"{'variant':<26}{'bal_acc':>9}{'cheap':>8}{'mid':>8}{'front':>8}{'under':>12}{'tier_acc':>10}",
        "-" * 92,
    ]
    for lab, s in [("A global 2.0/5.0", base_te), ("B per-domain bump", pool_b_te), ("C per-domain thresholds", pool_c_te)]:
        lines.append(
            f"{lab:<26}{s['balanced_acc']:>9.3f}{s.get('recall_cheap', 0):>8.3f}{s.get('recall_mid', 0):>8.3f}"
            f"{s.get('recall_frontier', 0):>8.3f}{str(s['under']) + '/' + str(s['n_frontier']):>12}{s['tier_acc']:>10.3f}"
        )
    best_name, best_te = max(
        [("A global", base_te), ("B bump", pool_b_te), ("C per-domain", pool_c_te)],
        key=lambda kv: kv[1]["balanced_acc"],
    )
    lines += [
        "",
        f"best on test by balanced accuracy: {best_name}  ({best_te['balanced_acc']:.3f})",
        f"baseline for reference:          A global  ({base_te['balanced_acc']:.3f})",
        "",
        "--- caveat ---",
        "Per-domain thresholds are 8 numbers fitted on 2,600 calibration rows, so the",
        "calib-to-test drop is the honest signal of whether it generalizes. Read the",
        "TEST pooled row, not the calib-per-domain rows.",
    ]
    OUT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    OUT_JSON.write_text(
        json.dumps(
            {
                "baseline": {"balanced_acc": base_te["balanced_acc"], "under": base_te["under"]},
                "bump": {"bumps": bumps, "balanced_acc": pool_b_te["balanced_acc"], "under": pool_b_te["under"]},
                "per_domain": {"cuts": cuts, "balanced_acc": pool_c_te["balanced_acc"], "under": pool_c_te["under"]},
                "best": best_name,
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
