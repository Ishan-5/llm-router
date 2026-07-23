import json
import time
import asyncio
import logging
import secrets
import ipaddress
import re
import httpx
from urllib.parse import urlparse
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
from sqlalchemy import func, String
from router.classifier import get_tier, score_difficulty
from predict_difficulty import predict_difficulty, score_to_tier
from router.rate_limiter import call_with_failover, AllTiersFailedError
from router.providers import stream_model, validate_key
from router.cache import check_cache, add_to_cache
from router.db import log_request, SessionLocal, RequestLog, ApiKey, UserConfig, UserSettings, ModelPricing, AlertRule, compute_quality_score
from router.auth import require_api_key, check_budget, require_user, require_admin, require_admin_api_key, require_admin_any, require_any_auth, is_admin_user_id, invalidate_key_cache
from router.config import TIER_MARGIN, MODEL_CONFIG, SUPPORTED_PROVIDERS, ALLOWED_ORIGINS, TAVILY_API_KEY, ADMIN_USER_ID, SUPABASE_URL, SUPABASE_SERVICE_KEY
from router.guardrails import is_prompt_injection, sanitize_pii, needs_web_search
from router.providers_registry import PROVIDERS_REGISTRY
from router.model_config_loader import get_active_config, get_pricing_for_model
from router.openai_compat import router as openai_compat_router

log = logging.getLogger("routewise")


# ------------------------------------------------------------------
# SSRF-safe webhook validator
# ------------------------------------------------------------------

_PRIVATE_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local / AWS metadata
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]


def _validate_webhook_url(url: str):
    """Raises ValueError if the URL is unsafe (SSRF risk)."""
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("Webhook URL must use https://")
    host = parsed.hostname
    if not host:
        raise ValueError("Invalid webhook URL")
    try:
        addr = ipaddress.ip_address(host)
        for net in _PRIVATE_RANGES:
            if addr in net:
                raise ValueError("Webhook URL must not point to a private/internal address")
    except ValueError as e:
        if "private" in str(e) or "internal" in str(e):
            raise
        # hostname, not IP — do a basic check for localhost
        if host.lower() in ("localhost", "metadata.google.internal"):
            raise ValueError("Webhook URL must not point to a private/internal address")


# ------------------------------------------------------------------
# Alert checker
# ------------------------------------------------------------------

ALERT_COOLDOWN_SECONDS = 3600  # 1 hour between repeat alerts


def _check_and_fire_alerts():
    """Check all active alert rules and fire webhooks if thresholds are breached."""
    session = SessionLocal()
    try:
        rules = session.query(AlertRule).filter(AlertRule.is_active == True).all()
        if not rules:
            return

        now = datetime.utcnow()
        today_start = datetime.combine(now.date(), datetime.min.time())
        hour_ago = now - timedelta(hours=1)

        for rule in rules:
            # cooldown check
            if rule.last_fired_at and (now - rule.last_fired_at).total_seconds() < ALERT_COOLDOWN_SECONDS:
                continue

            breached = False
            payload = {"alert_type": rule.alert_type, "threshold": rule.threshold}

            if rule.alert_type == "daily_spend":
                key_ids = [k.id for k in session.query(ApiKey.id).filter(func.cast(ApiKey.user_id, String) == rule.user_id, ApiKey.is_active == True).all()]
                spent = float(session.query(func.sum(RequestLog.cost_usd)).filter(
                    RequestLog.api_key_id.in_(key_ids),
                    RequestLog.created_at >= today_start,
                ).scalar() or 0.0)
                payload["current_value"] = round(spent, 6)
                payload["message"] = f"Daily spend ${spent:.4f} exceeded threshold ${rule.threshold:.4f}"
                breached = spent >= rule.threshold

            elif rule.alert_type == "error_rate":
                key_ids = [k.id for k in session.query(ApiKey.id).filter(func.cast(ApiKey.user_id, String) == rule.user_id, ApiKey.is_active == True).all()]
                total = session.query(func.count(RequestLog.id)).filter(
                    RequestLog.api_key_id.in_(key_ids),
                    RequestLog.created_at >= hour_ago,
                ).scalar() or 0
                errors = session.query(func.count(RequestLog.id)).filter(
                    RequestLog.api_key_id.in_(key_ids),
                    RequestLog.created_at >= hour_ago,
                    RequestLog.tier == "failed",
                ).scalar() or 0
                rate = (errors / total * 100) if total > 0 else 0.0
                payload["current_value"] = round(rate, 2)
                payload["message"] = f"Error rate {rate:.1f}% exceeded threshold {rule.threshold:.1f}%"
                breached = rate >= rule.threshold

            elif rule.alert_type == "latency":
                key_ids = [k.id for k in session.query(ApiKey.id).filter(func.cast(ApiKey.user_id, String) == rule.user_id, ApiKey.is_active == True).all()]
                avg_latency = float(session.query(func.avg(RequestLog.latency_ms)).filter(
                    RequestLog.api_key_id.in_(key_ids),
                    RequestLog.created_at >= hour_ago,
                    RequestLog.tier != "failed",
                ).scalar() or 0.0)
                payload["current_value"] = round(avg_latency, 1)
                payload["message"] = f"Avg latency {avg_latency:.0f}ms exceeded threshold {rule.threshold:.0f}ms"
                breached = avg_latency >= rule.threshold

            if breached:
                try:
                    httpx.post(rule.webhook_url, json=payload, timeout=5, follow_redirects=False)
                    rule.last_fired_at = now
                    session.commit()
                    log.info("Alert fired: %s for user %s", rule.alert_type, rule.user_id)
                except Exception as e:
                    log.warning("Webhook delivery failed for rule %s: %s", rule.id, e)
    except Exception as e:
        log.warning("Alert checker error: %s", e)
    finally:
        session.close()


