"""
Export live LLM-labeled queries to a CSV for retraining the difficulty model.

Each row is a query the router served live, with both the ML model's difficulty
score and the LLM-as-labeler's ground-truth score. Feed this to
`src/train_difficulty_model.py` (or merge into the labeled pool) to retrain on
real traffic instead of the static dataset.

Usage:
    python scripts/export_labeled_queries.py
    python scripts/export_labeled_queries.py training_export.csv
"""
import sys
import csv
sys.path.append(".")
from router.db import SessionLocal, RequestLog
from predict_difficulty import score_to_tier

DEFAULT_OUT = "labeled_queries_live.csv"

TIER_RANK = {"cheap": 0, "mid": 1, "frontier": 2}


def export(output_path: str):
    session = SessionLocal()
    out_rows = []
    try:
        rows = (
            session.query(RequestLog)
            .filter(
                RequestLog.llm_difficulty_score.isnot(None),
                RequestLog.difficulty_score.isnot(None),
                RequestLog.cache_hit == False,
                RequestLog.tier != "web",
            )
            .order_by(RequestLog.created_at.desc())
            .all()
        )
        for r in rows:
            ml_tier = score_to_tier(r.difficulty_score, margin=1.0)[0]
            llm_tier = r.llm_predicted_tier or score_to_tier(r.llm_difficulty_score, margin=1.0)[0]
            agreement = ml_tier == llm_tier
            out_rows.append({
                "query": r.query,
                "difficulty_score": r.difficulty_score,
                "ml_tier": ml_tier,
                "llm_difficulty_score": r.llm_difficulty_score,
                "llm_tier": llm_tier,
                "agreement": agreement,
                "served_tier": r.tier,
                "cache_hit": r.cache_hit,
                "created_at": r.created_at.isoformat() if r.created_at else "",
            })
    finally:
        session.close()

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()) if out_rows else [
            "query", "difficulty_score", "ml_tier", "llm_difficulty_score",
            "llm_tier", "agreement", "served_tier", "cache_hit", "created_at",
        ])
        writer.writeheader()
        writer.writerows(out_rows)

    agree = sum(1 for r in out_rows if r["agreement"])
    n = len(out_rows)
    print(f"Exported {n} labeled rows to {output_path}")
    print(f"Exact-tier agreement: {agree}/{n} ({agree / n * 100:.1f}%)" if n else "No labeled rows yet.")


if __name__ == "__main__":
    output_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT
    export(output_path)