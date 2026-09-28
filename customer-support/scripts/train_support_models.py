"""Train support-specific difficulty regressors and compare against the deployed model.

Three runs, all evaluated on the SAME 783-row held-out set so the comparison is
honest and directly comparable to the deployed model's published numbers
(MAE 1.018 / Spearman 0.861 / tier acc 77.5%).

  generic      backend/models/difficulty_regressor.joblib (v20_ensemble_v18_v19),
               trained on the 8,000 gold rows with in_train==1. NOT retrained.
  support_all  every support label (DS2 synthetic + DS3 real)
  support_ds3  real tickets only, to test whether DS2 dilutes the model

The 783 held-out rows are recovered from the old work folder, not the repo:
the repo's copy of gold v7 dropped the `in_train` column that defines the
split. `in_train==0` there yields exactly 783 rows, matching the deployed
bundle's eval_note ("held-out = v4 783 rows").

Feature order is copied from backend/src/predict_difficulty.py: MiniLM 384-dim
embedding THEN the 4 handcrafted features (388 total). The 845 MB embedder is
loaded in place from the repo and is never copied.

A hard self-check runs first: if the featurization is wrong, the generic model
will not reproduce its own published metrics, and the script aborts rather than
reporting a comparison built on a mismatch.

Nothing is written into the llm-router git repo. Models go to models/.
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
OLD = Path(r"D:\llm-router-ml-upgrade")

LABELS = CS / "data" / "labeled" / "labeled_support.csv"
OLD_V7 = OLD / "data" / "gold_v2" / "gold_labeled_queries_v7.csv"
GENERIC = REPO / "backend" / "models" / "difficulty_regressor.joblib"
EMBED_DIR = REPO / "backend" / "models" / "minilm"
OUT = CS / "models"
REPORT = CS / "docs" / "train_report.md"

# The deployed model's own recorded metrics. Used as the featurization self-check.
DEPLOYED = {"mae": 1.018, "spearman": 0.861, "tier_acc": 0.775}
SELFCHECK_TOL = 0.06

HELD_OUT_N = 783
DEPLOYED_THR = (4.5, 6.0)
TRAIN_FRAC = 0.8
SEED = 42
ENSEMBLE_SEEDS = (18, 19)  # mirrors the deployed v18+v19 pairing

sys.path.insert(0, str(REPO / "backend" / "src"))


# ---------------------------------------------------------------- features
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


# ---------------------------------------------------------------- metrics
def score_to_tier(score: float, thr: tuple[float, float] = DEPLOYED_THR) -> str:
    if score <= thr[0]:
        return "cheap"
    if score >= thr[1]:
        return "frontier"
    return "mid"


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    def rank(x: np.ndarray) -> np.ndarray:
        order = np.argsort(x, kind="mergesort")
        r = np.empty(len(x), dtype=np.float64)
        r[order] = np.arange(1, len(x) + 1)
        _, inv, cnt = np.unique(x, return_inverse=True, return_counts=True)
        sums = np.zeros(len(cnt), dtype=np.float64)
        np.add.at(sums, inv, r)
        return (sums / cnt)[inv]

    ra, rb = rank(np.asarray(a, float)), rank(np.asarray(b, float))
    ra -= ra.mean()
    rb -= rb.mean()
    den = float(np.sqrt((ra**2).sum() * (rb**2).sum()))
    return float((ra * rb).sum() / den) if den else 0.0


def evaluate(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    y_true = np.asarray(y_true, float)
    y_pred = np.clip(np.asarray(y_pred, float), 0, 10)
    t_true = [score_to_tier(v) for v in y_true]
    t_pred = [score_to_tier(v) for v in y_pred]
    recall = {}
    for tier in ("cheap", "mid", "frontier"):
        mask = [i for i, t in enumerate(t_true) if t == tier]
        if mask:
            recall[tier] = float(np.mean([t_pred[i] == tier for i in mask]))
    return {
        "mae": float(np.mean(np.abs(y_true - y_pred))),
        "spearman": spearman(y_true, y_pred),
        "tier_acc": float(np.mean([a == b for a, b in zip(t_true, t_pred)])),
        "recall": recall,
        "under_routed": int(sum(1 for a, b in zip(t_true, t_pred) if a == "frontier" and b != "frontier")),
        "over_routed": int(sum(1 for a, b in zip(t_true, t_pred) if a != "frontier" and b == "frontier")),
        "n_true_frontier": t_true.count("frontier"),
    }


# ---------------------------------------------------------------- data
def load_support() -> tuple[list[str], np.ndarray, list[dict[str, str]]]:
    rows = [r for r in csv.DictReader(LABELS.open(encoding="utf-8")) if r["query"].strip()]
    return (
        [r["query"] for r in rows],
        np.array([float(r["score"]) for r in rows], dtype=np.float32),
        rows,
    )


def load_held_out() -> tuple[list[str], np.ndarray, dict]:
    """Recover the exact 783-row v4 held-out split via the old folder's in_train flag."""
    if not OLD_V7.exists():
        raise SystemExit(f"cannot recover the held-out split: {OLD_V7} is missing")
    rows = list(csv.DictReader(OLD_V7.open(encoding="utf-8-sig")))
    if "in_train" not in rows[0]:
        raise SystemExit(f"{OLD_V7} has no in_train column; split is unrecoverable")
    n_train = sum(1 for r in rows if str(r["in_train"]).strip() == "1")
    held = [
        r
        for r in rows
        if str(r["in_train"]).strip() == "0" and r["query"].strip() and r["gold_score"].strip()
    ]
    meta = {
        "gold_v7_total": len(rows),
        "generic_train_rows": n_train,
        "held_out": len(held),
        "gold_version": "v7",
    }
    if len(held) != HELD_OUT_N:
        raise SystemExit(f"expected {HELD_OUT_N} held-out rows, recovered {len(held)}")
    return (
        [r["query"] for r in held],
        np.array([float(r["gold_score"]) for r in held], dtype=np.float32),
        meta,
    )


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


