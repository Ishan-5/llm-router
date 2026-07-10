from groq import Groq
from router.config import GROQ_API_KEY, MODEL_CONFIG, OLLAMA_FALLBACK_CONFIG
from router.ollama_client import call_ollama

client = Groq(api_key=GROQ_API_KEY)

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
            print(f"[ollama] local call failed ({e}), falling back to Groq cheap model")
            cfg = OLLAMA_FALLBACK_CONFIG
            result = _call_groq(cfg["model_id"], cfg["price_per_m_input"], cfg["price_per_m_output"], query, "cheap")
            result["ollama_fallback"] = True
            return result

    cfg = MODEL_CONFIG[tier]
    return _call_groq(cfg["model_id"], cfg["price_per_m_input"], cfg["price_per_m_output"], query, tier)