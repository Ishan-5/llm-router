"""Reproducible retrain pipeline for the difficulty scorer (MLOps).

The pipeline does the whole train -> evaluate -> log -> deploy loop in one
command, so a "release" is repeatable instead of a one-off notebook run.

Usage:
    python mlops/retrain.py                       # train candidate, compare vs live model, log a metrics row
    python mlops/retrain.py --deploy --version v21   # only deploy if the candidate beats the live model
    python mlops/retrain.py --force --deploy --version v21  # deploy regardless
    python mlops/retrain.py --quick               # subsample for a fast smoke test (no deploy)

Rules
-----
- Data: the versioned gold CSV (8,783 Claude/human gold rows) is the only
  training input. Provenance is preserved per row (source + label_source).
- Split: if mlops/heldout_queries.csv exists (a query column), those exact rows
  are held out of training and become the evaluation set — the canonical way to
  reproduce the real v20-style eval on queries the live model never saw.
  Otherwise a deterministic random split (random_state=42) is used, and the
  live-model comparison is flagged as possibly leaky.
- Features: identical to the runtime prediction path (predict_difficulty.py),
  so train and serve can never drift apart.
- Model: ensemble of two LightGBM regressors (tuned + frontier-weighted 2.5x),
  averaged via EnsembleRegressor — the v20 architecture, recreated in-repo.
- Every run appends one row to model_metrics.csv (the experiment tracker).
- --deploy only writes a new joblib if it beats the current live metrics, and
  backs up the old model first so rollback is a file copy.
"""
import argparse
import datetime
import os
import re
import shutil
import sys

