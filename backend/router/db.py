import os
import logging
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Text
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime

load_dotenv()

log = logging.getLogger("routewise.db")

Base = declarative_base()
_db_url = os.getenv("DATABASE_URL", "")
_is_postgres = _db_url.startswith("postgresql")
_connect_args = {"connect_timeout": 10} if _is_postgres else {}
_pool_kwargs = {"pool_pre_ping": True, "pool_recycle": 300, "pool_size": 5, "max_overflow": 10} if _is_postgres else {}
engine = create_engine(_db_url, connect_args=_connect_args, **_pool_kwargs)
SessionLocal = sessionmaker(bind=engine)


class ApiKey(Base):
    __tablename__ = "api_keys"
    id = Column(Integer, primary_key=True)
    key = Column(String, unique=True, index=True)
    name = Column(String)
    user_id = Column(String, nullable=True, index=True)
    daily_budget_usd = Column(Float, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class RequestLog(Base):
    __tablename__ = "request_logs"
    __table_args__ = (
        {"sqlite_autoincrement": True},
    )
    id = Column(Integer, primary_key=True)
    api_key_id = Column(Integer, nullable=True, index=True)
    user_id = Column(String, nullable=True, index=True)
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
    tokens_saved_usd = Column(Float, nullable=True)
    quality_score = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class UserConfig(Base):
    __tablename__ = "user_configs"
    id = Column(Integer, primary_key=True)
    user_id = Column(String, nullable=True, index=True)
    tier = Column(String)
    provider = Column(String)
    model_id = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserSettings(Base):
    __tablename__ = "user_settings"
    id = Column(Integer, primary_key=True)
    user_id = Column(String, nullable=True, index=True, unique=True)
    router_threshold = Column(Float, default=1.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AlertRule(Base):
    __tablename__ = "alert_rules"
    id = Column(Integer, primary_key=True)
    user_id = Column(String, nullable=False, index=True)
    alert_type = Column(String, nullable=False)  # daily_spend | error_rate | latency
    threshold = Column(Float, nullable=False)
    webhook_url = Column(String, nullable=False)
    last_fired_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ModelPricing(Base):
    __tablename__ = "model_pricing"
    id = Column(Integer, primary_key=True)
    provider = Column(String, nullable=False)
    model_id = Column(String, nullable=False, index=True)
    display_name = Column(String, nullable=False)
    price_per_m_input = Column(Float, nullable=False)
    price_per_m_output = Column(Float, nullable=False)
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


try:
    Base.metadata.create_all(engine)
except Exception as e:
    log.warning("DB init failed (will retry on first request): %s", e)

# Migration: add quality_score column if missing on existing tables
try:
    from sqlalchemy import text
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE request_logs ADD COLUMN quality_score FLOAT"))
        conn.commit()
except Exception:
    pass


def compute_quality_score(cache_hit: bool, cache_similarity: float | None, fallback_used: bool) -> float:
    if cache_hit and cache_similarity is not None:
        return round(min(float(cache_similarity), 1.0), 4)
    if fallback_used:
        return 0.85
    return 1.0


def log_request(data: dict):
    session = SessionLocal()
    try:
        entry = RequestLog(**data)
        session.add(entry)
        session.commit()
    except Exception as e:
        log.error("log_request failed: %s | data=%s", e, {k: v for k, v in data.items() if k != 'response'})
        session.rollback()
        try:
            session.close()
            session = SessionLocal()
            entry = RequestLog(**data)
            session.add(entry)
            session.commit()
        except Exception as e2:
            log.error("log_request retry also failed: %s", e2)
            session.rollback()
    finally:
        session.close()