@asynccontextmanager
async def lifespan(app):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    try:
        import sys
        sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent.parent / 'src'))
        from predict_difficulty import preload_models
        preload_models()
        log.info("ML models loaded successfully")
    except Exception as e:
        log.warning("ML model preload failed: %s", e)

    async def _alert_loop():
        while True:
            await asyncio.sleep(300)
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(executor, _check_and_fire_alerts)
                log.info("Alert check completed")
            except Exception as e:
                log.warning("Alert loop error: %s", e)

    task = asyncio.create_task(_alert_loop())
    yield
    task.cancel()


app = FastAPI(lifespan=lifespan)
executor = ThreadPoolExecutor()

app.include_router(openai_compat_router)


app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "DELETE", "HEAD"],
    allow_headers=["*"],
)


DEFAULT_THRESHOLD = 1.0


def load_user_threshold(user_id: str | None) -> float:
    if not user_id:
        return DEFAULT_THRESHOLD
    session = SessionLocal()
    try:
        settings = session.query(UserSettings).filter(UserSettings.user_id == user_id).first()
        return settings.router_threshold if settings else DEFAULT_THRESHOLD
    finally:
        session.close()


class QueryRequest(BaseModel):
    query: str
    override_tier: str | None = None
    user_api_keys: dict | None = None
    bypass_cache: bool = False
    threshold: float | None = None

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

    @field_validator("threshold")
    @classmethod
    def validate_threshold(cls, v):
        if v is not None and (v < 0.0 or v > 2.0):
            raise ValueError("threshold must be between 0.0 and 2.0")
        return v


async def _preprocess(req: QueryRequest, api_key: ApiKey, start: float):
    """
    Shared pre-processing for both /route and /route/stream.
    Returns one of three dicts:
      {"type": "web",   "answer": str, "latency_ms": float, "quality_score": float}
      {"type": "cache", "cached": dict, "tokens_saved_usd": float, "latency_ms": float, "quality_score": float}
      {"type": "live",  "tier": str, "difficulty_score": float, "over_budget": bool, "user_config": dict, "threshold": float}
    """
    loop = asyncio.get_event_loop()

    threshold = req.threshold if req.threshold is not None else load_user_threshold(api_key.user_id)

    # web search -- runs before cache/classifier
    if needs_web_search(req.query) and TAVILY_API_KEY:
        try:
            import httpx
            resp = await loop.run_in_executor(
                executor, lambda: httpx.post(
                    "https://api.tavily.com/search",
                    json={"api_key": TAVILY_API_KEY, "query": req.query, "search_depth": "advanced", "max_results": 5, "include_answer": True},
                    timeout=10,
                )
            )
            resp.raise_for_status()
            data = resp.json()
            answer = data.get("answer") or (
                "\n\n".join(r["content"][:300] for r in data.get("results", [])[:3])
                + "\n\n[web results truncated — showing first 300 chars per source]"
            )
        except Exception as e:
            log.debug("Web search failed, falling through to normal routing: %s", e)
        else:
            latency_ms = round((time.time() - start) * 1000, 2)
            log_request({
                "api_key_id": api_key.id, "user_id": api_key.user_id,
                "query": sanitize_pii(req.query),
                "response": answer,
                "difficulty_score": None, "intended_tier": "web", "tier": "web",
                "fallback_used": False, "cache_hit": False, "cache_similarity": None,
                "model_id": "tavily/search", "input_tokens": 0, "output_tokens": 0,
                "cost_usd": 0.0, "latency_ms": latency_ms,
                "quality_score": 1.0,
            })
            return {"type": "web", "answer": answer, "latency_ms": latency_ms, "quality_score": 1.0}

    # cache check + classifier in parallel
    async def _maybe_check_cache():
        if req.bypass_cache:
            return None
        return await loop.run_in_executor(executor, check_cache, req.query)

    cached, (difficulty_score, tier, cheap_ceil, frontier_floor) = await asyncio.gather(
        _maybe_check_cache(),
        loop.run_in_executor(executor, get_tier, req.query, threshold),
    )

    if cached is not None:
        latency_ms = round((time.time() - start) * 1000, 2)
        price_in, price_out = get_pricing_for_model(cached["model_id"])
        tokens_saved_usd = round(
            (cached["input_tokens"] / 1_000_000 * price_in)
            + (cached["output_tokens"] / 1_000_000 * price_out), 6)
        quality_score = compute_quality_score(cache_hit=True, cache_similarity=cached["similarity"], fallback_used=False)
        log_request({
            "api_key_id": api_key.id, "user_id": api_key.user_id,
            "query": sanitize_pii(req.query),
            "response": cached["response"],
            "difficulty_score": None, "intended_tier": cached["tier"], "tier": cached["tier"],
            "fallback_used": False, "cache_hit": True, "cache_similarity": cached["similarity"],
            "model_id": cached["model_id"], "input_tokens": 0, "output_tokens": 0,
            "cost_usd": 0.0, "latency_ms": latency_ms, "tokens_saved_usd": tokens_saved_usd,
            "quality_score": quality_score,
        })
        return {"type": "cache", "cached": cached, "tokens_saved_usd": tokens_saved_usd, "latency_ms": latency_ms, "quality_score": quality_score}

    # live model call -- resolve tier + budget
    routing_tier = req.override_tier if req.override_tier else tier
    over_budget = not check_budget(api_key)
    if over_budget:
        routing_tier = "cheap"

    user_config = get_active_config(api_key.user_id)
    if req.user_api_keys:
        for t, key in req.user_api_keys.items():
            if t in user_config and key:
                user_config[t]["api_key"] = key

    return {
        "type": "live",
        "tier": routing_tier,
        "difficulty_score": difficulty_score,
        "predicted_tier": tier,
        "over_budget": over_budget,
        "user_config": user_config,
        "threshold": threshold,
        "cheap_ceil": cheap_ceil,
        "frontier_floor": frontier_floor,
    }


