import json
import time
import uuid
import asyncio
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, HTTPException, Depends, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from router.classifier import get_tier
from router.cache import check_cache, add_to_cache
from router.db import log_request, ApiKey
from router.auth import require_api_key, check_budget
from router.config import TIER_MARGIN, MODEL_CONFIG
from router.guardrails import is_prompt_injection, sanitize_pii
from router.rate_limiter import call_with_failover, AllTiersFailedError
from router.providers import stream_model
from router.model_config_loader import get_active_config, get_pricing_for_model

router = APIRouter()
executor = ThreadPoolExecutor()


class ChatMessage(BaseModel):
    role: str
    content: str | None = None


class ChatCompletionRequest(BaseModel):
    model: str = "auto"
    messages: list[ChatMessage]
    stream: bool = False
    max_tokens: int | None = None
    temperature: float | None = None


def _generate_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex}"


def _resolve_tier(model: str) -> tuple[str | None, str]:
    """
    Maps the model field to a tier.
    Returns (override_tier, mode) where:
      - mode="auto" means use the ML classifier
      - mode="force" means the user explicitly chose a tier
    """
    model_lower = model.strip().lower()
    if model_lower in ("auto", "", "auto-routing"):
        return None, "auto"
    if model_lower in ("cheap", "mid", "frontier"):
        return model_lower, "force"
    # Unrecognized string — treat as auto (ML routing is the product)
    return None, "auto"


def _extract_user_query(messages: list[ChatMessage]) -> str:
    """Extract the last user message content for scoring and cache lookup."""
    for msg in reversed(messages):
        if msg.role == "user" and msg.content:
            return msg.content
    return ""


def _build_messages_for_provider(messages: list[ChatMessage]) -> list[dict]:
    """Convert ChatMessage list to plain dicts for provider calls."""
    return [{"role": m.role, "content": m.content or ""} for m in messages]


def _build_chat_response(
    id: str,
    model: str,
    content: str,
    usage: dict,
    tier: str,
) -> dict:
    return {
        "id": id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": usage.get("input_tokens", 0),
            "completion_tokens": usage.get("output_tokens", 0),
            "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
        },
        "x-routewise-tier": tier,
    }


def _build_stream_chunk(id: str, model: str, delta: dict, finish_reason: str | None = None) -> str:
    chunk = {
        "id": id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason,
            }
        ],
    }
    return f"data: {json.dumps(chunk)}\n\n"


