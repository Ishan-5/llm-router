import json
import time
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
from router.support_policy import available_support_modes, SUPPORT_MODES
# Re-exported: callers and tests import these from this module.
from router.classifier import get_tier
from router.support_policy import get_tier_with_mode
from router.multiturn import build_scoring_context, score_with_context
from router.rate_limiter import call_with_failover, AllTiersFailedError, stream_model_with_failover
from router.cache import check_cache, add_to_cache
from router.db import log_request, SessionLocal, ApiKey, RequestLog, UserSettings, compute_quality_score
from router.auth import require_api_key, check_budget
from router.config import TAVILY_API_KEY, MODEL_CONFIG
from router.guardrails import is_prompt_injection, sanitize_pii, needs_web_search
from router.model_config_loader import get_active_config, get_pricing_for_model, resolve_tier_pricing
from router.quality_judge import update_quality_score
from router.difficulty_labeler import update_difficulty_label

router = APIRouter()
log = logging.getLogger("routewise")
executor = ThreadPoolExecutor()

DEFAULT_THRESHOLD = 1.0


def _is_price(v) -> bool:
    """True only for a real non-negative number (bool is an int subclass, so reject it)."""
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0


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
    # Opt-in customer-support difficulty policy. None/"generic" keeps the live
    # production path exactly as it was; "2tier"/"3tier" score with the
    # support models instead. Costs no extra LLM call.
    support_mode: str | None = None
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

    @field_validator("support_mode")
    @classmethod
    def validate_support_mode(cls, v):
        if v is not None and v not in SUPPORT_MODES:
            raise ValueError(f"support_mode must be one of {list(SUPPORT_MODES)}")
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
        return await loop.run_in_executor(_executor, check_cache, req.query, api_key.id)

    def _score_sync() -> tuple:
        """Run in the executor thread. Raises HTTPException-free errors; the
        caller converts them, because HTTPException is not meaningful off-loop."""
        return score_with_context(
            req.query,
            margin=threshold,
            support_mode=req.support_mode,
            context=build_scoring_context(req.messages, req.query),
        )

    # Scoring and the cache lookup are independent, so run them together as
    # the live path always did. A support-policy failure must surface as 503
    # rather than silently falling back to a model that did not score.
    try:
        _cache_result, scored = await asyncio.gather(
            _maybe_check_cache(),
            loop.run_in_executor(_executor, _score_sync),
        )
    except HTTPException:
        raise
    except Exception as e:
        if req.support_mode and req.support_mode != "generic":
            log.error("support policy %s failed: %s", req.support_mode, e)
            raise HTTPException(
                status_code=503,
                detail=f"support policy {req.support_mode!r} unavailable: {e}",
            )
        raise
    cached = _cache_result
    difficulty_score, tier, cheap_ceil, frontier_floor, resolved_mode = scored

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

    if req.override_tier and req.override_tier not in ("cheap", "mid", "frontier"):
        raise HTTPException(status_code=400, detail="invalid override_tier")
    # A 2-tier support policy has no mid band, so forcing mid is incoherent.
    if (
        req.override_tier == "mid"
        and resolved_mode == "2tier"
    ):
        raise HTTPException(
            status_code=400,
            detail="override_tier 'mid' is not available under the 2tier support policy",
        )

    routing_tier = req.override_tier if req.override_tier else tier
    over_budget = not check_budget(api_key)
    if over_budget:
        routing_tier = "cheap"

    # build route_reason
    if req.override_tier:
        route_reason = f"override: forced to {req.override_tier}"
    elif over_budget:
        route_reason = f"budget exceeded — forced to cheap (score {difficulty_score:.2f})"
    elif resolved_mode != "generic":
        if routing_tier == "cheap":
            route_reason = f"support {resolved_mode}: score {difficulty_score:.2f} ≤ cheap ceiling {cheap_ceil:.2f}"
        elif routing_tier == "frontier":
            if resolved_mode == "2tier":
                route_reason = f"support {resolved_mode}: score {difficulty_score:.2f} > cheap ceiling {cheap_ceil:.2f} → frontier"
            else:
                route_reason = f"support {resolved_mode}: score {difficulty_score:.2f} ≥ frontier floor {frontier_floor:.2f}"
        else:
            route_reason = f"support {resolved_mode}: score {difficulty_score:.2f} between {cheap_ceil:.2f} and {frontier_floor:.2f} → mid"
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
                # Reprice against the effective model. The prices merged in by
                # get_active_config belong to the tier default, so without this a
                # BYOM override would be costed as the default model.
                pin = cfg.get("price_per_m_input")
                pout = cfg.get("price_per_m_output")
                if _is_price(pin) and _is_price(pout):
                    user_config[t]["price_per_m_input"] = float(pin)
                    user_config[t]["price_per_m_output"] = float(pout)
                else:
                    user_config[t]["price_per_m_input"], user_config[t]["price_per_m_output"] = resolve_tier_pricing(
                        user_config[t]["provider"],
                        user_config[t]["model_id"],
                        user_config[t]["price_per_m_input"],
                        user_config[t]["price_per_m_output"],
                    )

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
        "support_mode": resolved_mode,
        "available_tiers": (
            ["cheap", "frontier"] if resolved_mode == "2tier" else ["cheap", "mid", "frontier"]
        ),
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
    loop.run_in_executor(executor, add_to_cache, req.query, result["text"], result["tier"], result["model_id"], result["cost_usd"], result["input_tokens"], result["output_tokens"], api_key.id)
    if log_id is not None:
        loop.run_in_executor(executor, update_quality_score, log_id, sanitize_pii(req.query), result["text"], result["tier"], result["model_id"])
        loop.run_in_executor(executor, update_difficulty_label, log_id, sanitize_pii(req.query))
    return {
        "response": result["text"], "routed_to": result["tier"],
        "intended_tier": result["intended_tier"], "predicted_tier": pre["predicted_tier"],
        "override_used": req.override_tier is not None, "budget_capped": over_budget,
        "fallback_used": result["fallback_used"],
        "cross_provider_fallback": bool(result.get("cross_provider_fallback")),
        "cache_hit": False,
        "difficulty_score": difficulty_score, "cost_usd": result["cost_usd"],
        "latency_ms": latency_ms, "quality_score": quality_score,
        "cheap_ceil": pre["cheap_ceil"], "frontier_floor": pre["frontier_floor"],
        "support_mode": pre["support_mode"], "available_tiers": pre["available_tiers"],
        "model_id": result["model_id"],
        "route_reason": pre["route_reason"] if not result["fallback_used"] else f"{pre['route_reason']} (fallback to {result['tier']})",
        "request_log_id": log_id,
    }