@app.post("/route")
async def route_query(req: QueryRequest, api_key: ApiKey = Depends(require_api_key)):
    if is_prompt_injection(req.query):
        raise HTTPException(status_code=400, detail="Prompt injection detected")

    start = time.time()
    pre = await _preprocess(req, api_key, start)

    if pre["type"] == "web":
        return {
            "response": pre["answer"], "routed_to": "web", "intended_tier": "web",
            "predicted_tier": "web", "override_used": False, "budget_capped": False,
            "fallback_used": False, "cache_hit": False, "difficulty_score": None,
            "cost_usd": 0.0, "latency_ms": pre["latency_ms"],
        }

    if pre["type"] == "cache":
        cached = pre["cached"]
        return {
            "response": cached["response"], "routed_to": cached["tier"],
            "cache_hit": True, "cache_similarity": cached["similarity"],
            "cost_usd": 0.0, "tokens_saved_usd": pre["tokens_saved_usd"],
            "latency_ms": pre["latency_ms"],
        }

    # live
    routing_tier = pre["tier"]
    difficulty_score = pre["difficulty_score"]
    over_budget = pre["over_budget"]
    loop = asyncio.get_event_loop()

    try:
        result = await loop.run_in_executor(executor, call_with_failover, routing_tier, req.query, req.user_api_keys or {})
    except AllTiersFailedError as e:
        log.error("AllTiersFailedError: %s", e)
        log_request({
            "api_key_id": api_key.id, "user_id": api_key.user_id,
            "query": sanitize_pii(req.query),
            "response": None,
            "difficulty_score": difficulty_score, "intended_tier": routing_tier,
            "tier": "failed", "fallback_used": False,
            "cache_hit": False, "cache_similarity": None, "model_id": None,
            "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
            "latency_ms": round((time.time() - start) * 1000, 2),
            "quality_score": 0.0,
        })
        raise HTTPException(status_code=503, detail="All model tiers failed to respond. Check your API keys or try again later.")

    latency_ms = round((time.time() - start) * 1000, 2)
    quality_score = compute_quality_score(cache_hit=False, cache_similarity=None, fallback_used=result["fallback_used"])
    log_request({
        "api_key_id": api_key.id, "user_id": api_key.user_id,
        "query": sanitize_pii(req.query),
        "response": result["text"],
        "difficulty_score": difficulty_score, "intended_tier": result["intended_tier"],
        "tier": result["tier"], "fallback_used": result["fallback_used"],
        "cache_hit": False, "cache_similarity": None, "model_id": result["model_id"],
        "input_tokens": result["input_tokens"], "output_tokens": result["output_tokens"],
        "cost_usd": result["cost_usd"],
        "latency_ms": result["latency_ms"] if "latency_ms" in result else latency_ms,
        "quality_score": quality_score,
    })
    loop.run_in_executor(executor, add_to_cache, req.query, result["text"], result["tier"], result["model_id"], result["cost_usd"], result["input_tokens"], result["output_tokens"])
    return {
        "response": result["text"], "routed_to": result["tier"],
        "intended_tier": result["intended_tier"], "predicted_tier": pre["predicted_tier"],
        "override_used": req.override_tier is not None, "budget_capped": over_budget,
        "fallback_used": result["fallback_used"], "cache_hit": False,
        "difficulty_score": difficulty_score, "cost_usd": result["cost_usd"],
        "latency_ms": latency_ms, "quality_score": quality_score,
        "cheap_ceil": pre["cheap_ceil"], "frontier_floor": pre["frontier_floor"],
    }