@router.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest, request: Request, response: Response, api_key: ApiKey = Depends(require_api_key)):
    # --- validate messages ---
    if not req.messages or not any(m.role == "user" and m.content for m in req.messages):
        raise HTTPException(status_code=400, detail="messages must contain at least one user message")

    user_query = _extract_user_query(req.messages)

    # --- injection check ---
    if is_prompt_injection(user_query):
        raise HTTPException(status_code=400, detail="Prompt injection detected")

    # --- resolve tier ---
    override_tier, mode = _resolve_tier(req.model)
    start = time.time()
    chat_id = _generate_id()

    # --- web search check ---
    from router.guardrails import needs_web_search
    from router.config import TAVILY_API_KEY
    if needs_web_search(user_query) and TAVILY_API_KEY:
        try:
            import httpx
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(
                executor, lambda: httpx.post(
                    "https://api.tavily.com/search",
                    json={"api_key": TAVILY_API_KEY, "query": user_query, "search_depth": "advanced", "max_results": 5, "include_answer": True},
                    timeout=10,
                )
            )
            resp.raise_for_status()
            data = resp.json()
            answer = data.get("answer") or (
                "\n\n".join(r["content"][:300] for r in data.get("results", [])[:3])
                + "\n\n[web results truncated — showing first 300 chars per source]"
            )
        except Exception:
            pass
        else:
            latency_ms = round((time.time() - start) * 1000, 2)
            log_request({
                "api_key_id": api_key.id, "query": sanitize_pii(user_query),
                "response": answer,
                "difficulty_score": None, "intended_tier": "web", "tier": "web",
                "fallback_used": False, "cache_hit": False, "cache_similarity": None,
                "model_id": "tavily/search", "input_tokens": 0, "output_tokens": 0,
                "cost_usd": 0.0, "latency_ms": latency_ms,
            })
            response.headers["x-routewise-tier"] = "web"
            response.headers["x-routewise-cost"] = "0"
            response.headers["x-routewise-cache-hit"] = "false"
            response.headers["x-routewise-difficulty"] = ""
            return _build_chat_response(chat_id, req.model, answer, {"input_tokens": 0, "output_tokens": 0}, "web")

    # --- cache + classifier in parallel ---
    loop = asyncio.get_event_loop()

    async def _maybe_check_cache():
        return await loop.run_in_executor(executor, check_cache, user_query)

    cached, (difficulty_score, tier) = await asyncio.gather(
        _maybe_check_cache(),
        loop.run_in_executor(executor, get_tier, user_query, TIER_MARGIN),
    )

    if cached is not None:
        latency_ms = round((time.time() - start) * 1000, 2)
        log_request({
            "api_key_id": api_key.id, "query": sanitize_pii(user_query),
            "response": cached["response"],
            "difficulty_score": None, "intended_tier": cached["tier"], "tier": cached["tier"],
            "fallback_used": False, "cache_hit": True, "cache_similarity": cached["similarity"],
            "model_id": cached["model_id"], "input_tokens": 0, "output_tokens": 0,
            "cost_usd": 0.0, "latency_ms": latency_ms,
        })
        response.headers["x-routewise-tier"] = cached["tier"]
        response.headers["x-routewise-cost"] = "0"
        response.headers["x-routewise-cache-hit"] = "true"
        response.headers["x-routewise-difficulty"] = ""
        return _build_chat_response(chat_id, req.model, cached["response"], {"input_tokens": 0, "output_tokens": 0}, cached["tier"])

    # --- resolve tier ---
    routing_tier = override_tier if override_tier else tier
    over_budget = not check_budget(api_key)
    if over_budget:
        routing_tier = "cheap"

    provider_messages = _build_messages_for_provider(req.messages)

    # --- non-streaming ---
    if not req.stream:
        try:
            result = await loop.run_in_executor(
                executor, call_with_failover, routing_tier, user_query, None, provider_messages
            )
        except AllTiersFailedError:
            raise HTTPException(status_code=503, detail="All model tiers failed to respond.")

        latency_ms = round((time.time() - start) * 1000, 2)
        log_request({
            "api_key_id": api_key.id, "query": sanitize_pii(user_query),
            "response": result["text"],
            "difficulty_score": difficulty_score, "intended_tier": result["intended_tier"],
            "tier": result["tier"], "fallback_used": result["fallback_used"],
            "cache_hit": False, "cache_similarity": None, "model_id": result["model_id"],
            "input_tokens": result["input_tokens"], "output_tokens": result["output_tokens"],
            "cost_usd": result["cost_usd"], "latency_ms": latency_ms,
        })
        loop.run_in_executor(
            executor, add_to_cache, user_query, result["text"], result["tier"],
            result["model_id"], result["cost_usd"], result["input_tokens"], result["output_tokens"],
        )

        usage = {"input_tokens": result["input_tokens"], "output_tokens": result["output_tokens"]}
        response.headers["x-routewise-tier"] = result["tier"]
        response.headers["x-routewise-cost"] = str(result["cost_usd"])
        response.headers["x-routewise-cache-hit"] = "false"
        response.headers["x-routewise-difficulty"] = str(difficulty_score)
        return _build_chat_response(chat_id, req.model, result["text"], usage, result["tier"])

    # --- streaming ---
    async def _stream():
        full_text = []
        meta = None
        queue = asyncio.Queue()

        def _run_generator():
            try:
                for item in stream_model(routing_tier, user_query, messages=provider_messages):
                    loop.call_soon_threadsafe(queue.put_nowait, item)
            except Exception as e:
                loop.call_soon_threadsafe(queue.put_nowait, Exception(str(e)))
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        loop.run_in_executor(executor, _run_generator)

        # initial chunk with role
        yield _build_stream_chunk(chat_id, req.model, {"role": "assistant"})

        while True:
            item = await queue.get()
            if item is None:
                break
            if isinstance(item, Exception):
                err_chunk = {
                    "error": {"message": str(item), "type": "server_error", "code": "model_error"},
                }
                yield f"data: {json.dumps(err_chunk)}\n\n"
                return
            if isinstance(item, dict):
                meta = item
            else:
                full_text.append(item)
                yield _build_stream_chunk(chat_id, req.model, {"content": item})

        # final chunk with finish_reason
        yield _build_stream_chunk(chat_id, req.model, {}, finish_reason="stop")
        yield "data: [DONE]\n\n"

        if meta is None:
            return

        latency_ms = round((time.time() - start) * 1000, 2)
        full_response = "".join(full_text)

        log_request({
            "api_key_id": api_key.id, "query": sanitize_pii(user_query),
            "response": full_response,
            "difficulty_score": difficulty_score, "intended_tier": routing_tier,
            "tier": meta["tier"], "fallback_used": False, "cache_hit": False,
            "cache_similarity": None, "model_id": meta["model_id"],
            "input_tokens": meta["input_tokens"], "output_tokens": meta["output_tokens"],
            "cost_usd": meta["cost_usd"], "latency_ms": latency_ms,
        })
        loop.run_in_executor(
            executor, add_to_cache, user_query, full_response,
            meta["tier"], meta["model_id"], meta["cost_usd"],
            meta["input_tokens"], meta["output_tokens"],
        )

    return StreamingResponse(_stream(), media_type="text/event-stream")
