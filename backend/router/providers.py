from groq import Groq
from openai import OpenAI
from router.config import GROQ_API_KEY, GEMINI_API_KEY, MODEL_CONFIG, OLLAMA_FALLBACK_CONFIG, GEMINI_FALLBACK_CONFIG
from router.providers_registry import PROVIDERS_REGISTRY
from router.ollama_client import call_ollama

# default Groq client (used when no user api key supplied)
_default_groq_client = Groq(api_key=GROQ_API_KEY)
_gemini_client = None


def _call_openai_compatible(
    model_id: str,
    query: str,
    tier_label: str,
    price_in: float,
    price_out: float,
    api_key: str,
    base_url: str,
    max_tokens: int = 1000,
) -> dict:
    """
    Generic caller for any OpenAI-compatible API.
    Covers: Groq, OpenAI, DeepSeek, Perplexity, Mistral, xAI, Gemini.
    """
    client = OpenAI(api_key=api_key, base_url=base_url)
    response = client.chat.completions.create(
        model=model_id,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": query}],
    )
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


def _call_anthropic(
    model_id: str,
    query: str,
    tier_label: str,
    price_in: float,
    price_out: float,
    api_key: str,
    max_tokens: int = 1000,
) -> dict:
    """Anthropic has its own SDK and API format -- handled separately."""
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model_id,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": query}],
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
) -> dict:
    """
    Routes to the correct provider caller based on provider name.
    Used by both call_model (normal routing) and validate_key (test calls).
    """
    if provider == "ollama":
        return call_ollama(query, model=model_id)

    if provider == "anthropic":
        return _call_anthropic(model_id, query, tier_label, price_in, price_out, api_key, max_tokens)

    # All other providers are OpenAI-compatible
    base_url = PROVIDERS_REGISTRY[provider]["base_url"]
    return _call_openai_compatible(model_id, query, tier_label, price_in, price_out, api_key, base_url, max_tokens)


def call_model(tier: str, query: str, user_config: dict | None = None) -> dict:
    """
    Calls the model for the given tier.
    If user_config is provided (from model_config_loader), uses the user's
    provider/model/api_key. Otherwise falls back to the hardcoded defaults.
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
                api_key = GROQ_API_KEY
            elif provider == "gemini":
                api_key = GEMINI_API_KEY

        if provider == "ollama":
            try:
                return call_ollama(query, model=model_id)
            except Exception as e:
                print(f"[ollama] local call failed ({e}), falling back to Groq cheap model")
                cfg = OLLAMA_FALLBACK_CONFIG
                result = _call_openai_compatible(
                    cfg["model_id"], query, tier,
                    cfg["price_per_m_input"], cfg["price_per_m_output"],
                    GROQ_API_KEY, PROVIDERS_REGISTRY["groq"]["base_url"],
                )
                result["ollama_fallback"] = True
                return result

        return call_provider(provider, model_id, query, tier, api_key, price_in, price_out)

    # --- default path (no user config) ---
    if tier == "cheap":
        try:
            return call_ollama(query)
        except Exception as e:
            print(f"[ollama] local call failed ({e}), falling back to Groq cheap model")
            cfg = OLLAMA_FALLBACK_CONFIG
            result = _call_openai_compatible(
                cfg["model_id"], query, "cheap",
                cfg["price_per_m_input"], cfg["price_per_m_output"],
                GROQ_API_KEY, PROVIDERS_REGISTRY["groq"]["base_url"],
            )
            result["ollama_fallback"] = True
            return result

    cfg = MODEL_CONFIG[tier]
    return _call_openai_compatible(
        cfg["model_id"], query, tier,
        cfg["price_per_m_input"], cfg["price_per_m_output"],
        GROQ_API_KEY, PROVIDERS_REGISTRY["groq"]["base_url"],
    )


def call_gemini(query: str) -> dict:
    """
    Last-resort fallback: independent provider if entire Groq/Ollama chain fails.
    See rate_limiter.py.
    """
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = OpenAI(
            api_key=GEMINI_API_KEY,
            base_url=PROVIDERS_REGISTRY["gemini"]["base_url"],
        )
    cfg = GEMINI_FALLBACK_CONFIG
    response = _gemini_client.chat.completions.create(
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
        "model_id": cfg["model_id"],
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost, 6),
    }


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