@app.post("/route/stream")
async def route_query_stream(req: QueryRequest, api_key: ApiKey = Depends(require_api_key)):
    if is_prompt_injection(req.query):
        raise HTTPException(status_code=400, detail="Prompt injection detected")

    start = time.time()
    pre = await _preprocess(req, api_key, start)

    if pre["type"] == "web":
        answer = pre["answer"]
        latency_ms = pre["latency_ms"]
        async def _web_stream():
            yield f"data: {json.dumps({'type': 'meta', 'routed_to': 'web', 'cache_hit': False, 'cost_usd': 0.0, 'latency_ms': latency_ms})}\n\n"
            yield f"data: {json.dumps({'type': 'chunk', 'text': answer})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return StreamingResponse(_web_stream(), media_type="text/event-stream")

    if pre["type"] == "cache":
        cached = pre["cached"]
        tokens_saved_usd = pre["tokens_saved_usd"]
        latency_ms = pre["latency_ms"]
        async def _cache_stream():
            yield f"data: {json.dumps({'type': 'meta', 'routed_to': cached['tier'], 'cache_hit': True, 'cache_similarity': cached['similarity'], 'cost_usd': 0.0, 'tokens_saved_usd': tokens_saved_usd, 'latency_ms': latency_ms})}\n\n"
            yield f"data: {json.dumps({'type': 'chunk', 'text': cached['response']})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return StreamingResponse(_cache_stream(), media_type="text/event-stream")

    # live
    routing_tier = pre["tier"]
    difficulty_score = pre["difficulty_score"]
    over_budget = pre["over_budget"]
    user_config = pre["user_config"]
    loop = asyncio.get_event_loop()

    async def _live_stream():
        full_text = []
        meta = None
        queue = asyncio.Queue()

        def _run_generator():
            try:
                for item in stream_model(routing_tier, req.query, user_config.get(routing_tier)):
                    loop.call_soon_threadsafe(queue.put_nowait, item)
            except Exception as e:
                loop.call_soon_threadsafe(queue.put_nowait, Exception(str(e)))
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)  # sentinel

        loop.run_in_executor(executor, _run_generator)

        while True:
            item = await queue.get()
            if item is None:
                break
            if isinstance(item, Exception):
                yield f"data: {json.dumps({'type': 'error', 'detail': str(item)})}\n\n"
                return
            if isinstance(item, dict):
                meta = item
            else:
                full_text.append(item)
                yield f"data: {json.dumps({'type': 'chunk', 'text': item})}\n\n"

        if meta is None:
            yield f"data: {json.dumps({'type': 'error', 'detail': 'No response from model'})}\n\n"
            return

        latency_ms = round((time.time() - start) * 1000, 2)
        full_response = "".join(full_text)
        quality_score = compute_quality_score(cache_hit=False, cache_similarity=None, fallback_used=False)

        log_request({"api_key_id": api_key.id, "user_id": api_key.user_id, "query": sanitize_pii(req.query),
            "response": full_response,
            "difficulty_score": difficulty_score, "intended_tier": routing_tier,
            "tier": meta["tier"], "fallback_used": False, "cache_hit": False,
            "cache_similarity": None, "model_id": meta["model_id"],
            "input_tokens": meta["input_tokens"], "output_tokens": meta["output_tokens"],
            "cost_usd": meta["cost_usd"], "latency_ms": latency_ms,
            "quality_score": quality_score})

        loop.run_in_executor(executor, add_to_cache, req.query, full_response,
            meta["tier"], meta["model_id"], meta["cost_usd"],
            meta["input_tokens"], meta["output_tokens"])

        yield f"data: {json.dumps({'type': 'done', 'routed_to': meta['tier'], 'intended_tier': routing_tier, 'predicted_tier': pre['predicted_tier'], 'override_used': req.override_tier is not None, 'budget_capped': over_budget, 'fallback_used': False, 'cache_hit': False, 'difficulty_score': difficulty_score, 'cost_usd': meta['cost_usd'], 'latency_ms': latency_ms, 'quality_score': quality_score})}\n\n"

    return StreamingResponse(_live_stream(), media_type="text/event-stream")


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
def get_config(authorization: str | None = Header(default=None)):
    """Returns active model config. If a valid user JWT is provided, returns that user's config. Otherwise returns defaults."""
    user_id = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        try:
            resp = httpx.get(
                f"{SUPABASE_URL}/auth/v1/user",
                headers={"Authorization": f"Bearer {token}", "apikey": SUPABASE_SERVICE_KEY},
                timeout=5,
            )
            if resp.status_code == 200:
                user_id = resp.json()["id"]
        except Exception as e:
            log.debug("JWT verification failed for /config: %s", e)
    config = get_active_config(user_id)
    return {
        tier: {k: v for k, v in cfg.items() if k != "api_key"}
        for tier, cfg in config.items()
    }


KEY_VALIDATION_TIMEOUT = 5


@app.post("/config")
async def save_config(req: UserConfigRequest, user_id: str = Depends(require_user)):
    """Saves BYOM config per tier for the calling user."""
    tiers = {"cheap": req.cheap, "mid": req.mid, "frontier": req.frontier}
    loop = asyncio.get_event_loop()
    results = {}
    session = SessionLocal()
    try:
        for tier, cfg in tiers.items():
            if cfg is None:
                continue
            try:
                await asyncio.wait_for(
                    loop.run_in_executor(executor, validate_key, cfg.provider, cfg.model_id, cfg.api_key),
                    timeout=KEY_VALIDATION_TIMEOUT,
                )
            except asyncio.TimeoutError:
                raise HTTPException(status_code=408, detail=f"Key validation timed out for {tier} tier")
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Key validation failed for {tier} tier: {e}")

            existing = session.query(UserConfig).filter(
                UserConfig.user_id == user_id, UserConfig.tier == tier
            ).first()
            if existing:
                existing.provider = cfg.provider
                existing.model_id = cfg.model_id
                existing.updated_at = datetime.utcnow()
            else:
                session.add(UserConfig(user_id=user_id, tier=tier, provider=cfg.provider, model_id=cfg.model_id))
            results[tier] = {"provider": cfg.provider, "model_id": cfg.model_id, "status": "saved"}
        session.commit()
    finally:
        session.close()
    return {"saved": results}


@app.delete("/config")
def reset_config(user_id: str = Depends(require_user)):
    """Clears BYOM config for the calling user only."""
    session = SessionLocal()
    try:
        session.query(UserConfig).filter(UserConfig.user_id == user_id).delete()
        session.commit()
    finally:
        session.close()
    return {"reset": True}


@app.get("/keys")
def get_keys(user_id: str = Depends(require_user)):
    """Returns all active API keys for the calling user."""
    session = SessionLocal()
    try:
        rows = session.query(ApiKey).filter(ApiKey.user_id == user_id, ApiKey.is_active == True).all()
        return [{"id": r.id, "key": r.key, "name": r.name, "created_at": r.created_at.isoformat()} for r in rows]
    finally:
        session.close()


class KeyCreateRequest(BaseModel):
    name: str


@app.post("/keys")
def create_key(req: KeyCreateRequest, user_id: str = Depends(require_user)):
    """Generates a new API key for the calling user."""
    key = "rw_" + secrets.token_urlsafe(32)
    session = SessionLocal()
    try:
        record = ApiKey(key=key, name=req.name.strip(), user_id=user_id)
        session.add(record)
        session.commit()
        return {"key": key, "name": record.name, "created_at": record.created_at.isoformat()}
    finally:
        session.close()


@app.delete("/keys/{key_id}")
def revoke_key(key_id: int, user_id: str = Depends(require_user)):
    """Revokes an API key. Only the owning user can revoke their own keys."""
    session = SessionLocal()
    try:
        record = session.query(ApiKey).filter(ApiKey.id == key_id, ApiKey.user_id == user_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="Key not found")
        record.is_active = False
        session.commit()
        invalidate_key_cache(record.key)
    finally:
        session.close()
    return {"revoked": key_id}


