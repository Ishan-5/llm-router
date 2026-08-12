import json
import time
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
from router.classifier import get_tier
from router.rate_limiter import call_with_failover, AllTiersFailedError
from router.cache import check_cache, add_to_cache
from router.db import log_request, SessionLocal, ApiKey, RequestLog, UserSettings, compute_quality_score
from router.auth import require_api_key, check_budget
from router.config import TAVILY_API_KEY, MODEL_CONFIG
from router.guardrails import is_prompt_injection, sanitize_pii, needs_web_search
from router.model_config_loader import get_active_config, get_pricing_for_model
from router.providers import stream_model
from router.quality_judge import update_quality_score

router = APIRouter()
log = logging.getLogger("routewise")
executor = ThreadPoolExecutor()

DEFAULT_THRESHOLD = 1.0


def load_user_threshold(user_id: str | None) -> float:
    if not user_id:
        return DEFAULT_THRESHOLD
    session = SessionLocal()
    try:
        settings = session.query(UserSettings).filter(UserSettings.user_id == str(user_id)).first()
        return settings.router_threshold if settings else DEFAULT_THRESHOLD
    finally:
        session.close()


class QueryRequest(BaseModel):
    query: str
    override_tier: str | None = None
    user_api_keys: dict | None = None
    byom_config: dict | None = None
    bypass_cache: bool = False
    threshold: float | None = None
    messages: list[dict] | None = None  # multi-turn: [{"role": "user"|"assistant", "content": str}]

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


