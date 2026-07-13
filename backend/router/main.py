import time
import asyncio
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
from sqlalchemy import func
from router.classifier import get_tier
from router.rate_limiter import call_with_failover, AllTiersFailedError
from router.cache import check_cache, add_to_cache
from router.db import log_request, SessionLocal, RequestLog, ApiKey, UserConfig
from router.auth import require_api_key, check_budget
from router.config import TIER_MARGIN, MODEL_CONFIG, SUPPORTED_PROVIDERS
from router.guardrails import is_prompt_injection, sanitize_pii
from router.providers_registry import PROVIDERS_REGISTRY
from router.model_config_loader import get_active_config
from router.providers import validate_key

app = FastAPI()
executor = ThreadPoolExecutor()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # fine for a local demo; restrict this in real prod
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    query: str
    override_tier: str | None = None

    @field_validator("query")
    @classmethod
    def validate_query(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("Query cannot be empty")
        if len(v) > 1000:
            raise ValueError("Query cannot exceed 1000 characters")
        return v

    @field_validator("override_tier")
    @classmethod
    def validate_override(cls, v):
        if v is not None and v not in ("cheap", "mid", "frontier"):
            raise ValueError("override_tier must be 'cheap', 'mid', or 'frontier'")
        return v


@app.post("/route")
async def route_query(req: QueryRequest, api_key: ApiKey = Depends(require_api_key)):
    if is_prompt_injection(req.query):
        raise HTTPException(status_code=400, detail="Prompt injection detected")

    start = time.time()
    loop = asyncio.get_event_loop()

    # 1. Run cache check and classifier in parallel
    cached, (difficulty_score, tier) = await asyncio.gather(
        loop.run_in_executor(executor, check_cache, req.query),
        loop.run_in_executor(executor, get_tier, req.query, TIER_MARGIN),
    )

    if cached is not None:
        latency_ms = round((time.time() - start) * 1000, 2)
        log_request({
            "api_key_id": api_key.id,
            "query": sanitize_pii(req.query),
            "difficulty_score": None,
            "intended_tier": cached["tier"],
            "tier": cached["tier"],
            "fallback_used": False,
            "cache_hit": True,
            "cache_similarity": cached["similarity"],
            "model_id": cached["model_id"],
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0.0,
            "latency_ms": latency_ms,
        })
        return {
            "response": cached["response"],
            "routed_to": cached["tier"],
            "cache_hit": True,
            "cache_similarity": cached["similarity"],
            "cost_usd": 0.0,
            "latency_ms": latency_ms,
        }

    # 2. No cache hit -- use override if given, otherwise the predicted tier
    routing_tier = req.override_tier if req.override_tier else tier

    # 2a. Budget enforcement -- if this key is over its daily cap, force
    # everything to the cheap tier regardless of predicted difficulty or override
    over_budget = not check_budget(api_key)
    if over_budget:
        routing_tier = "cheap"

    try:
        result = await loop.run_in_executor(executor, call_with_failover, routing_tier, req.query)
    except AllTiersFailedError as e:
        raise HTTPException(status_code=503, detail=str(e))

    latency_ms = round((time.time() - start) * 1000, 2)

    log_request({
        "api_key_id": api_key.id,
        "query": sanitize_pii(req.query),
        "difficulty_score": difficulty_score,
        "intended_tier": result["intended_tier"],
        "tier": result["tier"],
        "fallback_used": result["fallback_used"],
        "cache_hit": False,
        "cache_similarity": None,
        "model_id": result["model_id"],
        "input_tokens": result["input_tokens"],
        "output_tokens": result["output_tokens"],
        "cost_usd": result["cost_usd"],
        "latency_ms": result["latency_ms"] if "latency_ms" in result else latency_ms,
    })

    # 3. Store in cache async (fire and forget -- don't block the response)
    loop.run_in_executor(executor, add_to_cache, req.query, result["text"], result["tier"], result["model_id"], result["cost_usd"])

    return {
        "response": result["text"],
        "routed_to": result["tier"],
        "intended_tier": result["intended_tier"],
        "predicted_tier": tier,
        "override_used": req.override_tier is not None,
        "budget_capped": over_budget,
        "fallback_used": result["fallback_used"],
        "cache_hit": False,
        "difficulty_score": difficulty_score,
        "cost_usd": result["cost_usd"],
        "latency_ms": latency_ms,
    }


@app.get("/providers")
def get_providers():
    """Returns all supported providers and their known models for frontend dropdowns."""
    return PROVIDERS_REGISTRY


class TierConfig(BaseModel):
    model_config = {"protected_namespaces": ()}

    provider: str
    model_id: str
    api_key: str

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v):
        if v not in SUPPORTED_PROVIDERS:
            raise ValueError(f"Unsupported provider '{v}'. Must be one of: {SUPPORTED_PROVIDERS}")
        return v

    @field_validator("model_id")
    @classmethod
    def validate_model_id(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("model_id cannot be empty")
        return v


class UserConfigRequest(BaseModel):
    cheap: TierConfig | None = None
    mid: TierConfig | None = None
    frontier: TierConfig | None = None


@app.get("/config")
def get_config():
    """Returns the currently active model config (user overrides merged with defaults)."""
    config = get_active_config()
    # strip api_key from response -- never send keys back to frontend
    return {
        tier: {k: v for k, v in cfg.items() if k != "api_key"}
        for tier, cfg in config.items()
    }


@app.post("/config")
def save_config(req: UserConfigRequest):
    """
    Saves user model config for each tier provided.
    1. Format-validates provider + model_id (via pydantic above)
    2. Makes a test call (max_tokens=1) to verify the key works
    3. Saves provider + model_id to user_configs table (no api_key stored)
    API keys are returned to frontend to store in localStorage only.
    """
    tiers = {
        "cheap": req.cheap,
        "mid": req.mid,
        "frontier": req.frontier,
    }

    results = {}
    session = SessionLocal()
    try:
        for tier, cfg in tiers.items():
            if cfg is None:
                continue

            # validate key with a real test call
            try:
                validate_key(cfg.provider, cfg.model_id, cfg.api_key)
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Key validation failed for {tier} tier ({cfg.provider}/{cfg.model_id}): {e}"
                )

            # save only non-sensitive fields to DB
            entry = UserConfig(tier=tier, provider=cfg.provider, model_id=cfg.model_id)
            session.add(entry)
            results[tier] = {"provider": cfg.provider, "model_id": cfg.model_id, "status": "saved"}

        session.commit()
    finally:
        session.close()

    return {"saved": results}


