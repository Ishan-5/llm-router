import logging

from router.db import SessionLocal, UserConfig, ModelPricing, KeyProviderConfig
from router.config import MODEL_CONFIG, OLLAMA_FALLBACK_CONFIG
from router.providers_registry import PROVIDERS_REGISTRY

log = logging.getLogger("routewise")

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


def resolve_tier_pricing(provider: str, model_id: str, fallback_in: float, fallback_out: float) -> tuple[float, float]:
    """
    Resolve pricing for a (provider, model_id) pair after a BYOM override.
    Looks up the model_pricing table by provider AND model_id so we never price a
    request with another model's rates. Returns the caller's fallback when the
    model is not in the table (e.g. a user-supplied custom model).
    """
    session = SessionLocal()
    try:
        row = session.query(ModelPricing).filter(
            ModelPricing.provider == provider,
            ModelPricing.model_id == model_id,
            ModelPricing.is_active == True,
        ).first()
        if row:
            return row.price_per_m_input, row.price_per_m_output
    finally:
        session.close()
    return fallback_in, fallback_out


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


def get_active_config(user_id: str | None = None, key_id: int | None = None) -> dict:
    """
    Returns the merged config for all 3 tiers.

    Precedence per tier: a BYOM row on the calling key, then the user's saved
    account config, then the server defaults. Request-level overrides are
    applied by the route handlers on top of this, so a request still wins.
    """
    from router.secret_store import decrypt

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

        key_rows = {}
        if key_id is not None:
            key_rows = {
                row.tier: row
                for row in session.query(KeyProviderConfig).filter(
                    KeyProviderConfig.api_key_id == key_id
                ).all()
            }

        merged = {}
        for tier, defaults in PROVIDER_DEFAULTS.items():
            cfg = defaults.copy()
            if tier in user_overrides:
                cfg = {**cfg, **user_overrides[tier]}

            stored_prices = False
            store = key_rows.get(tier)
            if store is not None:
                secret = decrypt(store.api_key_encrypted) if store.api_key_encrypted else None
                # Never silently send one provider's credential to another, and
                # never call a provider that needs a key without one: fall back
                # to the account default for this tier instead.
                if store.api_key_encrypted and secret is None:
                    log.warning(
                        "ignoring BYOM for key %s tier %s: credential unreadable", key_id, tier
                    )
                elif store.provider != "ollama" and secret is None:
                    log.warning(
                        "ignoring BYOM for key %s tier %s: no credential stored", key_id, tier
                    )
                else:
                    cfg["provider"] = store.provider
                    cfg["model_id"] = store.model_id
                    if secret:
                        cfg["api_key"] = secret
                    if store.price_per_m_input is not None and store.price_per_m_output is not None:
                        cfg["price_per_m_input"] = store.price_per_m_input
                        cfg["price_per_m_output"] = store.price_per_m_output
                        stored_prices = True

            # look up real pricing from DB, fall back to defaults if not found
            if not stored_prices:
                pricing = _get_pricing(session, cfg["provider"], cfg["model_id"])
                if pricing:
                    cfg["price_per_m_input"], cfg["price_per_m_output"] = pricing

            merged[tier] = cfg
    finally:
        session.close()

    return merged