@app.get("/logs")
def get_logs(limit: int = 50, api_key: ApiKey = Depends(require_api_key)):
    """Returns the most recent request logs for the calling key only. limit capped at 100."""
    limit = max(1, min(limit, 100))
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
                "response": (r.response[:500] + "...") if r.response and len(r.response) > 500 else r.response,
                "tier": r.tier,
                "intended_tier": r.intended_tier,
                "model_id": r.model_id,
                "difficulty_score": r.difficulty_score,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "cost_usd": r.cost_usd,
                "latency_ms": r.latency_ms,
                "cache_hit": r.cache_hit,
                "cache_similarity": r.cache_similarity,
                "fallback_used": r.fallback_used,
                "tokens_saved_usd": r.tokens_saved_usd,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    finally:
        session.close()


@app.get("/logs/{log_id}")
def get_log_detail(log_id: int, api_key: ApiKey = Depends(require_api_key)):
    """Returns the full detail of a single log entry. Only accessible by the owning key."""
    session = SessionLocal()
    try:
        r = session.query(RequestLog).filter(RequestLog.id == log_id, RequestLog.api_key_id == api_key.id).first()
        if not r:
            raise HTTPException(status_code=404, detail="Log entry not found")
        return {
            "id": r.id,
            "query": r.query,
            "response": r.response,
            "tier": r.tier,
            "intended_tier": r.intended_tier,
            "model_id": r.model_id,
            "difficulty_score": r.difficulty_score,
            "input_tokens": r.input_tokens,
            "output_tokens": r.output_tokens,
            "cost_usd": r.cost_usd,
            "latency_ms": r.latency_ms,
            "cache_hit": r.cache_hit,
            "cache_similarity": r.cache_similarity,
            "fallback_used": r.fallback_used,
            "tokens_saved_usd": r.tokens_saved_usd,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
    finally:
        session.close()


@app.api_route("/health", methods=["GET", "HEAD"])
def health():
    return {"status": "ok"}


@app.get("/stats")
def get_stats(api_key: ApiKey = Depends(require_api_key)):
    """
    Aggregates real logged requests for the dashboard.
    If the calling key belongs to the admin user → global stats (all keys).
    Otherwise → scoped to the calling key only.
    """
    session = SessionLocal()
    try:
        is_admin = is_admin_user_id(api_key.user_id)
        base_filter = [] if is_admin else [RequestLog.api_key_id == api_key.id]

        total_requests = session.query(func.count(RequestLog.id)).filter(*base_filter).scalar() or 0

        tier_counts = dict(
            session.query(RequestLog.tier, func.count(RequestLog.id))
            .filter(*base_filter)
            .group_by(RequestLog.tier).all()
        )

        tier_costs = {
            tier: float(cost or 0.0)
            for tier, cost in session.query(RequestLog.tier, func.sum(RequestLog.cost_usd))
            .filter(*base_filter)
            .group_by(RequestLog.tier).all()
            if tier
        }

        total_actual_cost = float(session.query(func.sum(RequestLog.cost_usd)).filter(*base_filter).scalar() or 0.0)

        cache_hits = session.query(func.count(RequestLog.id)).filter(RequestLog.cache_hit == True, *base_filter).scalar() or 0
        cache_hit_rate = (cache_hits / total_requests) if total_requests else 0.0

        fallback_count = session.query(func.count(RequestLog.id)).filter(RequestLog.fallback_used == True, *base_filter).scalar() or 0

        frontier_cfg = MODEL_CONFIG["frontier"]
        token_rows = session.query(RequestLog.input_tokens, RequestLog.output_tokens, RequestLog.created_at).filter(*base_filter).all()

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
            session.query(RequestLog.tier, func.avg(RequestLog.latency_ms)).filter(*base_filter).group_by(RequestLog.tier).all()
            if tier and avg is not None
        }

        daily_actual = session.query(
            func.date(RequestLog.created_at).label("day"),
            func.sum(RequestLog.cost_usd),
        ).filter(*base_filter).group_by("day").order_by("day").all()

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
            .filter(RequestLog.cache_hit == True, *base_filter)
            .scalar() or 0.0
        )
        routing_savings_usd = max(0.0, round(total_hypothetical_cost - total_actual_cost, 6))
        total_savings_usd = round(cache_savings_usd + routing_savings_usd, 6)

        average_quality = float(
            session.query(func.avg(RequestLog.quality_score))
            .filter(*base_filter, RequestLog.quality_score.isnot(None))
            .scalar() or 0.0
        )

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
            "average_quality": round(average_quality, 4),
            "is_global": is_admin,
        }
    finally:
        session.close()


