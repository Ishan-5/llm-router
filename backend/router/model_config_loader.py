"""
Merges user-supplied model config (from user_configs table) with the
hardcoded defaults. Any tier the user hasn't configured falls back to
the default model for that tier.
"""
from router.db import SessionLocal, UserConfig
from router.config import MODEL_CONFIG, OLLAMA_FALLBACK_CONFIG
from router.providers_registry import PROVIDERS_REGISTRY

# Validate that default providers exist in the registry
assert "ollama" in PROVIDERS_REGISTRY
assert "groq" in PROVIDERS_REGISTRY

PROVIDER_DEFAULTS = {
    "cheap": {
        "provider": "ollama",
        "model_id": "llama3.2",
        "price_per_m_input": OLLAMA_FALLBACK_CONFIG["price_per_m_input"],
        "price_per_m_output": OLLAMA_FALLBACK_CONFIG["price_per_m_output"],
    },
    "mid": {
        "provider": "groq",
        "model_id": MODEL_CONFIG["mid"]["model_id"],
        "price_per_m_input": MODEL_CONFIG["mid"]["price_per_m_input"],
        "price_per_m_output": MODEL_CONFIG["mid"]["price_per_m_output"],
    },
    "frontier": {
        "provider": "groq",
        "model_id": "qwen/qwen3-32b",
        "price_per_m_input": 0.29,
        "price_per_m_output": 0.59,
    },
}


def get_active_config() -> dict:
    """
    Returns the merged config for all 3 tiers.
    User config (latest row per tier) overrides defaults.
    Missing tiers fall back to PROVIDER_DEFAULTS.
    """
    session = SessionLocal()
    try:
        rows = session.query(UserConfig).order_by(UserConfig.created_at.desc()).all()
    finally:
        session.close()

    # latest row per tier wins
    user_overrides = {}
    for row in rows:
        if row.tier not in user_overrides:
            user_overrides[row.tier] = {
                "provider": row.provider,
                "model_id": row.model_id,
            }

    merged = {}
    for tier, defaults in PROVIDER_DEFAULTS.items():
        if tier in user_overrides:
            merged[tier] = {**defaults, **user_overrides[tier]}
        else:
            merged[tier] = defaults.copy()

    return merged
