import os
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime

Base = declarative_base()
engine = create_engine(os.getenv("DATABASE_URL"))
SessionLocal = sessionmaker(bind=engine)


class ApiKey(Base):
    __tablename__ = "api_keys"
    id = Column(Integer, primary_key=True)
    key = Column(String, unique=True, index=True)
    name = Column(String)  # e.g. "acme-corp-demo"
    daily_budget_usd = Column(Float, nullable=True)  # None = no cap
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class RequestLog(Base):
    __tablename__ = "request_logs"
    id = Column(Integer, primary_key=True)
    api_key_id = Column(Integer, nullable=True)  # which key made this request
    query = Column(String)
    difficulty_score = Column(Float)
    intended_tier = Column(String)
    tier = Column(String)
    fallback_used = Column(Boolean, default=False)
    cache_hit = Column(Boolean, default=False)
    cache_similarity = Column(Float, nullable=True)
    model_id = Column(String)
    input_tokens = Column(Integer)
    output_tokens = Column(Integer)
    cost_usd = Column(Float)
    latency_ms = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)


class UserConfig(Base):
    __tablename__ = "user_configs"
    id = Column(Integer, primary_key=True)
    tier = Column(String)        # cheap / mid / frontier
    provider = Column(String)    # groq / openai / anthropic / ollama
    model_id = Column(String)    # e.g. gpt-4o-mini
    created_at = Column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(engine)


def log_request(data: dict):
    session = SessionLocal()
    entry = RequestLog(**data)
    session.add(entry)
    session.commit()
    session.close()