@app.get("/stats")
def get_stats():
    """
    Aggregates real logged requests for the dashboard.

    HONEST LIMITATION: cache-hit rows are logged with input_tokens=output_tokens=0
    (no provider call happened, so there's nothing to count), which means the
    "hypothetical cost" for cache hits comes out to $0 too -- understating how
    much a cache hit actually saved. Fixing this properly would mean estimating
    token count from query length for cache-hit rows; not done here, so treat
    total_hypothetical_cost as a slight underestimate of true savings.
    """
    session = SessionLocal()
    try:
        total_requests = session.query(func.count(RequestLog.id)).scalar() or 0

        tier_counts = dict(
            session.query(RequestLog.tier, func.count(RequestLog.id))
            .group_by(RequestLog.tier).all()
        )

        total_actual_cost = float(session.query(func.sum(RequestLog.cost_usd)).scalar() or 0.0)

        cache_hits = session.query(func.count(RequestLog.id)).filter(RequestLog.cache_hit == True).scalar() or 0
        cache_hit_rate = (cache_hits / total_requests) if total_requests else 0.0

        fallback_count = session.query(func.count(RequestLog.id)).filter(RequestLog.fallback_used == True).scalar() or 0

        frontier_cfg = MODEL_CONFIG["frontier"]
        token_rows = session.query(RequestLog.input_tokens, RequestLog.output_tokens, RequestLog.created_at).all()

        total_hypothetical_cost = 0.0
        hyp_by_day = defaultdict(float)
        for in_tok, out_tok, created_at in token_rows:
            hyp_cost = (
                (in_tok or 0) / 1_000_000 * frontier_cfg["price_per_m_input"]
                + (out_tok or 0) / 1_000_000 * frontier_cfg["price_per_m_output"]
            )
            total_hypothetical_cost += hyp_cost
            day = created_at.date().isoformat() if created_at else "unknown"
            hyp_by_day[day] += hyp_cost

        avg_latency_by_tier = {
            tier: float(avg) for tier, avg in
            session.query(RequestLog.tier, func.avg(RequestLog.latency_ms)).group_by(RequestLog.tier).all()
            if tier and avg is not None
        }

        daily_actual = session.query(
            func.date(RequestLog.created_at).label("day"),
            func.sum(RequestLog.cost_usd),
        ).group_by("day").order_by("day").all()

        daily_costs = [
            {
                "date": str(day),
                "actual_cost": float(actual or 0),
                "hypothetical_cost": hyp_by_day.get(str(day), 0.0),
            }
            for day, actual in daily_actual
        ]

        return {
            "total_requests": total_requests,
            "tier_counts": tier_counts,
            "total_actual_cost": total_actual_cost,
            "total_hypothetical_cost": total_hypothetical_cost,
            "cache_hit_rate": cache_hit_rate,
            "fallback_count": fallback_count,
            "avg_latency_by_tier": avg_latency_by_tier,
            "daily_costs": daily_costs,
        }
    finally:
        session.close()