import joblib
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.linear_model import Ridge
from sklearn.metrics import (
    accuracy_score,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    recall_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.normpath(os.path.join(BASE, "..", "src"))
sys.path.insert(0, SRC)

from predict_difficulty import EnsembleRegressor, score_to_tier  # noqa: E402

GOLD_CSV = os.path.normpath(os.path.join(
    BASE, "..", "dataset_pipeline", "datasets", "labeled_dataset", "gold_labeled_queries.csv"
))
MODEL_OUT = os.path.normpath(os.path.join(BASE, "..", "models", "difficulty_regressor.joblib"))
METRICS_CSV = os.path.join(BASE, "model_metrics.csv")
HELDOUT_CSV = os.path.join(BASE, "heldout_queries.csv")
EMBEDDER_NAME = "all-MiniLM-L6-v2"

# Production-balanced boundaries (margin=1.0). Pulled from the single source of
# truth (score_to_tier) so eval always measures the same tiers the router uses.
_CHEAP_CEIL = score_to_tier(0.0, margin=1.0)[1]
_FRONTIER_FLOOR = score_to_tier(0.0, margin=1.0)[2]

TIERS = ["cheap", "mid", "frontier"]


def _now_utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def load_gold() -> pd.DataFrame:
    df = pd.read_csv(GOLD_CSV)
    df = df[["query", "gold_score", "source", "label_source"]].copy()
    df = df[df["gold_score"].between(0, 10)].dropna(subset=["query"])
    return df


def build_features(queries: pd.Series) -> np.ndarray:
    """Same handcrafted features as predict_difficulty.py (must never diverge)."""
    word_count = queries.str.split().str.len().to_numpy().astype(float)
    has_code = queries.str.contains(
        r"(?:def |function|class |import |SELECT |for\(|while\()"
    ).astype(int).to_numpy().astype(float)
    question_mark = queries.str.contains(r"\?").astype(int).to_numpy().astype(float)
    requested_length = (
        queries.str.extract(r"(\d+)[\s-]*word")[0].astype(float).fillna(0.0).to_numpy()
    )
    return np.column_stack([word_count, has_code, question_mark, requested_length])


def embed_queries(embedder, queries: pd.Series) -> np.ndarray:
    return embedder.encode(list(queries), show_progress_bar=True, batch_size=64)


def tier_of(scores: np.ndarray) -> np.ndarray:
    """Balanced thresholds (cheap<=4.5, frontier>=6.0) — what the router uses at margin=1.0."""
    out = np.full(scores.shape, "mid", dtype=object)
    out[scores <= _CHEAP_CEIL] = "cheap"
    out[scores >= _FRONTIER_FLOOR] = "frontier"
    return out


def train_ensemble(X_train, y_train, x_test):
    """v20-style ensemble: tuned LGBM + frontier-weighted LGBM (2.5x), averaged."""
    from lightgbm import LGBMRegressor

    base = dict(
        n_estimators=400,
        max_depth=6,
        learning_rate=0.05,
        num_leaves=63,
        min_child_samples=20,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        verbose=-1,
    )

    tuned = LGBMRegressor(**base)
    tuned.fit(X_train, y_train)

    sample_weight = np.where(y_train >= 7, 2.5, 1.0)
    frontier_weighted = LGBMRegressor(**base)
    frontier_weighted.fit(X_train, y_train, sample_weight=sample_weight)

    models = [tuned, frontier_weighted]
    return EnsembleRegressor(models), models


def evaluate(model, X_test, y_test):
    preds = np.clip(model.predict(X_test), 0, 10)
    y_true_tier = tier_of(y_test)
    y_pred_tier = tier_of(preds)

    return {
        "mae": float(mean_absolute_error(y_test, preds)),
        "rmse": float(np.sqrt(mean_squared_error(y_test, preds))),
        "r2": float(r2_score(y_test, preds)),
        "spearman": float(spearmanr(y_test, preds).statistic or 0.0),
        "tier_acc": float(accuracy_score(y_true_tier, y_pred_tier)),
        "cheap_recall": float(recall_score(y_true_tier, y_pred_tier, labels=TIERS, average=None)[0]),
        "mid_recall": float(recall_score(y_true_tier, y_pred_tier, labels=TIERS, average=None)[1]),
        "frontier_recall": float(recall_score(y_true_tier, y_pred_tier, labels=TIERS, average=None)[2]),
        "under_routed_frontier": int(np.sum((y_true_tier == "frontier") & (y_pred_tier != "frontier"))),
    }


def load_current_bundle():
    if not os.path.exists(MODEL_OUT):
        return None, None
    bundle = joblib.load(MODEL_OUT)
    return bundle, bundle.get("version", "unknown")


def read_metrics() -> pd.DataFrame:
    if os.path.exists(METRICS_CSV):
        return pd.read_csv(METRICS_CSV)
    return pd.DataFrame()


def record_metrics(row: dict):
    df = read_metrics()
    frame = pd.DataFrame([row])
    if df.empty:
        frame.to_csv(METRICS_CSV, index=False)
    else:
        frame.to_csv(METRICS_CSV, mode="a", header=False, index=False)
    print(f"\nMetrics row logged -> {METRICS_CSV}")


def print_report(label: str, m: dict):
    print(f"\n-- {label} --")
    print(f"MAE:          {m['mae']:.3f}")
    print(f"RMSE:         {m['rmse']:.3f}   R2: {m['r2']:.3f}")
    print(f"Spearman:     {m['spearman']:.3f}")
    print(f"Tier accuracy (balanced 4.5/6.0): {m['tier_acc']:.1%}")
    print(f"Recall  cheap={m['cheap_recall']:.2f}  mid={m['mid_recall']:.2f}  frontier={m['frontier_recall']:.2f}")
    print(f"Under-routed frontier (of frontier gold): {m['under_routed_frontier']}")


def auto_version() -> str:
    return "cand-" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deploy", action="store_true", help="write a new joblib if it beats the live model")
    parser.add_argument("--force", action="store_true", help="deploy even if the candidate loses")
    parser.add_argument("--version", default=None, help="version label for this run (default: cand-<timestamp>)")
    parser.add_argument("--quick", action="store_true", help="subsample rows for a fast smoke test (never deploys)")
    args = parser.parse_args()

    version = args.version or auto_version()
    gold = load_gold()
    print(f"Gold dataset: {len(gold)} rows (balanced 0-10 score, provenance preserved)")

    leak_warning = False
    if os.path.exists(HELDOUT_CSV):
        held = pd.read_csv(HELDOUT_CSV)[["query"]].drop_duplicates()
        test_df = gold.merge(held, on="query", how="inner")
        train_df = gold[~gold["query"].isin(test_df["query"])]
        print(f"Canonical held-out set: {len(test_df)} rows (from {HELDOUT_CSV})")
        print(f"Train: {len(train_df)} rows   Held-out: {len(test_df)} rows")
    else:
        rng = np.random.default_rng(42)
        held_mask = np.zeros(len(gold), dtype=bool)
        held_idx = rng.choice(len(gold), size=min(783, len(gold)), replace=False)
        held_mask[held_idx] = True
        train_df, test_df = gold[~held_mask], gold[held_mask]
        print(f"No canonical held-out set — using deterministic random split.")
        print(f"Train: {len(train_df)} rows   Held-out: {len(test_df)} rows")
        leak_warning = True  # these rows may overlap what the live model already trained on

    if args.quick:
        train_df = train_df.sample(n=min(1500, len(train_df)), random_state=1)
        test_df = test_df.sample(n=min(120, len(test_df)), random_state=1)
        print(f"[quick] subsampled -> train: {len(train_df)}, held-out: {len(test_df)}")

    print(f"\nLoading embedder: {EMBEDDER_NAME} (CPU)")
    from sentence_transformers import SentenceTransformer
    embedder = SentenceTransformer(EMBEDDER_NAME)

    print("Embedding queries...")
    X_train = np.hstack([embed_queries(embedder, train_df["query"]), build_features(train_df["query"])])
    y_train = train_df["gold_score"].to_numpy().astype(float)
    X_test = np.hstack([embed_queries(embedder, test_df["query"]), build_features(test_df["query"])])
    y_test = test_df["gold_score"].to_numpy().astype(float)

    print("\nTraining candidate ensemble (LGBM tuned + frontier-weighted 2.5x)...")
    candidate, sub_models = train_ensemble(X_train, y_train, X_test)
    cand_metrics = evaluate(candidate, X_test, y_test)
    print_report("CANDIDATE", cand_metrics)

    live_metrics = None
    deployed_key = None
    db, deployed_version = load_current_bundle()
    if db is not None:
        if leak_warning:
            print(
                "\n[!] Comparing against the live model WITHOUT a disjoint held-out set — "
                "live MAE/tier will look flattered because it trained on overlapping rows. "
                "Drop the real never-seen questions into mlops/heldout_queries.csv for a fair comparison."
            )
        live_metrics = evaluate(db["model"], X_test, y_test)
        deployed_key = deployed_version
        print_report(f"LIVE MODEL (bundle version={deployed_version})", live_metrics)

    # Deploy decision.
    deploy = False
    if args.quick:
        print("\n[quick] dry-run only — no deploy.")  # quick never deploys
    elif args.deploy:
        if args.force:
            deploy = True
        elif live_metrics is not None:
            beat = cand_metrics["mae"] < live_metrics["mae"]
            tier_beat = cand_metrics["tier_acc"] > live_metrics["tier_acc"]
            deploy = beat and tier_beat
            print(
                f"\nDeploy decision: candidate MAE {cand_metrics['mae']:.3f} vs live {live_metrics['mae']:.3f}; "
                f"tier acc {cand_metrics['tier_acc']:.1%} vs {live_metrics['tier_acc']:.1%} -> "
                f"{'DEPLOY' if deploy else 'skip (not a clean win on both)'}"
            )
        else:
            deploy = True  # no live model to beat — first deploy

    if deploy:
        if os.path.exists(MODEL_OUT):
            backup = f"{MODEL_OUT}.bak_{version}"
            shutil.copy2(MODEL_OUT, backup)
            print(f"Backed up current model -> {backup}")
        bundle = {
            "model": candidate,
            "embedder_name": EMBEDDER_NAME,
            "model_name": f"LGBM-ensemble ({', '.join(type(m).__name__ for m in sub_models)})",
            "version": version,
            "trained_at_utc": _now_utc(),
            "train_rows": int(len(train_df)),
            "test_rows": int(len(test_df)),
            "test_mae": cand_metrics["mae"],
            "test_spearman": cand_metrics["spearman"],
            "tier_acc": cand_metrics["tier_acc"],
        }
        joblib.dump(bundle, MODEL_OUT)
        print(f"Deployed -> {MODEL_OUT} (version {version})")
        status = "yes"
    else:
        status = "no"
        print("\nNo deploy this run (candidate evaluated + logged only).")

    # Log every run to the experiment tracker.
    note = "SMOKE TEST" if args.quick else f"replaced {deployed_key}" if deploy and deployed_key else "candidate (not deployed)"
    row = {
        "version": version,
        "date_utc": _now_utc(),
        "pipeline_source": "quick" if args.quick else "mlops",
        "train_rows": int(len(train_df)),
        "test_rows": int(len(test_df)),
        "mae": cand_metrics["mae"],
        "rmse": cand_metrics["rmse"],
        "r2": cand_metrics["r2"],
        "spearman": cand_metrics["spearman"],
        "tier_acc": cand_metrics["tier_acc"],
        "cheap_recall": cand_metrics["cheap_recall"],
        "mid_recall": cand_metrics["mid_recall"],
        "frontier_recall": cand_metrics["frontier_recall"],
        "under_routed_frontier": cand_metrics["under_routed_frontier"],
        "deployed": status,
        "notes": note,
    }
    record_metrics(row)


if __name__ == "__main__":
    main()