async def _preprocess(req: QueryRequest, api_key: ApiKey, start: float, _executor):
    loop = asyncio.get_event_loop()
    threshold = req.threshold if req.threshold is not None else load_user_threshold(api_key.user_id)

    if needs_web_search(req.query) and TAVILY_API_KEY:
        try:
            import httpx
            resp = await loop.run_in_executor(
                _executor, lambda: httpx.post(
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
            log_id = log_request({
                "api_key_id": api_key.id, "user_id": api_key.user_id,
                "query": sanitize_pii(req.query), "response": answer,
                "difficulty_score": None, "intended_tier": "web", "tier": "web",
                "fallback_used": False, "cache_hit": False, "cache_similarity": None,
                "model_id": "tavily/search", "input_tokens": 0, "output_tokens": 0,
                "cost_usd": 0.0, "latency_ms": latency_ms, "quality_score": 1.0,
            })
            return {"type": "web", "answer": answer, "latency_ms": latency_ms, "quality_score": 1.0, "log_id": log_id}

    async def _maybe_check_cache():
        if req.bypass_cache:
            return None
        return await loop.run_in_executor(_executor, check_cache, req.query)

    cached, (difficulty_score, tier, cheap_ceil, frontier_floor) = await asyncio.gather(
        _maybe_check_cache(),
        loop.run_in_executor(_executor, get_tier, req.query, threshold),
    )

    if cached is not None:
        latency_ms = round((time.time() - start) * 1000, 2)
        price_in, price_out = get_pricing_for_model(cached["model_id"])
        tokens_saved_usd = round(
            (cached["input_tokens"] / 1_000_000 * price_in)
            + (cached["output_tokens"] / 1_000_000 * price_out), 6)
        quality_score = compute_quality_score(cache_hit=True, cache_similarity=cached["similarity"], fallback_used=False)
        log_id = log_request({
            "api_key_id": api_key.id, "user_id": api_key.user_id,
            "query": sanitize_pii(req.query), "response": cached["response"],
            "difficulty_score": None, "intended_tier": cached["tier"], "tier": cached["tier"],
            "fallback_used": False, "cache_hit": True, "cache_similarity": cached["similarity"],
            "model_id": cached["model_id"], "input_tokens": 0, "output_tokens": 0,
            "cost_usd": 0.0, "latency_ms": latency_ms, "tokens_saved_usd": tokens_saved_usd,
            "quality_score": quality_score,
        })
        return {"type": "cache", "cached": cached, "tokens_saved_usd": tokens_saved_usd, "latency_ms": latency_ms, "quality_score": quality_score, "log_id": log_id}

    routing_tier = req.override_tier if req.override_tier else tier
    over_budget = not check_budget(api_key)
    if over_budget:
        routing_tier = "cheap"

    # build route_reason
    if req.override_tier:
        route_reason = f"override: forced to {req.override_tier}"
    elif over_budget:
        route_reason = f"budget exceeded — forced to cheap (score {difficulty_score:.2f})"
    elif routing_tier == "cheap":
        route_reason = f"score {difficulty_score:.2f} ≤ cheap ceiling {cheap_ceil:.2f}"
    elif routing_tier == "frontier":
        route_reason = f"score {difficulty_score:.2f} ≥ frontier floor {frontier_floor:.2f}"
    else:
        route_reason = f"score {difficulty_score:.2f} between {cheap_ceil:.2f} and {frontier_floor:.2f} → mid"

    user_config = get_active_config(api_key.user_id)
    if req.user_api_keys:
        for t, key in req.user_api_keys.items():
            if t in user_config and key:
                user_config[t]["api_key"] = key
    if req.byom_config:
        for t, cfg in req.byom_config.items():
            if t in user_config and isinstance(cfg, dict):
                if cfg.get("provider"):
                    user_config[t]["provider"] = cfg["provider"]
                if cfg.get("model_id"):
                    user_config[t]["model_id"] = cfg["model_id"]

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
        "messages": req.messages,
        "route_reason": route_reason,
    }


@router.post("/route")
async def route_query(req: QueryRequest, api_key: ApiKey = Depends(require_api_key)):
    if is_prompt_injection(req.query):
        raise HTTPException(status_code=400, detail="Prompt injection detected")

    start = time.time()
    pre = await _preprocess(req, api_key, start, executor)

    if pre["type"] == "web":
        return {
            "response": pre["answer"], "routed_to": "web", "intended_tier": "web",
            "predicted_tier": "web", "override_used": False, "budget_capped": False,
            "fallback_used": False, "cache_hit": False, "difficulty_score": None,
            "cost_usd": 0.0, "latency_ms": pre["latency_ms"],
            "model_id": "tavily/search", "request_log_id": pre["log_id"],
        }

    if pre["type"] == "cache":
        cached = pre["cached"]
        return {
            "response": cached["response"], "routed_to": cached["tier"],
            "cache_hit": True, "cache_similarity": cached["similarity"],
            "cost_usd": 0.0, "tokens_saved_usd": pre["tokens_saved_usd"],
            "latency_ms": pre["latency_ms"], "model_id": cached["model_id"],
            "route_reason": f"cache hit (similarity {cached['similarity']:.2f})",
            "request_log_id": pre["log_id"],
        }

    routing_tier = pre["tier"]
    difficulty_score = pre["difficulty_score"]
    over_budget = pre["over_budget"]
    loop = asyncio.get_event_loop()

    try:
        result = await loop.run_in_executor(executor, call_with_failover, routing_tier, req.query, req.user_api_keys or {}, pre["messages"], None, None, pre["user_config"])
    except AllTiersFailedError as e:
        log.error("AllTiersFailedError: %s", e)
        log_request({
            "api_key_id": api_key.id, "user_id": api_key.user_id,
            "query": sanitize_pii(req.query), "response": None,
            "difficulty_score": difficulty_score, "intended_tier": routing_tier,
            "tier": "failed", "fallback_used": False,
            "cache_hit": False, "cache_similarity": None, "model_id": None,
            "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
            "latency_ms": round((time.time() - start) * 1000, 2), "quality_score": 0.0,
        })
        raise HTTPException(status_code=503, detail="All model tiers failed to respond. Check your API keys or try again later.")

    latency_ms = round((time.time() - start) * 1000, 2)
    quality_score = compute_quality_score(cache_hit=False, cache_similarity=None, fallback_used=result["fallback_used"])
    log_id = log_request({
        "api_key_id": api_key.id, "user_id": api_key.user_id,
        "query": sanitize_pii(req.query), "response": result["text"],
        "difficulty_score": difficulty_score, "intended_tier": result["intended_tier"],
        "tier": result["tier"], "fallback_used": result["fallback_used"],
        "cache_hit": False, "cache_similarity": None, "model_id": result["model_id"],
        "input_tokens": result["input_tokens"], "output_tokens": result["output_tokens"],
        "cost_usd": result["cost_usd"],
        "latency_ms": result["latency_ms"] if "latency_ms" in result else latency_ms,
        "quality_score": quality_score,
    })
    loop.run_in_executor(executor, add_to_cache, req.query, result["text"], result["tier"], result["model_id"], result["cost_usd"], result["input_tokens"], result["output_tokens"])
    if log_id is not None:
        loop.run_in_executor(executor, update_quality_score, log_id, sanitize_pii(req.query), result["text"], result["tier"], result["model_id"])
    return {
        "response": result["text"], "routed_to": result["tier"],
        "intended_tier": result["intended_tier"], "predicted_tier": pre["predicted_tier"],
        "override_used": req.override_tier is not None, "budget_capped": over_budget,
        "fallback_used": result["fallback_used"], "cache_hit": False,
        "difficulty_score": difficulty_score, "cost_usd": result["cost_usd"],
        "latency_ms": latency_ms, "quality_score": quality_score,
        "cheap_ceil": pre["cheap_ceil"], "frontier_floor": pre["frontier_floor"],
        "model_id": result["model_id"],
        "route_reason": pre["route_reason"] if not result["fallback_used"] else f"{pre['route_reason']} (fallback to {result['tier']})",
        "request_log_id": log_id,
    }


@router.post("/route/stream")
async def route_query_stream(req: QueryRequest, api_key: ApiKey = Depends(require_api_key)):
    if is_prompt_injection(req.query):
        raise HTTPException(status_code=400, detail="Prompt injection detected")

    start = time.time()
    pre = await _preprocess(req, api_key, start, executor)

    if pre["type"] == "web":
        answer = pre["answer"]
        latency_ms = pre["latency_ms"]
        log_id = pre.get("log_id")
        async def _web_stream():
            yield f"data: {json.dumps({'type': 'meta', 'routed_to': 'web', 'cache_hit': False, 'cost_usd': 0.0, 'latency_ms': latency_ms, 'model_id': 'tavily/search', 'request_log_id': log_id})}\n\n"
            yield f"data: {json.dumps({'type': 'chunk', 'text': answer})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return StreamingResponse(_web_stream(), media_type="text/event-stream")

    if pre["type"] == "cache":
        cached = pre["cached"]
        tokens_saved_usd = pre["tokens_saved_usd"]
        latency_ms = pre["latency_ms"]
        log_id = pre.get("log_id")
        async def _cache_stream():
            yield f"data: {json.dumps({'type': 'meta', 'routed_to': cached['tier'], 'cache_hit': True, 'cache_similarity': cached['similarity'], 'cost_usd': 0.0, 'tokens_saved_usd': tokens_saved_usd, 'latency_ms': latency_ms, 'model_id': cached['model_id'], 'request_log_id': log_id})}\n\n"
            yield f"data: {json.dumps({'type': 'chunk', 'text': cached['response']})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return StreamingResponse(_cache_stream(), media_type="text/event-stream")

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
                for item in stream_model(routing_tier, req.query, user_config.get(routing_tier), messages=pre.get("messages")):
                    loop.call_soon_threadsafe(queue.put_nowait, item)
            except Exception as e:
                loop.call_soon_threadsafe(queue.put_nowait, Exception(str(e)))
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

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

        log_id = log_request({
            "api_key_id": api_key.id, "user_id": api_key.user_id,
            "query": sanitize_pii(req.query), "response": full_response,
            "difficulty_score": difficulty_score, "intended_tier": routing_tier,
            "tier": meta["tier"], "fallback_used": False, "cache_hit": False,
            "cache_similarity": None, "model_id": meta["model_id"],
            "input_tokens": meta["input_tokens"], "output_tokens": meta["output_tokens"],
            "cost_usd": meta["cost_usd"], "latency_ms": latency_ms, "quality_score": quality_score,
        })
        loop.run_in_executor(executor, add_to_cache, req.query, full_response,
            meta["tier"], meta["model_id"], meta["cost_usd"],
            meta["input_tokens"], meta["output_tokens"])
        if log_id is not None:
            loop.run_in_executor(executor, update_quality_score, log_id, sanitize_pii(req.query), full_response, meta["tier"], meta["model_id"])

        yield f"data: {json.dumps({'type': 'done', 'routed_to': meta['tier'], 'intended_tier': routing_tier, 'predicted_tier': pre['predicted_tier'], 'override_used': req.override_tier is not None, 'budget_capped': over_budget, 'fallback_used': False, 'cache_hit': False, 'difficulty_score': difficulty_score, 'cost_usd': meta['cost_usd'], 'latency_ms': latency_ms, 'quality_score': quality_score, 'model_id': meta['model_id'], 'request_log_id': log_id})}\n\n"

    return StreamingResponse(_live_stream(), media_type="text/event-stream")


class FeedbackRequest(BaseModel):
    request_log_id: int
    feedback: str  # 'up' | 'down'
    reason: str | None = None

    @field_validator("feedback")
    @classmethod
    def validate_feedback(cls, v):
        if v not in ("up", "down"):
            raise ValueError("feedback must be 'up' or 'down'")
        return v

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v):
        if v is not None:
            v = v.strip()
            if len(v) > 1000:
                raise ValueError("reason cannot exceed 1000 characters")
        return v


@router.post("/route/feedback")
async def submit_feedback(req: FeedbackRequest, api_key: ApiKey = Depends(require_api_key)):
    session = SessionLocal()
    try:
        entry = session.query(RequestLog).filter(RequestLog.id == req.request_log_id).first()
        if entry is None:
            raise HTTPException(status_code=404, detail="Request log entry not found")
        entry.feedback = req.feedback
        entry.feedback_reason = req.reason or None
        session.commit()
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        log.error("submit_feedback failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to save feedback")
    finally:
        session.close()
    return {"ok": True, "request_log_id": req.request_log_id, "feedback": req.feedback}
