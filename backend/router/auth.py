# Auth layer: API key validation, rate limiting, budget enforcement, JWT verification.
import time
import logging
import httpx
from collections import defaultdict
from fastapi import Header, HTTPException, Request
from router.db import SessionLocal, ApiKey
from router.budgets import budget_status
from router.config import SUPABASE_URL, SUPABASE_SERVICE_KEY, ADMIN_USER_ID

log = logging.getLogger("routewise.auth")

# Two budgets, on purpose.
#
# A provider call spends the user's money, so it gets the tight limit. The
# dashboard's own free traffic -- the /route/explain preview that scores as you
# type, and the /stats and /config polls -- gets a much larger SEPARATE budget,
# so it can never spend the real requests' budget.
#
# Before this split there was one 20/min budget shared by every authenticated
# endpoint on a single key, and the public demo's key is baked into the
# frontend bundle, so it was also shared by every visitor. The dashboard polls
# /stats every 12-15s and called /route/explain on a 450ms debounce, so two
# people opening the site emptied the bucket and every genuine question came
# back 429 Too Many Requests.
RATE_LIMIT_PER_MINUTE = 60
READ_RATE_LIMIT_PER_MINUTE = 240

# Endpoints that never reach a provider. Classified by prefix so a brand new
# route defaults to costing money until someone says otherwise: an
# over-permissive list would let a caller drain the model budget for free.
_READ_ONLY_PREFIXES = (
    # /route and /openai are deliberately absent: anything not listed here is
    # treated as a provider call, so a route added later costs money until
    # someone classifies it.
    "/route/explain",
    "/route/policies",
    "/route/feedback",
    "/stats",
    "/logs",
    "/analytics",
    "/policy-analytics",
    "/calibrate",
    "/compare",
    "/config",
    "/settings",
    "/keys",
    "/teams",
    "/admin",
    "/alerts",
    "/catalog",
    "/tiers",
    "/pricing",
    "/providers",
    "/project",
    "/evaluate",
    "/demo/chaos",
)


def rate_limit_bucket(path: str) -> str:
    """Which budget a request path spends: 'read' (free) or 'call' (costs money)."""
    return "read" if path.startswith(_READ_ONLY_PREFIXES) else "call"


# (bucket, api_key) -> list of request timestamps (sliding window)
_request_log: dict[str, list[float]] = defaultdict(list)
_MAX_TRACKED_KEYS = 10_000  # prevent unbounded memory growth

# In-memory API key cache: key_string -> (record_or_None, timestamp)
# Avoids hitting Supabase on every request. TTL: 30 seconds.
_KEY_CACHE_TTL = 30
_key_cache: dict[str, tuple[ApiKey | None, float]] = {}


def invalidate_key_cache(key_string: str = None):
    """Clear cached key. Call after key creation/revocation."""
    if key_string:
        _key_cache.pop(key_string, None)
    else:
        _key_cache.clear()


def check_rate_limit(api_key: str, bucket: str = "call"):
    limit = READ_RATE_LIMIT_PER_MINUTE if bucket == "read" else RATE_LIMIT_PER_MINUTE
    now = time.time()
    window_start = now - 60
    tracked = f"{bucket}:{api_key}"
    _request_log[tracked] = [t for t in _request_log[tracked] if t > window_start]
    if len(_request_log[tracked]) >= limit:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit: max {limit} requests/minute per key",
        )
    _request_log[tracked].append(now)
    # Evict oldest tracked keys if memory growing too large
    if len(_request_log) > _MAX_TRACKED_KEYS:
        cutoff = now - 120  # remove keys with no activity in 2 minutes
        stale = [k for k, ts in _request_log.items() if not ts or max(ts) < cutoff]
        for k in stale[:len(stale) // 2]:
            del _request_log[k]


def check_budget(api_key_record: ApiKey) -> bool:
    """True when no cap is exhausted.

    Kept as a boolean because that is what callers and tests want; the richer
    BudgetStatus is available from router.budgets when a caller needs to say
    which cap tripped.
    """
    return budget_status(api_key_record).allowed


def _lookup_key_cached(key: str) -> ApiKey | None:
    """Look up API key with in-memory cache. Returns record or None."""
    now = time.time()
    if key in _key_cache:
        record, ts = _key_cache[key]
        if now - ts < _KEY_CACHE_TTL:
            return record
    session = SessionLocal()
    try:
        record = session.query(ApiKey).filter(ApiKey.key == key, ApiKey.is_active == True).first()
    finally:
        session.close()
    _key_cache[key] = (record, now)
    return record


async def require_api_key(request: Request, authorization: str = Header(None)) -> ApiKey:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header. Expected: Bearer <key>")

    key = authorization.removeprefix("Bearer ").strip()
    record = _lookup_key_cached(key)

    if record is None:
        raise HTTPException(status_code=401, detail="Invalid or inactive API key")

    # Pick the budget from the path so the dashboard's free traffic cannot
    # exhaust the budget the provider calls need.
    check_rate_limit(key, rate_limit_bucket(request.url.path))
    return record


async def require_user(authorization: str = Header(None)) -> str:
    """Verifies Supabase JWT and returns the user_id (UUID string)."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")

    token = authorization.removeprefix("Bearer ").strip()

    try:
        resp = httpx.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={"Authorization": f"Bearer {token}", "apikey": SUPABASE_SERVICE_KEY},
            timeout=5,
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=401, detail="Invalid or expired session")
        return resp.json()["id"]
    except HTTPException:
        raise
    except Exception as e:
        log.warning("require_user exception: %s", e)
        raise HTTPException(status_code=401, detail="Could not verify session")


async def require_admin_any(request: Request, authorization: str = Header(None)) -> str:
    """Accepts either API key (rw_...) or Supabase JWT. Returns admin user_id."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing auth")

    token = authorization.removeprefix("Bearer ").strip()

    if token.startswith("rw_"):
        record = _lookup_key_cached(token)
        if record and record.user_id and is_admin_user_id(record.user_id):
            # Admin reads (/admin/stats, /admin/keys, ...) are dashboard
            # traffic: they must spend the read budget, not the model budget.
            check_rate_limit(token, rate_limit_bucket(request.url.path))
            return record.user_id
        raise HTTPException(status_code=403, detail="Admin access required (API key)")

    user_id = await require_user(authorization)
    if not is_admin_user_id(user_id):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user_id


def is_admin_user_id(user_id: str | None) -> bool:
    """Check if a user_id belongs to the admin. Used for optional admin checks."""
    return bool(user_id) and user_id == ADMIN_USER_ID


async def require_any_auth(request: Request, authorization: str = Header(None)):
    """Accepts either API key (rw_...) or Supabase JWT. Returns the auth identity."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing auth")

    token = authorization.removeprefix("Bearer ").strip()

    if token.startswith("rw_"):
        record = _lookup_key_cached(token)
        if record:
            check_rate_limit(token, rate_limit_bucket(request.url.path))
            return {"type": "api_key", "record": record, "user_id": record.user_id}
        raise HTTPException(status_code=401, detail="Invalid API key")

    user_id = await require_user(authorization)
    return {"type": "jwt", "record": None, "user_id": user_id}