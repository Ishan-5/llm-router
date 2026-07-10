import os
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime

Base = declarative_base()
engine = create_engine(os.getenv("DATABASE_URL"))
SessionLocal = sessionmaker(bind=engine)

class RequestLog(Base):
    __tablename__ = "request_logs"
    id = Column(Integer, primary_key=True)
    query = Column(String)
    difficulty_score = Column(Float)
    intended_tier = Column(String)
    tier = Column(String)  # tier that actually served the request
    fallback_used = Column(Boolean, default=False)
    cache_hit = Column(Boolean, default=False)
    cache_similarity = Column(Float, nullable=True)
    model_id = Column(String)
    input_tokens = Column(Integer)
    output_tokens = Column(Integer)
    cost_usd = Column(Float)
    latency_ms = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

try:
    Base.metadata.create_all(engine)
except Exception as e:
    print(f"[db] DB init failed (will retry on first request): {e}")

def log_request(data: dict):
    session = SessionLocal()
    entry = RequestLog(**data)
    session.add(entry)
    session.commit()
    session.close()