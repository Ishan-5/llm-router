import sys
import os
import json
import numpy as np
from sqlalchemy import create_engine, Column, Integer, String, Float, Text, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime, timedelta

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))
from predict_difficulty import get_embedder

SIMILARITY_THRESHOLD = 0.95  # conservative on purpose -- see module docstring

Base = declarative_base()

_db_url = os.getenv("DATABASE_URL", "")
_connect_args = {"connect_timeout": 10} if _db_url.startswith("postgresql") else {}
engine = create_engine(_db_url, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine)


class QueryCache(Base):
    __tablename__ = "query_cache"
    id = Column(Integer, primary_key=True)
    query = Column(Text)
    embedding = Column(Text)  # JSON-encoded list of floats
    response = Column(Text)
    tier = Column(String)
    model_id = Column(String)
    original_cost_usd = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)


try:
    Base.metadata.create_all(engine)
except Exception as e:
    print(f"[cache] DB init failed (will retry on first request): {e}")


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))


def check_cache(query: str) -> dict | None:
    embedder = get_embedder()
    query_embed = embedder.encode([query])[0]

    session = SessionLocal()
    rows = session.query(QueryCache).all()
    session.close()

    if not rows:
        return None

    matrix = np.array([json.loads(r.embedding) for r in rows])
    norms = np.linalg.norm(matrix, axis=1) * np.linalg.norm(query_embed)
    sims = matrix @ query_embed / (norms + 1e-8)
    best_idx = int(np.argmax(sims))
    best_sim = float(sims[best_idx])
    best_row = rows[best_idx]

    if best_sim >= SIMILARITY_THRESHOLD:
        return {
            "matched_query": best_row.query,
            "response": best_row.response,
            "tier": best_row.tier,
            "model_id": best_row.model_id,
            "original_cost_usd": best_row.original_cost_usd,
            "similarity": best_sim,
        }
    return None


MAX_ROWS = 5_000
EXPIRY_DAYS = 30


def _evict(session):
    expiry_cutoff = datetime.utcnow() - timedelta(days=EXPIRY_DAYS)
    session.query(QueryCache).filter(QueryCache.created_at < expiry_cutoff).delete()
    excess = session.query(QueryCache).count() - MAX_ROWS
    if excess > 0:
        oldest_ids = [r.id for r in session.query(QueryCache.id).order_by(QueryCache.created_at).limit(excess)]
        session.query(QueryCache).filter(QueryCache.id.in_(oldest_ids)).delete(synchronize_session=False)


def add_to_cache(query: str, response: str, tier: str, model_id: str, cost_usd: float):
    embedder = get_embedder()
    embedding = embedder.encode([query])[0].tolist()

    session = SessionLocal()
    entry = QueryCache(
        query=query,
        embedding=json.dumps(embedding),
        response=response,
        tier=tier,
        model_id=model_id,
        original_cost_usd=cost_usd,
    )
    session.add(entry)
    _evict(session)
    session.commit()
    session.close()