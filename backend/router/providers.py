import logging
from groq import Groq
from openai import OpenAI
from router.config import GROQ_API_KEY, GEMINI_API_KEY, MODEL_CONFIG, OLLAMA_FALLBACK_CONFIG, GEMINI_FALLBACK_CONFIG
from router.providers_registry import PROVIDERS_REGISTRY
from router.ollama_client import call_ollama
from router.load_balancer import get_key_for_tier, report_rate_limit_from_error

log = logging.getLogger("routewise.providers")

# Client cache to avoid creating new HTTP sessions per request (resource leak fix)
_client_cache: dict[tuple[str, str], OpenAI] = {}


def _get_client(api_key: str, base_url: str) -> OpenAI:
    """Return a cached OpenAI client for the given (api_key, base_url) pair."""
    key = (api_key, base_url)
    if key not in _client_cache:
        _client_cache[key] = OpenAI(api_key=api_key, base_url=base_url)
    return _client_cache[key]

# default Groq client (used when no user api key supplied)


def _get_groq_key(tier: str) -> str:
    """Get a Groq API key for the tier. Uses load balancer if multi-key configured, else falls back to single key."""
    key = get_key_for_tier(tier)
    if key:
        return key
    return GROQ_API_KEY


def _call_openai_compatible(
    model_id: str,
    query: str,
    tier_label: str,
    price_in: float,
    price_out: float,
    api_key: str,
    base_url: str,
    max_tokens: int = 1000,
    messages: list[dict] | None = None,
    temperature: float | None = None,
) -> dict:
    """
    Generic caller for any OpenAI-compatible API.
    Covers: Groq, OpenAI, DeepSeek, Perplexity, Mistral, xAI, Gemini.
    """
    client = _get_client(api_key, base_url)
    kwargs = {
        "model": model_id,
        "max_tokens": max_tokens,
        "messages": messages if messages else [{"role": "user", "content": query}],
    }
    if temperature is not None:
        kwargs["temperature"] = temperature
    response = client.chat.completions.create(**kwargs)
    input_tokens = response.usage.prompt_tokens
    output_tokens = response.usage.completion_tokens
    cost = (
        (input_tokens / 1_000_000) * price_in
        + (output_tokens / 1_000_000) * price_out
    )
    return {
        "text": response.choices[0].message.content,
        "tier": tier_label,
        "model_id": model_id,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost, 6),
    }


def _stream_openai_compatible(
    model_id: str,
    query: str,
    tier_label: str,
    price_in: float,
    price_out: float,
    api_key: str,
    base_url: str,
    max_tokens: int = 1000,
    messages: list[dict] | None = None,
    temperature: float | None = None,
):
    """
    Streaming version. Yields text chunks, then a final dict with metadata.
    Caller collects chunks until it gets a dict (the sentinel).
    """
    client = _get_client(api_key, base_url)
    kwargs = {
        "model": model_id,
        "max_tokens": max_tokens,
        "messages": messages if messages else [{"role": "user", "content": query}],
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if temperature is not None:
        kwargs["temperature"] = temperature
    stream = client.chat.completions.create(**kwargs)
    input_tokens = 0
    output_tokens = 0
    for chunk in stream:
        if chunk.usage:
            input_tokens = chunk.usage.prompt_tokens or 0
            output_tokens = chunk.usage.completion_tokens or 0
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content
    cost = (input_tokens / 1_000_000) * price_in + (output_tokens / 1_000_000) * price_out
    yield {"tier": tier_label, "model_id": model_id, "input_tokens": input_tokens, "output_tokens": output_tokens, "cost_usd": round(cost, 6)}


def _call_anthropic(
    model_id: str,
    query: str,
    tier_label: str,
    price_in: float,
    price_out: float,
    api_key: str,
    max_tokens: int = 1000,
    messages: list[dict] | None = None,
) -> dict:
    """Anthropic has its own SDK and API format -- handled separately."""
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model_id,
        max_tokens=max_tokens,
        messages=messages if messages else [{"role": "user", "content": query}],
    )
    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    cost = (
        (input_tokens / 1_000_000) * price_in
        + (output_tokens / 1_000_000) * price_out
    )
    return {
        "text": response.content[0].text,
        "tier": tier_label,
        "model_id": model_id,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost, 6),
    }


def call_provider(
    provider: str,
    model_id: str,
    query: str,
    tier_label: str,
    api_key: str,
    price_in: float = 0.0,
    price_out: float = 0.0,
    max_tokens: int = 1000,
    messages: list[dict] | None = None,
) -> dict:
    """
    Routes to the correct provider caller based on provider name.
    Used by both call_model (normal routing) and validate_key (test calls).
    """
    if provider == "ollama":
        return call_ollama(query, model=model_id)

    if provider == "anthropic":
        return _call_anthropic(model_id, query, tier_label, price_in, price_out, api_key, max_tokens, messages)

    # All other providers are OpenAI-compatible
    base_url = PROVIDERS_REGISTRY[provider]["base_url"]
    return _call_openai_compatible(model_id, query, tier_label, price_in, price_out, api_key, base_url, max_tokens, messages)


