"""
Three tables — keys, logs, config. 
Everything the router tracks flows through RequestLog. 
The ApiKey table is what makes auth and budget enforcement possible. 
UserConfig is what makes BYOM possible. Base.metadata.create_all(engine) means zero manual DB setup needed.
"""

import os
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Text
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


Base.metadata.create_all(engine)


def log_request(data: dict):
    session = SessionLocal()
    entry = RequestLog(**data)
    session.add(entry)
    session.commit()
    session.close()