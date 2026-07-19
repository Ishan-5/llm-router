"""
Handles provider failures by falling back to a cheaper/different tier
instead of failing the request outright.

Two distinct error types are handled differently, on purpose:
  - Rate limit (429): retrying the SAME model is pointless -- Groq's error
    tells you to wait minutes, and a live user request can't wait that long.
    So we skip immediately to the next tier in the fallback chain, AND mark
    the current key as rate-limited in the load balancer.
  - Transient errors (timeouts, connection issues, 5xx): these might
    succeed on a quick retry, so we retry once before falling back.

If every tier in the normal chain fails (e.g. a full Groq outage), Gemini
is tried once as a last resort -- a genuinely independent provider, not
just another tier of the same infrastructure.
"""
import time
from router.config import FALLBACK_CHAIN
from router.providers import call_model, call_gemini
from router.model_config_loader import get_active_config
from router.load_balancer import report_rate_limit_from_error


class AllTiersFailedError(Exception):
    """Raised when the intended tier AND every fallback tier failed."""
    pass


def _is_rate_limit_error(exc: Exception) -> bool:
    msg = str(exc)
    return "429" in msg or "rate_limit" in msg


def _call_with_one_retry(tier: str, query: str, user_config: dict, messages: list[dict] | None = None):
    """One quick retry for transient (non-rate-limit) errors only."""
    try:
        return call_model(tier, query, user_config.get(tier), messages=messages)
    except Exception as e:
        if _is_rate_limit_error(e):
            report_rate_limit_from_error(tier, e)  # mark key as rate-limited in load balancer
            raise  # don't retry rate limits, caller will fall back immediately
        time.sleep(1)
        return call_model(tier, query, user_config.get(tier), messages=messages)  # let this one raise if it fails again


def call_with_failover(intended_tier: str, query: str, user_api_keys: dict | None = None, messages: list[dict] | None = None) -> dict:
    """
    Tries intended_tier, then falls back through FALLBACK_CHAIN on failure.
    Loads active config (user overrides merged with defaults) once per call.
    user_api_keys: { tier: api_key } sent from frontend localStorage -- merged
    into config here so keys are never stored server-side.
    """
    user_config = get_active_config()

    # inject api keys from request into the config for each tier
    if user_api_keys:
        for tier, key in user_api_keys.items():
            if tier in user_config and key:
                user_config[tier]["api_key"] = key

    chain = [intended_tier] + FALLBACK_CHAIN.get(intended_tier, [])
    errors = []

    for i, tier in enumerate(chain):
        try:
            result = _call_with_one_retry(tier, query, user_config, messages=messages)
            result["intended_tier"] = intended_tier
            result["fallback_used"] = (tier != intended_tier)
            if result["fallback_used"]:
                print(f"[failover] '{intended_tier}' failed, served by '{tier}' instead. "
                      f"Reason '{intended_tier}' failed: {errors[-1] if errors else 'unknown'}")
            return result
        except Exception as e:
            error_detail = f"{tier}: {type(e).__name__}: {e}"
            errors.append(error_detail)
            print(f"[failover] tier '{tier}' failed -- {error_detail}")
            continue  # try next tier in the chain

    # Entire chain failed -- last resort: try a genuinely
    # independent provider before giving up completely.
    try:
        result = call_gemini(query)
        result["tier"] = intended_tier  # keep tier label consistent for frontend/logs
        result["intended_tier"] = intended_tier
        result["fallback_used"] = True
        result["cross_provider_fallback"] = True
        print(f"[failover] entire chain failed for '{intended_tier}', "
              f"served by Gemini (independent provider) instead")
        return result
    except Exception as e:
        errors.append(f"gemini: {type(e).__name__}: {e}")
        print(f"[failover] Gemini last-resort also failed -- {errors[-1]}")

    raise AllTiersFailedError(
        f"All tiers failed for intended_tier='{intended_tier}'. Errors: {errors}"
    )