@app.get("/analytics")
def get_analytics(api_key: ApiKey = Depends(require_api_key)):
    """Detailed cost analytics for the dashboard. Scoped to the calling key."""
    session = SessionLocal()
    try:
        base_filter = [RequestLog.api_key_id == api_key.id]

        total_requests = session.query(func.count(RequestLog.id)).filter(*base_filter).scalar() or 0

        # Cost by tier
        tier_costs = dict(
            session.query(RequestLog.tier, func.sum(RequestLog.cost_usd))
            .filter(*base_filter)
            .group_by(RequestLog.tier).all()
        )

        # Cost by model
        model_costs = dict(
            session.query(RequestLog.model_id, func.sum(RequestLog.cost_usd))
            .filter(*base_filter)
            .group_by(RequestLog.model_id).all()
        )

        # Token usage by tier
        tier_tokens = {}
        for tier, in_tok, out_tok in session.query(
            RequestLog.tier,
            func.sum(RequestLog.input_tokens),
            func.sum(RequestLog.output_tokens),
        ).filter(*base_filter).group_by(RequestLog.tier).all():
            tier_tokens[tier] = {"input": in_tok or 0, "output": out_tok or 0}

        # Daily costs (last 30 days)
        daily_rows = session.query(
            func.date(RequestLog.created_at).label("day"),
            func.sum(RequestLog.cost_usd),
            func.count(RequestLog.id),
            func.avg(RequestLog.latency_ms),
        ).filter(*base_filter).group_by("day").order_by(func.date(RequestLog.created_at).desc()).limit(30).all()

        daily = [
            {
                "date": str(day),
                "cost": float(cost or 0),
                "requests": count,
                "avg_latency": round(float(avg or 0), 1),
            }
            for day, cost, count, avg in reversed(daily_rows)
        ]

        # Cache stats
        cache_hits = session.query(func.count(RequestLog.id)).filter(
            *base_filter, RequestLog.cache_hit == True
        ).scalar() or 0
        cache_savings = float(
            session.query(func.sum(RequestLog.tokens_saved_usd)).filter(
                *base_filter, RequestLog.cache_hit == True
            ).scalar() or 0.0
        )

        # Fallback rate
        fallbacks = session.query(func.count(RequestLog.id)).filter(
            *base_filter, RequestLog.fallback_used == True
        ).scalar() or 0

        # Avg latency by tier
        latency_by_tier = dict(
            session.query(RequestLog.tier, func.avg(RequestLog.latency_ms))
            .filter(*base_filter)
            .group_by(RequestLog.tier).all()
        )

        # Top 5 most expensive requests
        top_expensive = session.query(
            RequestLog.id, RequestLog.query, RequestLog.tier, RequestLog.model_id,
            RequestLog.cost_usd, RequestLog.input_tokens, RequestLog.output_tokens,
            RequestLog.created_at,
        ).filter(*base_filter).order_by(RequestLog.cost_usd.desc()).limit(5).all()

        top_expensive_list = [
            {
                "id": r.id,
                "query": r.query[:100] + "..." if r.query and len(r.query) > 100 else r.query,
                "tier": r.tier,
                "model": r.model_id,
                "cost": float(r.cost_usd or 0),
                "tokens": (r.input_tokens or 0) + (r.output_tokens or 0),
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in top_expensive
        ]

        # Total actual cost
        total_cost = float(session.query(func.sum(RequestLog.cost_usd)).filter(*base_filter).scalar() or 0.0)

        # Hypothetical cost (if everything went to frontier)
        frontier_cfg = MODEL_CONFIG["frontier"]
        token_rows = session.query(RequestLog.input_tokens, RequestLog.output_tokens).filter(*base_filter).all()
        hypothetical = sum(
            (in_tok or 0) / 1_000_000 * frontier_cfg["price_per_m_input"]
            + (out_tok or 0) / 1_000_000 * frontier_cfg["price_per_m_output"]
            for in_tok, out_tok in token_rows
        )

        return {
            "summary": {
                "total_requests": total_requests,
                "total_cost": round(total_cost, 6),
                "hypothetical_cost": round(hypothetical, 6),
                "savings": round(max(0, hypothetical - total_cost), 6),
                "savings_pct": round((1 - total_cost / hypothetical) * 100, 1) if hypothetical > 0 else 0,
                "cache_hit_rate": round(cache_hits / total_requests * 100, 1) if total_requests else 0,
                "cache_savings": round(cache_savings, 6),
                "fallback_rate": round(fallbacks / total_requests * 100, 1) if total_requests else 0,
            },
            "tier_costs": {k: round(float(v or 0), 6) for k, v in tier_costs.items()},
            "model_costs": {k: round(float(v or 0), 6) for k, v in model_costs.items()},
            "tier_tokens": tier_tokens,
            "daily": daily,
            "latency_by_tier": {k: round(float(v or 0), 1) for k, v in latency_by_tier.items()},
            "top_expensive": top_expensive_list,
        }
    finally:
        session.close()


@app.get("/settings")
def get_settings(user_id: str = Depends(require_user)):
    session = SessionLocal()
    try:
        settings = session.query(UserSettings).filter(UserSettings.user_id == user_id).first()
        if settings is None:
            return {"router_threshold": DEFAULT_THRESHOLD}
        return {"router_threshold": settings.router_threshold}
    finally:
        session.close()


class SettingsRequest(BaseModel):
    router_threshold: float

    @field_validator("router_threshold")
    @classmethod
    def validate_threshold(cls, v):
        if v < 0.0 or v > 2.0:
            raise ValueError("router_threshold must be between 0.0 and 2.0")
        return v


@app.post("/settings")
def save_settings(req: SettingsRequest, user_id: str = Depends(require_user)):
    session = SessionLocal()
    try:
        settings = session.query(UserSettings).filter(UserSettings.user_id == user_id).first()
        if settings:
            settings.router_threshold = req.router_threshold
            settings.updated_at = datetime.utcnow()
        else:
            session.add(UserSettings(user_id=user_id, router_threshold=req.router_threshold))
        session.commit()
        return {"router_threshold": req.router_threshold}
    finally:
        session.close()


@app.get("/calibrate")
def calibrate(auth=Depends(require_any_auth)):
    session = SessionLocal()
    try:
        if auth["type"] == "api_key" and auth["record"]:
            base_filter = [RequestLog.api_key_id == auth["record"].id, RequestLog.cache_hit == False, RequestLog.tier != "web", RequestLog.difficulty_score.isnot(None)]
        else:
            key_ids = [k.id for k in session.query(ApiKey.id).filter(ApiKey.user_id == auth["user_id"], ApiKey.is_active == True).all()]
            if not key_ids:
                return {"message": "No API keys found. Create one in Settings first.", "modes": []}
            base_filter = [RequestLog.api_key_id.in_(key_ids), RequestLog.cache_hit == False, RequestLog.tier != "web", RequestLog.difficulty_score.isnot(None)]
        rows = session.query(RequestLog.difficulty_score, RequestLog.input_tokens, RequestLog.output_tokens).filter(*base_filter).order_by(RequestLog.created_at.desc()).limit(200).all()

        if not rows:
            return {"message": "Not enough data yet. Send some routed requests first.", "recommendation": None}

        margins = [("economy", 0.0), ("balanced", 1.0), ("quality", 2.0)]
        results = []
        for mode_name, margin in margins:
            cheap_count = mid_count = frontier_count = 0
            total_cost = 0.0
            for score, in_tok, out_tok in rows:
                tier, _, _ = score_to_tier(score, margin=margin)
                if tier == "frontier":
                    frontier_count += 1
                    tier_prices = MODEL_CONFIG["frontier"]
                elif tier == "cheap":
                    cheap_count += 1
                    tier_prices = MODEL_CONFIG["cheap"]
                else:
                    mid_count += 1
                    tier_prices = MODEL_CONFIG["mid"]
                total_cost += (in_tok or 0) / 1_000_000 * tier_prices["price_per_m_input"]
                total_cost += (out_tok or 0) / 1_000_000 * tier_prices["price_per_m_output"]

            frontier_cost = sum(
                (in_tok or 0) / 1_000_000 * MODEL_CONFIG["frontier"]["price_per_m_input"]
                + (out_tok or 0) / 1_000_000 * MODEL_CONFIG["frontier"]["price_per_m_output"]
                for _, in_tok, out_tok in rows
            )
            savings_pct = round((1 - total_cost / frontier_cost) * 100, 1) if frontier_cost > 0 else 0
            results.append({
                "mode": mode_name,
                "margin": margin,
                "cheap_pct": round(cheap_count / len(rows) * 100, 1),
                "mid_pct": round(mid_count / len(rows) * 100, 1),
                "frontier_pct": round(frontier_count / len(rows) * 100, 1),
                "estimated_cost": round(total_cost, 6),
                "savings_pct": savings_pct,
            })

        return {"analyzed_requests": len(rows), "modes": results}
    finally:
        session.close()


class EvaluateRequest(BaseModel):
    queries: list[str]


@app.post("/evaluate")
def evaluate(req: EvaluateRequest):
    margins = [("economy", 0.0), ("balanced", 1.0), ("quality", 2.0)]
    results = []
    for q in req.queries:
        score = predict_difficulty(q)
        entry = {"query": q, "difficulty_score": round(score, 4)}
        for mode_name, margin in margins:
            entry[f"tier_{mode_name}"] = score_to_tier(score, margin=margin)[0]
        results.append(entry)
    thresholds = [
        {"mode": "economy",  "cheap_below": 3.475, "frontier_above": 4.9},
        {"mode": "balanced", "cheap_below": 3.4,   "frontier_above": 4.6},
        {"mode": "quality",  "cheap_below": 3.325, "frontier_above": 4.3},
    ]
    return {"results": results, "thresholds": thresholds}


@app.get("/compare")
def compare(auth=Depends(require_any_auth)):
    session = SessionLocal()
    try:
        if auth["type"] == "api_key" and auth["record"]:
            base_filter = [RequestLog.api_key_id == auth["record"].id, RequestLog.cache_hit == False, RequestLog.tier != "web", RequestLog.difficulty_score.isnot(None)]
        else:
            key_ids = [k.id for k in session.query(ApiKey.id).filter(ApiKey.user_id == auth["user_id"], ApiKey.is_active == True).all()]
            if not key_ids:
                return {"message": "No API keys found.", "modes": []}
            base_filter = [RequestLog.api_key_id.in_(key_ids), RequestLog.cache_hit == False, RequestLog.tier != "web", RequestLog.difficulty_score.isnot(None)]
        rows = session.query(RequestLog.difficulty_score, RequestLog.input_tokens, RequestLog.output_tokens, RequestLog.created_at).filter(*base_filter).order_by(RequestLog.created_at.desc()).limit(500).all()

        if not rows:
            return {"message": "Not enough data.", "modes": []}

        ranges = [("economy", 0.0), ("balanced", 1.0), ("quality", 2.0)]
        results = []
        for mode_name, margin in ranges:
            total_cost = 0.0
            for score, in_tok, out_tok, _ in rows:
                tier, _, _ = score_to_tier(score, margin=margin)
                if tier == "frontier":
                    tier_prices = MODEL_CONFIG["frontier"]
                elif tier == "cheap":
                    tier_prices = MODEL_CONFIG["cheap"]
                else:
                    tier_prices = MODEL_CONFIG["mid"]
                total_cost += (in_tok or 0) / 1_000_000 * tier_prices["price_per_m_input"]
                total_cost += (out_tok or 0) / 1_000_000 * tier_prices["price_per_m_output"]

            baseline_cost = sum(
                (in_tok or 0) / 1_000_000 * MODEL_CONFIG["frontier"]["price_per_m_input"]
                + (out_tok or 0) / 1_000_000 * MODEL_CONFIG["frontier"]["price_per_m_output"]
                for _, in_tok, out_tok, _ in rows
            )
            savings_vs_frontier = round((1 - total_cost / baseline_cost) * 100, 1) if baseline_cost > 0 else 0
            results.append({
                "mode": mode_name,
                "margin": margin,
                "estimated_cost": round(total_cost, 6),
                "frontier_baseline_cost": round(baseline_cost, 6),
                "savings_pct": savings_vs_frontier,
            })

        return {"analyzed_requests": len(rows), "modes": results}
    finally:
        session.close()


# ------------------------------------------------------------------
# Alert endpoints
# ------------------------------------------------------------------

class AlertRuleRequest(BaseModel):
    alert_type: str
    threshold: float
    webhook_url: str

    @field_validator("alert_type")
    @classmethod
    def validate_alert_type(cls, v):
        if v not in ("daily_spend", "error_rate", "latency"):
            raise ValueError("alert_type must be daily_spend, error_rate, or latency")
        return v

    @field_validator("threshold")
    @classmethod
    def validate_threshold_positive(cls, v):
        if v <= 0:
            raise ValueError("threshold must be positive")
        return v

    @field_validator("webhook_url")
    @classmethod
    def validate_webhook(cls, v):
        _validate_webhook_url(v)
        return v


@app.get("/alerts")
def get_alerts(user_id: str = Depends(require_user)):
    session = SessionLocal()
    try:
        rows = session.query(AlertRule).filter(AlertRule.user_id == user_id, AlertRule.is_active == True).all()
        return [
            {
                "id": r.id,
                "alert_type": r.alert_type,
                "threshold": r.threshold,
                "webhook_url": r.webhook_url,
                "last_fired_at": r.last_fired_at.isoformat() if r.last_fired_at else None,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
    finally:
        session.close()


@app.post("/alerts")
def create_alert(req: AlertRuleRequest, user_id: str = Depends(require_user)):
    session = SessionLocal()
    try:
        rule = AlertRule(
            user_id=user_id,
            alert_type=req.alert_type,
            threshold=req.threshold,
            webhook_url=req.webhook_url,
        )
        session.add(rule)
        session.commit()
        session.refresh(rule)
        return {"id": rule.id, "alert_type": rule.alert_type, "threshold": rule.threshold, "webhook_url": rule.webhook_url}
    finally:
        session.close()


@app.delete("/alerts/{alert_id}")
def delete_alert(alert_id: int, user_id: str = Depends(require_user)):
    session = SessionLocal()
    try:
        rule = session.query(AlertRule).filter(AlertRule.id == alert_id, AlertRule.user_id == user_id).first()
        if not rule:
            raise HTTPException(status_code=404, detail="Alert rule not found")
        rule.is_active = False
        session.commit()
        return {"deleted": alert_id}
    finally:
        session.close()


# ------------------------------------------------------------------
# Admin endpoints (require ADMIN_USER_ID)
# ------------------------------------------------------------------

@app.get("/admin/stats")
def admin_stats(user_id: str = Depends(require_admin_any)):
    """Global stats across all users. Admin only (API key or JWT)."""
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
            .filter(RequestLog.cache_hit == True).scalar() or 0.0
        )
        routing_savings_usd = max(0.0, round(total_hypothetical_cost - total_actual_cost, 6))
        total_savings_usd = round(cache_savings_usd + routing_savings_usd, 6)

        average_quality = float(
            session.query(func.avg(RequestLog.quality_score))
            .filter(RequestLog.quality_score.isnot(None))
            .scalar() or 0.0
        )

        # Per-user breakdown
        user_request_counts = dict(
            session.query(ApiKey.user_id, func.count(RequestLog.id))
            .join(ApiKey, RequestLog.api_key_id == ApiKey.id)
            .filter(ApiKey.user_id.isnot(None))
            .group_by(ApiKey.user_id).all()
        )

        user_costs = dict(
            session.query(ApiKey.user_id, func.sum(RequestLog.cost_usd))
            .join(ApiKey, RequestLog.api_key_id == ApiKey.id)
            .filter(ApiKey.user_id.isnot(None))
            .group_by(ApiKey.user_id).all()
        )

        user_breakdown = []
        all_user_ids = set(user_request_counts.keys()) | set(user_costs.keys())
        for uid in sorted(all_user_ids):
            user_breakdown.append({
                "user_id": uid,
                "requests": user_request_counts.get(uid, 0),
                "cost_usd": round(float(user_costs.get(uid, 0) or 0), 6),
            })

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
            "average_quality": round(average_quality, 4),
            "user_breakdown": user_breakdown,
        }
    finally:
        session.close()


@app.get("/admin/keys")
def admin_keys(user_id: str = Depends(require_admin_any)):
    """List all API keys across all users. Admin only (API key or JWT)."""
    session = SessionLocal()
    try:
        rows = session.query(ApiKey).order_by(ApiKey.created_at.desc()).all()
        return [
            {
                "id": r.id,
                "key": r.key[:8] + "..." + r.key[-4:] if len(r.key) > 16 else r.key,
                "name": r.name,
                "user_id": r.user_id,
                "is_active": r.is_active,
                "daily_budget_usd": r.daily_budget_usd,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    finally:
        session.close()


@app.get("/admin/logs")
def admin_logs(limit: int = 50, user_id: str = Depends(require_admin_any)):
    """Recent request logs across all keys. Admin only (API key or JWT)."""
    limit = max(1, min(limit, 200))
    session = SessionLocal()
    try:
        rows = (
            session.query(RequestLog)
            .order_by(RequestLog.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": r.id,
                "query": r.query,
                "response": (r.response[:200] + "...") if r.response and len(r.response) > 200 else r.response,
                "tier": r.tier,
                "model_id": r.model_id,
                "cost_usd": r.cost_usd,
                "latency_ms": r.latency_ms,
                "cache_hit": r.cache_hit,
                "api_key_id": r.api_key_id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    finally:
        session.close()


@app.get("/admin/users")
def admin_users(user_id: str = Depends(require_admin_any)):
    """List all users who have created API keys. Admin only (API key or JWT)."""
    session = SessionLocal()
    try:
        rows = session.query(ApiKey.user_id).filter(ApiKey.user_id.isnot(None)).distinct().all()
        user_ids = [r[0] for r in rows]

        result = []
        for uid in user_ids:
            key_count = session.query(func.count(ApiKey.id)).filter(ApiKey.user_id == uid, ApiKey.is_active == True).scalar() or 0
            request_count = session.query(func.count(RequestLog.id)).join(ApiKey, RequestLog.api_key_id == ApiKey.id).filter(ApiKey.user_id == uid).scalar() or 0
            total_cost = float(session.query(func.sum(RequestLog.cost_usd)).join(ApiKey, RequestLog.api_key_id == ApiKey.id).filter(ApiKey.user_id == uid).scalar() or 0.0)
            result.append({
                "user_id": uid,
                "active_keys": key_count,
                "total_requests": request_count,
                "total_cost_usd": round(total_cost, 6),
            })
        return result
    finally:
        session.close()