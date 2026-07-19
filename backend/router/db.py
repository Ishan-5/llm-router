"""
Three tables — keys, logs, config. 
Everything the router tracks flows through RequestLog. 
The ApiKey table is what makes auth and budget enforcement possible. 
UserConfig is what makes BYOM possible. Base.metadata.create_all(engine) means zero manual DB setup needed.
"""

import os
import logging
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Text
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime

log = logging.getLogger("routewise.db")

Base = declarative_base()
_db_url = os.getenv("DATABASE_URL", "")
_connect_args = {"connect_timeout": 10} if _db_url.startswith("postgresql") else {}
engine = create_engine(_db_url, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine)


class ApiKey(Base):
    __tablename__ = "api_keys"
    id = Column(Integer, primary_key=True)
    key = Column(String, unique=True, index=True)
    name = Column(String)  # e.g. "acme-corp-demo"
    user_id = Column(String, nullable=True, index=True)  # Supabase auth user UUID
    daily_budget_usd = Column(Float, nullable=True)  # None = no cap
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class RequestLog(Base):
    __tablename__ = "request_logs"
    __table_args__ = (
        # Indexes for high-traffic query columns
        {"sqlite_autoincrement": True},
    )
    id = Column(Integer, primary_key=True)
    api_key_id = Column(Integer, nullable=True, index=True)  # which key made this request
    user_id = Column(String, nullable=True, index=True)       # Supabase auth user UUID (denormalized from api_keys for fast admin queries)
    query = Column(String)
    response = Column(Text, nullable=True)
    difficulty_score = Column(Float)
    intended_tier = Column(String, index=True)
    tier = Column(String, index=True)
    fallback_used = Column(Boolean, default=False)
    cache_hit = Column(Boolean, default=False, index=True)
    cache_similarity = Column(Float, nullable=True)
    model_id = Column(String, index=True)
    input_tokens = Column(Integer)
    output_tokens = Column(Integer)
    cost_usd = Column(Float)
    latency_ms = Column(Float)
    tokens_saved_usd = Column(Float, nullable=True)  # dollar value saved on cache hits
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class UserConfig(Base):
    __tablename__ = "user_configs"
    id = Column(Integer, primary_key=True)
    user_id = Column(String, nullable=True, index=True)  # Supabase auth user UUID
    tier = Column(String)        # cheap / mid / frontier
    provider = Column(String)    # groq / openai / anthropic / ollama
    model_id = Column(String)    # e.g. gpt-4o-mini
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ModelPricing(Base):
    __tablename__ = "model_pricing"
    id = Column(Integer, primary_key=True)
    provider = Column(String, nullable=False)           # groq / openai / anthropic / etc.
    model_id = Column(String, nullable=False, index=True)
    display_name = Column(String, nullable=False)
    price_per_m_input = Column(Float, nullable=False)
    price_per_m_output = Column(Float, nullable=False)
    notes = Column(Text, nullable=True)                 # e.g. tiered pricing detail
    is_active = Column(Boolean, default=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


try:
    Base.metadata.create_all(engine)
except Exception as e:
    log.warning("DB init failed (will retry on first request): %s", e)


def log_request(data: dict):
    session = SessionLocal()
    try:
        entry = RequestLog(**data)
        session.add(entry)
        session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()