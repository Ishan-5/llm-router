import os
import pandas as pd
import numpy as np
import joblib
from sentence_transformers import SentenceTransformer
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge, RidgeCV
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    mean_absolute_percentage_error,
    accuracy_score,
    precision_recall_fscore_support,
    confusion_matrix,
    classification_report,
)
from scipy.stats import spearmanr

_BASE = os.path.dirname(__file__)
DATA_PATH = os.path.join(_BASE, "..", "dataset_pipeline", "datasets", "labeled_dataset", "labeled_queries_full_v2.csv")
MODEL_OUT = os.path.join(_BASE, "..", "models", "difficulty_regressor.joblib")
EMBEDDER_NAME = "all-MiniLM-L6-v2"  # 384-dimensional embeddings, optimized for CPU execution


def load_data():
    df = pd.read_csv(DATA_PATH)
    df = df[df["difficulty_score"].between(0, 10)].copy()
    df = df.dropna(subset=["query"])
    print(f"Loaded {len(df)} usable rows")
    return df


def embed_queries(embedder, queries):
    return embedder.encode(list(queries), show_progress_bar=True, batch_size=64)


def add_handcrafted_features(df, X_embed):
    # Auxiliary handcrafted features to complement semantic embeddings
    word_count = df["query"].astype(str).str.split().str.len().values.reshape(-1, 1)
    has_code = df["query"].astype(str).str.contains(
        r"(?:def |function|class |import |SELECT |for\(|while\()"
    ).astype(int).values.reshape(-1, 1)
    question_mark = df["query"].astype(str).str.contains(r"\?").astype(int).values.reshape(-1, 1)

    requested_length = (
        df["query"].astype(str)
        .str.extract(r"(\d+)[\s-]*word")[0]
        .astype(float)
        .fillna(0)
        .values.reshape(-1, 1)
    )

    extra = np.hstack([word_count, has_code, question_mark, requested_length])
    return np.hstack([X_embed, extra])


