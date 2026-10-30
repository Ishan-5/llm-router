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
if not _db_url:
    _db_url = "sqlite:///./routewise_dev.db"
    log.warning(
        "DATABASE_URL not set - falling back to local SQLite dev DB "
        "(./routewise_dev.db). Set DATABASE_URL for production."
    )
_is_postgres = _db_url.startswith("postgresql")
_connect_args = {"connect_timeout": 10} if _is_postgres else {}
_pool_kwargs = {"pool_pre_ping": True, "pool_recycle": 300, "pool_size": 5, "max_overflow": 10} if _is_postgres else {}
engine = create_engine(_db_url, connect_args=_connect_args, **_pool_kwargs)
SessionLocal = sessionmaker(bind=engine)


class Team(Base):
    """A budget bucket a customer can put keys under.

    The owner ("CFO") sets one monthly cap here instead of a separate cap on
    every key. Requests made with any key in the team spend from that cap, so a
    team can share one key or give each member their own without changing how
    the budget is enforced.
    """
    __tablename__ = "teams"
    id = Column(Integer, primary_key=True)
    user_id = Column(String, nullable=True, index=True)
    name = Column(String, nullable=False)
    monthly_budget_usd = Column(Float, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ApiKey(Base):
    __tablename__ = "api_keys"
    id = Column(Integer, primary_key=True)
    key = Column(String, unique=True, index=True)
    name = Column(String)
    user_id = Column(String, nullable=True, index=True)
    team_id = Column(Integer, nullable=True, index=True)
    daily_budget_usd = Column(Float, nullable=True)
    # Optional per-key cap inside the team budget: enough for a contractor or a
    # CI job without giving it a whole team's worth of headroom.
    monthly_budget_usd = Column(Float, nullable=True)
    # Routing defaults for this key. A request can override them; they exist so
    # one key is a complete profile (policy, ceiling, sensitivity, cache) rather
    # than only a spend cap. NULL means "use the request or the account default".
    default_policy = Column(String, nullable=True)      # generic | 2tier | 3tier
    max_tier = Column(String, nullable=True)            # cheap | mid | frontier
    default_threshold = Column(Float, nullable=True)    # 0.0 .. 2.0
    cache_enabled = Column(Boolean, nullable=True, default=True)
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
    # Spend dimensions, supplied per request (X-RouteWise-Team / -Feature).
    # NULL means untagged; those requests still aggregate, just in one bucket.
    team_id = Column(String, nullable=True, index=True)
    feature_tag = Column(String, nullable=True, index=True)
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
    # Why a request was served by a cheaper tier than its score asked for.
    # budget_scope is one of key_daily, key_monthly, team_monthly, or NULL.
    budget_capped = Column(Boolean, nullable=True, default=False)
    budget_scope = Column(String, nullable=True)
    # quality_score is written only by the LLM judge (router/quality_judge.py).
    # quality_judged distinguishes a real judge score from "not scored yet".
    # Nothing else writes this column, so there is exactly one source of truth.
    quality_score = Column(Float, nullable=True)
    quality_judged = Column(Boolean, nullable=True, default=False)
    llm_difficulty_score = Column(Float, nullable=True)  # LLM-as-labeler ground-truth difficulty (0-10)
    llm_predicted_tier = Column(String, nullable=True)   # tier the router would pick from the LLM label
    label_judged = Column(Boolean, nullable=True, default=False)
    feedback = Column(String, nullable=True, index=True)  # up | down | None
    feedback_reason = Column(Text, nullable=True)
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
    _schema_ready = True
except Exception as e:
    _schema_ready = False
    log.warning("DB init failed (will retry on first request): %s", e)


# Columns added after a table first shipped.
#
# create_all() only creates missing TABLES; it never adds a column to a table
# that already exists, so a new field on the model above does nothing to a live
# database until an ALTER runs. Each statement is idempotent by exception:
# "duplicate column" means it is already there, which is the normal case after
# the first boot. Runs on SQLite (dev/tests) and Postgres (production) alike.
#
# Entries are (table, column, type). Keep this list append-only: a deploy only
# ever adds columns here, never rewrites an existing one.
_LATE_COLUMNS = (
    ("request_logs", "quality_score", "FLOAT"),
    ("request_logs", "feedback", "VARCHAR"),
    ("request_logs", "feedback_reason", "TEXT"),
    ("request_logs", "quality_judged", "BOOLEAN DEFAULT FALSE"),
    ("request_logs", "llm_difficulty_score", "FLOAT"),
    ("request_logs", "llm_predicted_tier", "VARCHAR"),
    ("request_logs", "label_judged", "BOOLEAN DEFAULT FALSE"),
    ("request_logs", "tokens_saved_usd", "FLOAT"),
    ("request_logs", "team_id", "VARCHAR"),
    ("request_logs", "feature_tag", "VARCHAR"),
    ("request_logs", "budget_capped", "BOOLEAN DEFAULT FALSE"),
    ("request_logs", "budget_scope", "VARCHAR"),
    ("api_keys", "team_id", "INTEGER"),
    ("api_keys", "monthly_budget_usd", "FLOAT"),
    ("api_keys", "default_policy", "VARCHAR"),
    ("api_keys", "max_tier", "VARCHAR"),
    ("api_keys", "default_threshold", "FLOAT"),
    ("api_keys", "cache_enabled", "BOOLEAN DEFAULT TRUE"),
)

_LATE_INDEXES = (
    ("ix_request_logs_team_id", "request_logs", "team_id"),
    ("ix_request_logs_feature_tag", "request_logs", "feature_tag"),
    ("ix_api_keys_team_id", "api_keys", "team_id"),
)


def _apply_late_schema():
    """Add post-launch columns and indexes that create_all() cannot."""
    from sqlalchemy import text

    for table, column, ddl in _LATE_COLUMNS:
        try:
            with engine.connect() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
                conn.commit()
        except Exception:
            pass  # already present

    for index_name, table, column in _LATE_INDEXES:
        try:
            with engine.connect() as conn:
                conn.execute(text(
                    f"CREATE INDEX IF NOT EXISTS {index_name} ON {table} ({column})"
                ))
                conn.commit()
        except Exception:
            pass


# Skip a dozen doomed round-trips when the database was unreachable above.
if _schema_ready:
    _apply_late_schema()


def log_request(data: dict):
    session = SessionLocal()
    try:
        entry = RequestLog(**data)
        session.add(entry)
        session.commit()
        return entry.id
    except Exception as e:
        log.error("log_request failed: %s | data=%s", e, {k: v for k, v in data.items() if k != 'response'})
        session.rollback()
        try:
            session.close()
            session = SessionLocal()
            entry = RequestLog(**data)
            session.add(entry)
            session.commit()
            return entry.id
        except Exception as e2:
            log.error("log_request retry also failed: %s", e2)
            session.rollback()
            return None
    finally:
        session.close()