def call_model(tier: str, query: str, user_config: dict | None = None, messages: list[dict] | None = None, max_tokens: int | None = None, temperature: float | None = None) -> dict:
    """
    Calls the model for the given tier.
    If user_config is provided (from model_config_loader), uses the user's
    provider/model/api_key. Otherwise falls back to the hardcoded defaults.
    Uses load balancer for key rotation when multiple keys are configured.
    """
    if user_config:
        provider = user_config["provider"]
        model_id = user_config["model_id"]
        api_key = user_config.get("api_key", "") or ""
        price_in = user_config.get("price_per_m_input", 0.0)
        price_out = user_config.get("price_per_m_output", 0.0)

        # if no user api_key supplied, use the default key for known providers
        if not api_key:
            if provider == "groq":
                api_key = _get_groq_key(tier)
            elif provider == "gemini":
                api_key = GEMINI_API_KEY

        if provider == "ollama":
            try:
                return call_ollama(query, model=model_id)
            except Exception as e:
                log.warning("ollama local call failed (%s), falling back to Groq cheap model", e)
                cfg = OLLAMA_FALLBACK_CONFIG
                result = _call_openai_compatible(
                    cfg["model_id"], query, tier,
                    cfg["price_per_m_input"], cfg["price_per_m_output"],
                    _get_groq_key("cheap"), PROVIDERS_REGISTRY["groq"]["base_url"],
                    messages=messages, max_tokens=max_tokens or 1000, temperature=temperature,
                )
                result["ollama_fallback"] = True
                return result

        effective_max = max_tokens or 1000
        return call_provider(provider, model_id, query, tier, api_key, price_in, price_out, effective_max, messages)

    # --- default path (no user config) ---
    if tier == "cheap":
        try:
            return call_ollama(query)
        except Exception as e:
            log.warning("ollama local call failed (%s), falling back to Groq cheap model", e)
            cfg = OLLAMA_FALLBACK_CONFIG
            result = _call_openai_compatible(
                cfg["model_id"], query, "cheap",
                cfg["price_per_m_input"], cfg["price_per_m_output"],
                _get_groq_key("cheap"), PROVIDERS_REGISTRY["groq"]["base_url"],
                messages=messages, max_tokens=max_tokens or 1000, temperature=temperature,
            )
            result["ollama_fallback"] = True
            return result

    cfg = MODEL_CONFIG[tier]
    effective_max = max_tokens or 1000
    return _call_openai_compatible(
        cfg["model_id"], query, tier,
        cfg["price_per_m_input"], cfg["price_per_m_output"],
        _get_groq_key(tier), PROVIDERS_REGISTRY["groq"]["base_url"],
        messages=messages, max_tokens=effective_max, temperature=temperature,
    )


def call_gemini(query: str) -> dict:
    """
    Last-resort fallback: independent provider if entire Groq/Ollama chain fails.
    See rate_limiter.py.
    """
    cfg = GEMINI_FALLBACK_CONFIG
    client = _get_client(GEMINI_API_KEY, PROVIDERS_REGISTRY["gemini"]["base_url"])
    response = client.chat.completions.create(
        model=cfg["model_id"],
        max_tokens=1000,
        messages=[{"role": "user", "content": query}],
    )
    input_tokens = response.usage.prompt_tokens
    output_tokens = response.usage.completion_tokens
    cost = (
        (input_tokens / 1_000_000) * cfg["price_per_m_input"]
        + (output_tokens / 1_000_000) * cfg["price_per_m_output"]
    )
    return {
        "text": response.choices[0].message.content,
        "tier": "gemini",
        "model_id": cfg["model_id"],
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost, 6),
    }


def stream_model(tier: str, query: str, user_config: dict | None = None, messages: list[dict] | None = None, max_tokens: int | None = None, temperature: float | None = None):
    """
    Streaming version of call_model. Yields text chunks then a final metadata dict.
    Only supports OpenAI-compatible providers -- Ollama falls back to call_model (non-streaming).
    Uses load balancer for key rotation when multiple keys are configured.
    """
    if user_config:
        # BYOM: skip streaming entirely -- non-streaming path gives accurate token counts
        # across all providers regardless of stream_options support
        result = call_model(tier, query, user_config, messages=messages, max_tokens=max_tokens, temperature=temperature)
        yield result["text"]
        yield {k: result[k] for k in ("tier", "model_id", "input_tokens", "output_tokens", "cost_usd")}
        return

    # default path
    effective_max = max_tokens or 1000
    if tier == "cheap":
        try:
            result = call_ollama(query)
            yield result["text"]
            yield {"tier": "cheap", "model_id": result["model_id"], "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
            return
        except Exception as e:
            log.warning("ollama local call failed (%s), falling back to Groq cheap model", e)
            cfg = OLLAMA_FALLBACK_CONFIG
            yield from _stream_openai_compatible(
                cfg["model_id"], query, "cheap",
                cfg["price_per_m_input"], cfg["price_per_m_output"],
                _get_groq_key("cheap"), PROVIDERS_REGISTRY["groq"]["base_url"],
                messages=messages, max_tokens=effective_max, temperature=temperature,
            )
            return

    cfg = MODEL_CONFIG[tier]
    yield from _stream_openai_compatible(
        cfg["model_id"], query, tier,
        cfg["price_per_m_input"], cfg["price_per_m_output"],
        _get_groq_key(tier), PROVIDERS_REGISTRY["groq"]["base_url"],
        messages=messages, max_tokens=effective_max, temperature=temperature,
    )


def validate_key(provider: str, model_id: str, api_key: str) -> bool:
    """
    Makes a minimal test call (max_tokens=1) to verify the key + model work.
    Returns True if successful, raises an exception with the error message if not.
    """
    call_provider(
        provider=provider,
        model_id=model_id,
        query="hi",
        tier_label="test",
        api_key=api_key,
        price_in=0.0,
        price_out=0.0,
        max_tokens=1,
    )
    return True
