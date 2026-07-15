import time
import asyncio
from datetime import datetime
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
from sqlalchemy import func
from router.classifier import get_tier
from router.rate_limiter import call_with_failover, AllTiersFailedError
from router.cache import check_cache, add_to_cache
from router.db import log_request, SessionLocal, RequestLog, ApiKey, UserConfig, ModelPricing
from router.auth import require_api_key, check_budget
from router.config import TIER_MARGIN, MODEL_CONFIG, SUPPORTED_PROVIDERS, ALLOWED_ORIGINS, TAVILY_API_KEY
from router.guardrails import is_prompt_injection, sanitize_pii, needs_web_search
from router.providers_registry import PROVIDERS_REGISTRY
from router.model_config_loader import get_active_config, get_pricing_for_model
from router.providers import validate_key

app = FastAPI()
executor = ThreadPoolExecutor()


app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    query: str
    override_tier: str | None = None
    user_api_keys: dict | None = None  # { tier: api_key } from localStorage, never stored
    bypass_cache: bool = False

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

    # web search check -- runs before cache/classifier, zero extra latency
    if needs_web_search(req.query) and TAVILY_API_KEY:
        start = time.time()
        try:
            import httpx
            resp = await asyncio.get_event_loop().run_in_executor(
                executor, lambda: httpx.post(
                    "https://api.tavily.com/search",
                    json={"api_key": TAVILY_API_KEY, "query": req.query, "search_depth": "advanced", "max_results": 5},
                    timeout=10,
                )
            )
            resp.raise_for_status()
            data = resp.json()
            answer = data.get("answer") or "\n\n".join(r["content"] for r in data.get("results", [])[:3])
        except Exception:
            pass  # fall through to normal routing
        else:
            latency_ms = round((time.time() - start) * 1000, 2)
            log_request({
                "api_key_id": api_key.id,
                "query": sanitize_pii(req.query),
                "difficulty_score": None,
                "intended_tier": "web",
                "tier": "web",
                "fallback_used": False,
                "cache_hit": False,
                "cache_similarity": None,
                "model_id": "tavily/search",
                "input_tokens": 0,
                "output_tokens": 0,
                "cost_usd": 0.0,
                "latency_ms": latency_ms,
            })
            return {
                "response": answer,
                "routed_to": "web",
                "intended_tier": "web",
                "predicted_tier": "web",
                "override_used": False,
                "budget_capped": False,
                "fallback_used": False,
                "cache_hit": False,
                "difficulty_score": None,
                "cost_usd": 0.0,
                "latency_ms": latency_ms,
            }

    start = time.time()
    loop = asyncio.get_event_loop()

    # 1. Run cache check and classifier in parallel
    async def _maybe_check_cache():
        if req.bypass_cache:
            return None
        return await loop.run_in_executor(executor, check_cache, req.query)

    cached, (difficulty_score, tier) = await asyncio.gather(
        _maybe_check_cache(),
        loop.run_in_executor(executor, get_tier, req.query, TIER_MARGIN),
    )

    if cached is not None:
        latency_ms = round((time.time() - start) * 1000, 2)
        price_in, price_out = get_pricing_for_model(cached["model_id"])
        tokens_saved_usd = round(
            (cached["input_tokens"] / 1_000_000 * price_in)
            + (cached["output_tokens"] / 1_000_000 * price_out),
            6,
        )
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
            "tokens_saved_usd": tokens_saved_usd,
        })
        return {
            "response": cached["response"],
            "routed_to": cached["tier"],
            "cache_hit": True,
            "cache_similarity": cached["similarity"],
            "cost_usd": 0.0,
            "tokens_saved_usd": tokens_saved_usd,
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
        result = await loop.run_in_executor(executor, call_with_failover, routing_tier, req.query, req.user_api_keys or {})
    except AllTiersFailedError as e:
        print(f"[route] AllTiersFailedError: {e}")  # full detail in server logs only
        raise HTTPException(status_code=503, detail="All model tiers failed to respond. Check your API keys or try again later.")

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
    loop.run_in_executor(executor, add_to_cache, req.query, result["text"], result["tier"], result["model_id"], result["cost_usd"], result["input_tokens"], result["output_tokens"])

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


@app.get("/pricing")
def get_pricing():
    """Returns all active model pricing rows for the frontend pricing table."""
    session = SessionLocal()
    try:
        rows = session.query(ModelPricing).filter(ModelPricing.is_active == True).order_by(ModelPricing.provider, ModelPricing.model_id).all()
        return [
            {
                "provider": r.provider,
                "model_id": r.model_id,
                "display_name": r.display_name,
                "price_per_m_input": r.price_per_m_input,
                "price_per_m_output": r.price_per_m_output,
                "notes": r.notes,
            }
            for r in rows
        ]
    finally:
        session.close()


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


KEY_VALIDATION_TIMEOUT = 5  # seconds -- provider test calls shouldn't take longer than this


@app.post("/config")
async def save_config(req: UserConfigRequest):
    """
    Saves user model config for each tier provided.
    1. Format-validates provider + model_id (via pydantic above)
    2. Makes a test call (max_tokens=1) to verify the key works, with a 5s timeout
    3. Saves provider + model_id to user_configs table (no api_key stored)
    API keys are returned to frontend to store in localStorage only.
    """
    tiers = {
        "cheap": req.cheap,
        "mid": req.mid,
        "frontier": req.frontier,
    }

    loop = asyncio.get_event_loop()
    results = {}
    session = SessionLocal()
    try:
        for tier, cfg in tiers.items():
            if cfg is None:
                continue

            # validate key with a real test call, bounded by timeout
            try:
                await asyncio.wait_for(
                    loop.run_in_executor(executor, validate_key, cfg.provider, cfg.model_id, cfg.api_key),
                    timeout=KEY_VALIDATION_TIMEOUT,
                )
            except asyncio.TimeoutError:
                raise HTTPException(
                    status_code=408,
                    detail=f"Key validation timed out for {tier} tier ({cfg.provider}/{cfg.model_id}) — provider took over {KEY_VALIDATION_TIMEOUT}s to respond"
                )
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Key validation failed for {tier} tier ({cfg.provider}/{cfg.model_id}): {e}"
                )

            # upsert: update existing row for this tier, or insert if none
            existing = session.query(UserConfig).filter(UserConfig.tier == tier).first()
            if existing:
                existing.provider = cfg.provider
                existing.model_id = cfg.model_id
                existing.updated_at = datetime.utcnow()
            else:
                session.add(UserConfig(tier=tier, provider=cfg.provider, model_id=cfg.model_id))
            results[tier] = {"provider": cfg.provider, "model_id": cfg.model_id, "status": "saved"}

        session.commit()
    finally:
        session.close()

    return {"saved": results}