def main():
    df = load_data()

    print(f"Loading embedder: {EMBEDDER_NAME}")
    embedder = SentenceTransformer(EMBEDDER_NAME)

    print("Embedding queries...")
    X_embed = embed_queries(embedder, df["query"])
    X = add_handcrafted_features(df, X_embed)
    y = df["difficulty_score"].values

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.15, random_state=42
    )

    candidates = {
        "Ridge (alpha=1.0)": Pipeline([
            ("scale", StandardScaler()),
            ("ridge", Ridge(alpha=1.0)),
        ]),
        "RidgeCV (auto-tuned alpha)": Pipeline([
            ("scale", StandardScaler()),
            ("ridge", RidgeCV(alphas=np.logspace(-2, 3, 20))),
        ]),
        "RandomForest": RandomForestRegressor(
            n_estimators=300, max_depth=12, random_state=42, n_jobs=-1
        ),
    }

    try:
        from lightgbm import LGBMRegressor
        candidates["LightGBM"] = LGBMRegressor(
            n_estimators=400, max_depth=6, learning_rate=0.05,
            random_state=42, verbose=-1,
        )
    except ImportError:
        print("(lightgbm not installed -- skipping. `pip install lightgbm --break-system-packages` to include it)")

    def bucketed_mae(y_true, y_pred):
        buckets = {
            "easy (0-3)": (y_true >= 0) & (y_true <= 3),
            "medium (4-6)": (y_true >= 4) & (y_true <= 6),
            "hard (7-10)": (y_true >= 7) & (y_true <= 10),
        }
        out = {}
        for name, mask in buckets.items():
            if mask.sum() > 0:
                out[name] = (mean_absolute_error(y_true[mask], y_pred[mask]), mask.sum())
        return out

    results = {}
    for name, model in candidates.items():
        model.fit(X_train, y_train)
        preds = model.predict(X_test)
        preds_clipped = np.clip(preds, 0, 10)
        mae = mean_absolute_error(y_test, preds_clipped)
        rho, _ = spearmanr(y_test, preds_clipped)
        results[name] = (model, mae, rho)
        extra_info = ""
        if hasattr(model, "named_steps") and "ridge" in getattr(model, "named_steps", {}) and hasattr(model.named_steps["ridge"], "alpha_"):
            extra_info = f" (chosen alpha={model.named_steps['ridge'].alpha_:.3f})"
        print(f"{name}: overall MAE={mae:.3f}  Spearman={rho:.3f}{extra_info}")
        for bucket_name, (bucket_mae, n) in bucketed_mae(y_test, preds_clipped).items():
            print(f"    {bucket_name}: MAE={bucket_mae:.3f}  (n={n})")

    best_name = min(results, key=lambda k: results[k][1])
    best_model, best_mae, best_rho = results[best_name]
    print(f"\nBest model: {best_name} (MAE={best_mae:.3f}, Spearman={best_rho:.3f})")

    
    print("\n" + "=" * 60)
    print("FULL METRICS -- best model:", best_name)
    print("=" * 60)

    preds = np.clip(best_model.predict(X_test), 0, 10)

    
    rmse = np.sqrt(mean_squared_error(y_test, preds))
    r2 = r2_score(y_test, preds)
    # MAPE is unstable near y=0 (division by ~0), so compute it only on y_test > 0
    nonzero_mask = y_test > 0
    mape = mean_absolute_percentage_error(y_test[nonzero_mask], preds[nonzero_mask]) if nonzero_mask.sum() > 0 else float("nan")

    print("\n-- Regression metrics (raw 0-10 score) --")
    print(f"MAE:  {mean_absolute_error(y_test, preds):.3f}  (avg points off, lower=better)")
    print(f"RMSE: {rmse:.3f}  (penalizes big misses more than MAE)")
    print(f"R^2:  {r2:.3f}  (variance explained, 1.0=perfect, 0=no better than predicting the mean)")
    print(f"MAPE: {mape:.1%}  (avg % error, excludes true-score==0 rows)")

    
    def to_tier(scores):
        tiers = np.full(scores.shape, "mid", dtype=object)
        tiers[scores <= 3] = "cheap"
        tiers[scores > 7] = "frontier"
        return tiers

    y_test_tier = to_tier(y_test)
    preds_tier = to_tier(preds)

    acc = accuracy_score(y_test_tier, preds_tier)
    precision, recall, f1, support = precision_recall_fscore_support(
        y_test_tier, preds_tier, labels=["cheap", "mid", "frontier"], zero_division=0
    )

    print("\n-- Tier-level classification metrics (cheap / mid / frontier) --")
    print(f"Tier accuracy: {acc:.1%}  (fraction routed to the exact correct tier)")
    print(f"\n{'Tier':<10}{'Precision':>12}{'Recall':>10}{'F1':>8}{'Support':>10}")
    for tier, p, r, f, s in zip(["cheap", "mid", "frontier"], precision, recall, f1, support):
        print(f"{tier:<10}{p:>12.2f}{r:>10.2f}{f:>8.2f}{s:>10d}")

    print("\nConfusion matrix (rows=true tier, cols=predicted tier):")
    cm = confusion_matrix(y_test_tier, preds_tier, labels=["cheap", "mid", "frontier"])
    print(f"{'':>12}{'cheap':>10}{'mid':>10}{'frontier':>10}")
    for label, row in zip(["cheap", "mid", "frontier"], cm):
        print(f"{label:>12}{row[0]:>10}{row[1]:>10}{row[2]:>10}")

    print("\nNote: off-diagonal cells adjacent to the diagonal (e.g. true=mid, pred=cheap)")
    print("are mild routing mistakes. Cells in the corners (true=cheap, pred=frontier or")
    print("vice versa) are the expensive/dangerous mistakes worth checking manually.")
    print("=" * 60)

    joblib.dump(
        {
            "model": best_model,
            "embedder_name": EMBEDDER_NAME,
            "model_name": best_name,
            "test_mae": best_mae,
            "test_spearman": best_rho,
        },
        MODEL_OUT,
    )
    print(f"Saved to {MODEL_OUT}")


if __name__ == "__main__":
    main()