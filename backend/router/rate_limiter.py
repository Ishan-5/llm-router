import time
from router.config import FALLBACK_CHAIN
from router.providers import call_model


class AllTiersFailedError(Exception):
    pass


def _is_rate_limit_error(exc: Exception) -> bool:
    msg = str(exc)
    return "429" in msg or "rate_limit" in msg


def _call_with_one_retry(tier: str, query: str):
    """One quick retry for transient (non-rate-limit) errors only."""
    try:
        return call_model(tier, query)
    except Exception as e:
        if _is_rate_limit_error(e):
            raise 
        time.sleep(1)
        return call_model(tier, query)  


def call_with_failover(intended_tier: str, query: str) -> dict:
    chain = [intended_tier] + FALLBACK_CHAIN.get(intended_tier, [])
    errors = []

    for i, tier in enumerate(chain):
        try:
            result = _call_with_one_retry(tier, query)
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
            continue  

    raise AllTiersFailedError(
        f"All tiers failed for intended_tier='{intended_tier}'. Errors: {errors}"
    )