@app.delete("/config")
def reset_config():
    """Clears all user config rows -- reverts all tiers to defaults."""
    session = SessionLocal()
    try:
        session.query(UserConfig).delete()
        session.commit()
    finally:
        session.close()
    return {"reset": True}


@app.get("/logs")
def get_logs(limit: int = 50, api_key: ApiKey = Depends(require_api_key)):
    """Returns the most recent request logs for the calling key only. limit capped at 100."""
    limit = min(limit, 100)
    session = SessionLocal()
    try:
        rows = (
            session.query(RequestLog)
            .filter(RequestLog.api_key_id == api_key.id)
            .order_by(RequestLog.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": r.id,
                "query": r.query,
                "tier": r.tier,
                "intended_tier": r.intended_tier,
                "model_id": r.model_id,
                "difficulty_score": r.difficulty_score,
                "cost_usd": r.cost_usd,
                "latency_ms": r.latency_ms,
                "cache_hit": r.cache_hit,
                "fallback_used": r.fallback_used,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    finally:
        session.close()


@app.get("/health")
def health():
    return {"status": "ok"}


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

        tier_costs = {
            tier: float(cost or 0.0)
            for tier, cost in session.query(RequestLog.tier, func.sum(RequestLog.cost_usd))
            .group_by(RequestLog.tier).all()
            if tier
        }

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

        cache_savings_usd = float(
            session.query(func.sum(RequestLog.tokens_saved_usd))
            .filter(RequestLog.cache_hit == True)
            .scalar() or 0.0
        )
        routing_savings_usd = max(0.0, round(total_hypothetical_cost - total_actual_cost, 6))
        total_savings_usd = round(cache_savings_usd + routing_savings_usd, 6)

        return {
            "total_requests": total_requests,
            "tier_counts": tier_counts,
            "tier_costs": tier_costs,
            "total_actual_cost": total_actual_cost,
            "total_hypothetical_cost": total_hypothetical_cost,
            "cache_hit_rate": cache_hit_rate,
            "fallback_count": fallback_count,
            "avg_latency_by_tier": avg_latency_by_tier,
            "daily_costs": daily_costs,
            "cache_savings_usd": cache_savings_usd,
            "routing_savings_usd": routing_savings_usd,
            "total_savings_usd": total_savings_usd,
        }
    finally:
        session.close()