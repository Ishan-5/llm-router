from groq import Groq
from openai import OpenAI
from router.config import GROQ_API_KEY, GEMINI_API_KEY, MODEL_CONFIG, OLLAMA_FALLBACK_CONFIG, GEMINI_FALLBACK_CONFIG
from router.ollama_client import call_ollama

client = Groq(api_key=GROQ_API_KEY)

_gemini_client = None

def _call_groq(model_id: str, price_in: float, price_out: float, query: str, tier_label: str) -> dict:
    response = client.chat.completions.create(
        model=model_id,
        max_tokens=1000,
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


def call_model(tier: str, query: str) -> dict:
    if tier == "cheap":
        try:
            return call_ollama(query)
        except Exception as e:
            # Ollama not running / model missing / connection refused, etc.
            # Fall back to Groq's cheap model, but keep tier="cheap" so the
            # frontend/logs still treat this as the cheap tier -- just a
            # different backend served it.
            print(f"[ollama] local call failed ({e}), falling back to Groq cheap model")
            cfg = OLLAMA_FALLBACK_CONFIG
            result = _call_groq(cfg["model_id"], cfg["price_per_m_input"], cfg["price_per_m_output"], query, "cheap")
            result["ollama_fallback"] = True
            return result

    cfg = MODEL_CONFIG[tier]
    return _call_groq(cfg["model_id"], cfg["price_per_m_input"], cfg["price_per_m_output"], query, tier)


def call_gemini(query: str) -> dict:
    """
    Last-resort fallback: a genuinely independent provider (Google, not Groq).
    Only called if the entire normal tier chain has already failed -- see
    rate_limiter.py. Not part of the normal MODEL_CONFIG tier system on
    purpose, since this isn't a routing decision, it's a "everything else
    already failed" safety net.
    """
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = OpenAI(
            api_key=GEMINI_API_KEY,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
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