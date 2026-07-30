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
import logging
from router.config import FALLBACK_CHAIN
from router.providers import call_model, call_gemini
from router.model_config_loader import get_active_config
from router.load_balancer import report_rate_limit_from_error
from router.circuit_breaker import get_breaker

log = logging.getLogger("routewise.failover")


class AllTiersFailedError(Exception):
    """Raised when the intended tier AND every fallback tier failed."""
    pass


def _is_rate_limit_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "rate_limit" in msg or "rate limit" in msg or "too many requests" in msg


def _call_with_one_retry(tier: str, query: str, user_config: dict, messages: list[dict] | None = None, max_tokens: int | None = None, temperature: float | None = None):
    """One quick retry for transient (non-rate-limit) errors only."""
    try:
        return call_model(tier, query, user_config.get(tier), messages=messages, max_tokens=max_tokens, temperature=temperature)
    except Exception as e:
        if _is_rate_limit_error(e):
            report_rate_limit_from_error(tier, e)  # mark key as rate-limited in load balancer
            raise  # don't retry rate limits, caller will fall back immediately
        time.sleep(1)
        return call_model(tier, query, user_config.get(tier), messages=messages, max_tokens=max_tokens, temperature=temperature)  # let this one raise if it fails again


def call_with_failover(intended_tier: str, query: str, user_api_keys: dict | None = None, messages: list[dict] | None = None, max_tokens: int | None = None, temperature: float | None = None, user_config: dict | None = None) -> dict:
    """
    Tries intended_tier, then falls back through FALLBACK_CHAIN on failure.
    user_config: pre-built config from _preprocess (already has user overrides + injected keys).
                 If not passed, falls back to get_active_config() with no user_id.
    """
    if user_config is None:
        user_config = get_active_config()
        # inject api keys from request into the config for each tier
        if user_api_keys:
            for tier, key in user_api_keys.items():
                if tier in user_config and key:
                    user_config[tier]["api_key"] = key

    chain = [intended_tier] + FALLBACK_CHAIN.get(intended_tier, [])
    errors = []

    for i, tier in enumerate(chain):
        breaker = get_breaker(tier)
        if breaker.is_open():
            log.info("Circuit OPEN for '%s' — skipping", tier)
            errors.append(f"{tier}: circuit open")
            continue
        try:
            result = _call_with_one_retry(tier, query, user_config, messages=messages, max_tokens=max_tokens, temperature=temperature)
            breaker.record_success()
            result["intended_tier"] = intended_tier
            result["fallback_used"] = (tier != intended_tier)
            if result["fallback_used"]:
                log.info("'%s' failed, served by '%s' instead. Reason: %s",
                      intended_tier, tier, errors[-1] if errors else 'unknown')
            return result
        except Exception as e:
            breaker.record_failure()
            error_detail = f"{tier}: {type(e).__name__}: {e}"
            errors.append(error_detail)
            log.warning("tier '%s' failed -- %s", tier, error_detail)
            continue

    # Entire chain failed -- last resort: try a genuinely
    # independent provider before giving up completely.
    gemini_breaker = get_breaker("gemini")
    if not gemini_breaker.is_open():
        try:
            result = call_gemini(query)
            gemini_breaker.record_success()
            result["tier"] = intended_tier
            result["intended_tier"] = intended_tier
            result["fallback_used"] = True
            result["cross_provider_fallback"] = True
            log.info("entire chain failed for '%s', served by Gemini (independent provider) instead",
                  intended_tier)
            return result
        except Exception as e:
            gemini_breaker.record_failure()
            errors.append(f"gemini: {type(e).__name__}: {e}")
            log.error("Gemini last-resort also failed -- %s", errors[-1])
    else:
        log.warning("Gemini circuit also OPEN — all providers unavailable")

    raise AllTiersFailedError(
        f"All tiers failed for intended_tier='{intended_tier}'. Errors: {errors}"
    )