# ---------------------------------------------------------------- training
def train_ensemble(X: np.ndarray, y: np.ndarray, tag: str) -> list:
    base = dict(
        objective="regression",
        n_estimators=400,
        learning_rate=0.05,
        num_leaves=31,
        colsample_bytree=0.8,
        subsample=0.8,
        verbose=-1,
    )
    models = []
    for sd in ENSEMBLE_SEEDS:
        m = LGBMRegressor(random_state=sd, **base)
        m.fit(X, y)
        models.append(m)
    return models


def ensemble_predict(models: list, X: np.ndarray) -> np.ndarray:
    return np.clip(np.mean([m.predict(X) for m in models], axis=0), 0, 10)


# ---------------------------------------------------------------- main
def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)

    print("== loading ==")
    sq, sy, srows = load_support()
    hq, hy, meta = load_held_out()
    print(f"  support labels : {len(sq):,}")
    print(f"  gold v7        : {meta['gold_v7_total']:,}  (generic trained on {meta['generic_train_rows']:,})")
    print(f"  held-out       : {len(hq):,}  <- exact v4 split, in_train==0")

    print("\n  support label makeup")
    for k, v in Counter(r["source"] for r in srows).most_common():
        print(f"    {k:<18} {v:>6,}")
    for k, v in Counter(r["domain"] for r in srows).most_common():
        print(f"    {k:<18} {v:>6,}")

    # ---- leakage checks ----
    print("\n== leakage checks ==")
    held_norm = {norm(q) for q in hq}
    support_norm = {norm(q) for q in sq}
    overlap = held_norm & support_norm
    print(f"  support vs held-out overlap : {len(overlap)} rows")
    if overlap:
        print("  -> dropping held-out rows that appear in the support training data")
        keep = [i for i, q in enumerate(hq) if norm(q) not in support_norm]
        hq = [hq[i] for i in keep]
        hy = hy[keep]
        print(f"  held-out after filter: {len(hq):,}")
    if not hq:
        raise SystemExit("held-out set is empty after leakage filtering")

    print("\n== featurizing (MiniLM 384 + 4 = 388) ==")
    fz = Featurizer(EMBED_DIR)
    Xh = fz.encode(hq)
    Xs = fz.encode(sq)
    print(f"  held-out {Xh.shape}   support {Xs.shape}")

    results = []

    # ---- run 1: deployed generic, with self-check ----
    print("\n== run 1/3: generic (deployed bundle, not retrained) ==")
    bundle = joblib.load(GENERIC)
    gp = np.clip(bundle["model"].predict(Xh), 0, 10)
    r1 = evaluate(hy, gp)
    r1.update(
        name="generic (deployed)",
        train_n=meta["generic_train_rows"],
        note="v20_ensemble_v18_v19, 8,000 gold labels, in_train==1",
    )
    results.append(r1)
    print(f"  MAE {r1['mae']:.3f}  spearman {r1['spearman']:.3f}  tier_acc {r1['tier_acc']:.1%}")
    print(f"  bundle says: MAE {DEPLOYED['mae']}  spearman {DEPLOYED['spearman']}  tier_acc {DEPLOYED['tier_acc']:.3f}")
    drift = max(
        abs(r1["mae"] - DEPLOYED["mae"]),
        abs(r1["spearman"] - DEPLOYED["spearman"]),
        abs(r1["tier_acc"] - DEPLOYED["tier_acc"]),
    )
    if drift > SELFCHECK_TOL:
        raise SystemExit(
            f"\nABORT: featurization does not reproduce the deployed model's own metrics "
            f"(max drift {drift:.3f} > {SELFCHECK_TOL}).\n"
            f"Fix feature order/scaling before trusting any comparison in this report."
        )
    print(f"  self-check PASSED (max drift {drift:.4f})")

    # ---- runs 2 and 3 ----
    for tag, keep_fn, desc in [
        ("support_all", lambda r: True, "all support labels (DS2 + DS3)"),
        ("support_ds3", lambda r: r["source"] == "ds3_tobi_bueck", "real tickets only (DS3)"),
    ]:
        idx = [i for i, r in enumerate(srows) if keep_fn(r)]
        X, y = Xs[idx], sy[idx]
        n = len(idx)
        cut = int(TRAIN_FRAC * n)
        perm = rng.sample(range(n), n)
        tr, te = perm[:cut], perm[cut:]

        print(f"\n== run {'2/3' if tag == 'support_all' else '3/3'}: {tag} ==")
        print(f"  {n:,} rows -> {len(tr):,} train / {len(te):,} internal test  ({desc})")
        models = train_ensemble(X[tr], y[tr], tag)

        internal = evaluate(y[te], ensemble_predict(models, X[te]))
        print(
            f"  internal : MAE {internal['mae']:.3f}  spearman {internal['spearman']:.3f}  "
            f"tier_acc {internal['tier_acc']:.1%}"
        )

        hp = ensemble_predict(models, Xh)
        hr = evaluate(hy, hp)
        hr.update(name=tag, train_n=len(tr), note=desc, internal=internal)
        results.append(hr)
        print(f"  held-out : MAE {hr['mae']:.3f}  spearman {hr['spearman']:.3f}  tier_acc {hr['tier_acc']:.1%}")

        joblib.dump(
            {
                "models": models,
                "seeds": list(ENSEMBLE_SEEDS),
                "feature_count": int(X.shape[1]),
                "feature_order": "minilm384_then_handcrafted4",
                "embedder": str(EMBED_DIR),
                "thr": DEPLOYED_THR,
                "train_n": len(tr),
                "held_out": {k: hr[k] for k in ("mae", "spearman", "tier_acc")},
                "tag": tag,
            },
            OUT / f"{tag}.joblib",
        )

    # ---- report ----
    g, a, d = results
    better_rho = [r for r in (a, d) if r["spearman"] > g["spearman"]]
    lines = [
        "# Support difficulty model - 3-run comparison",
        "",
        f"- held-out: **{len(hq):,} rows**, the exact v4 split (`in_train==0`) recovered from",
        f"  `{OLD_V7}`; thresholds cheap<=4.5, frontier>=6.0; seed {SEED}",
        f"- featurization self-check: reproduced the deployed model's own metrics to within {drift:.4f}",
        "",
        "## Headline - identical held-out rows, identical thresholds",
        "",
        "| run | train rows | MAE | Spearman | tier acc | frontier recall | under-routed |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r['name']} | {r['train_n']:,} | {r['mae']:.3f} | {r['spearman']:.3f} | "
            f"{r['tier_acc']:.1%} | {r['recall'].get('frontier', 0):.1%} | {r['under_routed']} |"
        )

    lines += ["", "## Per-tier recall", ""]
    for r in results:
        cells = "   ".join(f"{t} {r['recall'].get(t, 0):.1%}" for t in ("cheap", "mid", "frontier"))
        lines.append(f"- **{r['name']}**: {cells}")

    lines += ["", "## Under/over-routing vs gold", "",
              f"Gold frontier rows in the held-out set: {g['n_true_frontier']}", ""]
    for r in results:
        lines.append(
            f"- **{r['name']}**: under-routed {r['under_routed']}  "
            f"(hard query sent to a cheaper tier)   over-routed {r['over_routed']}"
        )

    lines += ["", "## Internal held-out split (support labels only)", ""]
    for r in results:
        if "internal" in r:
            i = r["internal"]
            lines.append(
                f"- **{r['name']}**: MAE {i['mae']:.3f}  spearman {i['spearman']:.3f}  tier acc {i['tier_acc']:.1%}"
            )

    lines += ["", "## Verdict", ""]
    if not better_rho:
        lines.append(
            "**No support model beat the deployed generic model on Spearman.** A support-specific "
            "model is not justified on this evidence - keep the generic model and do not spend the "
            "remaining 148 batches."
        )
    else:
        names = ", ".join(r["name"] for r in better_rho)
        lines.append(f"**{names} beat generic on Spearman.** That is the signal to keep going.")
    if a["spearman"] > d["spearman"]:
        lines.append(
            "DS2 synthetic rows helped (`support_all` > `support_ds3`), so the mix is worth keeping "
            "and finishing all 238 batches buys more data."
        )
    elif d["spearman"] > a["spearman"]:
        lines.append(
            "DS2 synthetic rows diluted the model (`support_ds3` > `support_all`). Train on real "
            "tickets only, and relabel only the DS3 batches going forward."
        )
    else:
        lines.append("DS2 and DS3 perform the same, so the DS2 labels carry no net value either way.")

    frontier_win = [r for r in (a, d) if r["recall"].get("frontier", 0) > g["recall"].get("frontier", 0)]
    if frontier_win:
        lines.append(
            f"**{', '.join(r['name'] for r in frontier_win)} also improved frontier recall**, which "
            "matters more than MAE: under-routing a genuinely hard query is the failure mode that "
            "hurts answer quality."
        )
    else:
        lines.append(
            "**No support model improved frontier recall.** Watch this: a model can win MAE by "
            "pushing hard queries downward, which is the wrong trade for a router."
        )

    lines += [
        "",
        "## Caveats",
        "",
        "- The held-out set is generic-domain gold (programming, writing, reasoning), not support "
        "tickets. It measures whether support training damaged general ability, NOT support-domain "
        "accuracy. For that, hold out some labeled support batches as an internal test set.",
        "- Score 9-10 is nearly empty in the support labels, so neither support model has evidence "
        "for the top band.",
        "- Two reply files were rejected at merge time (batch_225 had 209 lines, batch_238 had 199), "
        "so 400 of 18,000 potential labels are still missing.",
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n{'=' * 60}\n{REPORT.read_text(encoding='utf-8')}")
    print(f"models written to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
