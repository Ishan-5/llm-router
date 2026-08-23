from router.db import SessionLocal, UserConfig, ModelPricing
from router.config import MODEL_CONFIG, OLLAMA_FALLBACK_CONFIG
from router.providers_registry import PROVIDERS_REGISTRY

assert "ollama" in PROVIDERS_REGISTRY
assert "groq" in PROVIDERS_REGISTRY

PROVIDER_DEFAULTS = {
    "cheap": {
        "provider": MODEL_CONFIG["cheap"]["provider"],
        "model_id": MODEL_CONFIG["cheap"]["model_id"],
        "price_per_m_input": MODEL_CONFIG["cheap"]["price_per_m_input"],
        "price_per_m_output": MODEL_CONFIG["cheap"]["price_per_m_output"],
    },
    "mid": {
        "provider": MODEL_CONFIG["mid"]["provider"],
        "model_id": MODEL_CONFIG["mid"]["model_id"],
        "price_per_m_input": MODEL_CONFIG["mid"]["price_per_m_input"],
        "price_per_m_output": MODEL_CONFIG["mid"]["price_per_m_output"],
    },
    "frontier": {
        "provider": MODEL_CONFIG["frontier"]["provider"],
        "model_id": MODEL_CONFIG["frontier"]["model_id"],
        "price_per_m_input": MODEL_CONFIG["frontier"]["price_per_m_input"],
        "price_per_m_output": MODEL_CONFIG["frontier"]["price_per_m_output"],
    },
}


def _get_pricing(session, provider: str, model_id: str) -> tuple[float, float]:
    """Look up input/output pricing from DB. Returns (price_in, price_out) or None if not found."""
    row = session.query(ModelPricing).filter(
        ModelPricing.provider == provider,
        ModelPricing.model_id == model_id,
        ModelPricing.is_active == True,
    ).first()
    if row:
        return row.price_per_m_input, row.price_per_m_output
    return None


def get_pricing_for_model(model_id: str) -> tuple[float, float]:
    """
    Returns (price_per_m_input, price_per_m_output) for a given model_id.
    Checks model_pricing table first (any provider), falls back to MODEL_CONFIG defaults.
    Used to compute exact cache savings against the model that originally served the response.
    """
    session = SessionLocal()
    try:
        row = session.query(ModelPricing).filter(
            ModelPricing.model_id == model_id,
            ModelPricing.is_active == True,
        ).first()
        if row:
            return row.price_per_m_input, row.price_per_m_output
    finally:
        session.close()
    # fall back to hardcoded defaults by matching model_id
    for cfg in MODEL_CONFIG.values():
        if cfg["model_id"] == model_id:
            return cfg["price_per_m_input"], cfg["price_per_m_output"]
    # unknown model — use cheap tier pricing as a floor
    return MODEL_CONFIG["cheap"]["price_per_m_input"], MODEL_CONFIG["cheap"]["price_per_m_output"]


def get_active_config(user_id: str | None = None) -> dict:
    """
    Returns the merged config for all 3 tiers.
    If user_id is provided, user config rows for that user override defaults.
    Falls back to PROVIDER_DEFAULTS for any tier not configured.
    """
    session = SessionLocal()
    try:
        query = session.query(UserConfig).order_by(UserConfig.created_at.desc())
        if user_id:
            query = query.filter(UserConfig.user_id == user_id)
        else:
            query = query.filter(UserConfig.user_id == None)
        rows = query.all()

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
                cfg = {**defaults, **user_overrides[tier]}
            else:
                cfg = defaults.copy()

            # look up real pricing from DB, fall back to defaults if not found
            pricing = _get_pricing(session, cfg["provider"], cfg["model_id"])
            if pricing:
                cfg["price_per_m_input"], cfg["price_per_m_output"] = pricing

            merged[tier] = cfg
    finally:
        session.close()

    return merged