@router.get("/route/policies")
async def list_route_policies(api_key: ApiKey = Depends(require_api_key)):
    """Available difficulty policies and their routing tradeoffs.

    Lets the frontend render a selector without hardcoding tier counts, and
    report a policy as unavailable if its artifact fails to validate.
    """
    from router.support_policy import preload_support_policies
    import feature_builder as _fb

    available = preload_support_policies()
    return {"default": "generic", "available_modes": available, "policies": _fb.policy_manifest()}


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

        # Routing is decided before the first token. Emit it now so the diagram
        # lights up the instant the answer starts streaming, instead of only
        # after the whole response has finished arriving.
        early_meta = {
            "type": "meta",
            "routed_to": pre["tier"],
            "intended_tier": pre["tier"],
            "predicted_tier": pre["predicted_tier"],
            "override_used": req.override_tier is not None,
            "budget_capped": over_budget,
            "difficulty_score": difficulty_score,
            "support_mode": pre["support_mode"],
            "available_tiers": pre["available_tiers"],
            "n_tiers": len(pre["available_tiers"]),
            "cheap_ceil": pre["cheap_ceil"],
            "frontier_floor": pre["frontier_floor"],
            "route_reason": pre["route_reason"],
        }
        yield f"data: {json.dumps(early_meta)}\n\n"

        def _run_generator():
            try:
                for item in stream_model_with_failover(routing_tier, req.query, user_config, messages=pre.get("messages")):
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
                if item.get("type") == "failover":
                    yield f"data: {json.dumps({'type': 'failover', 'from_tier': item.get('from_tier'), 'detail': item.get('detail', '')})}\n\n"
                    continue
                meta = item
            else:
                full_text.append(item)
                yield f"data: {json.dumps({'type': 'chunk', 'text': item})}\n\n"

        if meta is None:
            yield f"data: {json.dumps({'type': 'error', 'detail': 'No response from model'})}\n\n"
            return

        latency_ms = round((time.time() - start) * 1000, 2)
        full_response = "".join(full_text)
        fallback_used = meta["tier"] != routing_tier
        cross_provider_fallback = meta["tier"] == "gemini"
        quality_score = compute_quality_score(cache_hit=False, cache_similarity=None, fallback_used=fallback_used)

        log_id = log_request({
            "api_key_id": api_key.id, "user_id": api_key.user_id,
            "query": sanitize_pii(req.query), "response": full_response,
            "difficulty_score": difficulty_score, "intended_tier": routing_tier,
            "tier": meta["tier"], "fallback_used": fallback_used, "cache_hit": False,
            "cache_similarity": None, "model_id": meta["model_id"],
            "input_tokens": meta["input_tokens"], "output_tokens": meta["output_tokens"],
            "cost_usd": meta["cost_usd"], "latency_ms": latency_ms, "quality_score": quality_score,
        })
        loop.run_in_executor(executor, add_to_cache, req.query, full_response,
            meta["tier"], meta["model_id"], meta["cost_usd"],
            meta["input_tokens"], meta["output_tokens"], api_key.id)
        if log_id is not None:
            loop.run_in_executor(executor, update_quality_score, log_id, sanitize_pii(req.query), full_response, meta["tier"], meta["model_id"])
            loop.run_in_executor(executor, update_difficulty_label, log_id, sanitize_pii(req.query))

        done_event = {
            "type": "done",
            "routed_to": meta["tier"],
            "intended_tier": routing_tier,
            "predicted_tier": pre["predicted_tier"],
            "override_used": req.override_tier is not None,
            "budget_capped": over_budget,
            "fallback_used": fallback_used,
            "cross_provider_fallback": cross_provider_fallback,
            "cache_hit": False,
            "difficulty_score": difficulty_score,
            "cost_usd": meta["cost_usd"],
            "latency_ms": latency_ms,
            "quality_score": quality_score,
            "model_id": meta["model_id"],
            "request_log_id": log_id,
            "support_mode": pre["support_mode"],
            "available_tiers": pre["available_tiers"],
            "n_tiers": len(pre["available_tiers"]),
            "cheap_ceil": pre["cheap_ceil"],
            "frontier_floor": pre["frontier_floor"],
            "route_reason": (
                pre["route_reason"]
                if not fallback_used
                else f"{pre['route_reason']} (fallback to {meta['tier']})"
            ),
        }
        yield f"data: {json.dumps(done_event)}\n\n"

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
