"""
Three functions, three jobs:

check_rate_limit — sliding window, in-memory, 20 req/min per key

check_budget — DB query, daily spend cap, forces cheap tier if over

require_api_key — the FastAPI dependency that gates every protected endpoint. Validates format → DB lookup → rate limit check → returns the key record

require_user — extracts and verifies the Supabase JWT from Authorization header, returns the user_id (UUID string). Used for dashboard endpoints (key management, BYOM config).

Every protected endpoint (/route, /logs, /config POST, /config DELETE) 
has Depends(require_api_key) which runs all three of these in sequence 
before the endpoint logic even starts.
"""
import time
import logging
import httpx
from collections import defaultdict
from datetime import datetime, date
from fastapi import Header, HTTPException
from router.db import SessionLocal, ApiKey, RequestLog
from router.config import SUPABASE_URL, SUPABASE_SERVICE_KEY, ADMIN_USER_ID
from sqlalchemy import func

log = logging.getLogger("routewise.auth")

RATE_LIMIT_PER_MINUTE = 20

# api_key -> list of request timestamps (sliding window)
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


def check_rate_limit(api_key: str):
    now = time.time()
    window_start = now - 60
    _request_log[api_key] = [t for t in _request_log[api_key] if t > window_start]
    if len(_request_log[api_key]) >= RATE_LIMIT_PER_MINUTE:
        raise HTTPException(status_code=429, detail=f"Rate limit: max {RATE_LIMIT_PER_MINUTE} requests/minute per key")
    _request_log[api_key].append(now)
    # Evict oldest tracked keys if memory growing too large
    if len(_request_log) > _MAX_TRACKED_KEYS:
        cutoff = now - 120  # remove keys with no activity in 2 minutes
        stale = [k for k, ts in _request_log.items() if not ts or max(ts) < cutoff]
        for k in stale[:len(stale) // 2]:
            del _request_log[k]


def check_budget(api_key_record: ApiKey) -> bool:
    if api_key_record.daily_budget_usd is None:
        return True

    session = SessionLocal()
    try:
        today_start = datetime.combine(date.today(), datetime.min.time())
        spent_today = session.query(func.sum(RequestLog.cost_usd)).filter(
            RequestLog.api_key_id == api_key_record.id,
            RequestLog.created_at >= today_start,
        ).scalar() or 0.0
        return spent_today < api_key_record.daily_budget_usd
    finally:
        session.close()


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


async def require_api_key(authorization: str = Header(None)) -> ApiKey:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header. Expected: Bearer <key>")

    key = authorization.removeprefix("Bearer ").strip()
    record = _lookup_key_cached(key)

    if record is None:
        raise HTTPException(status_code=401, detail="Invalid or inactive API key")

    check_rate_limit(key)
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


async def require_admin(authorization: str = Header(None)) -> str:
    """Verifies Supabase JWT and returns user_id only if it matches ADMIN_USER_ID."""
    user_id = await require_user(authorization)
    if user_id != ADMIN_USER_ID:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user_id


async def require_admin_api_key(authorization: str = Header(None)) -> ApiKey:
    """API-key-based admin check. Returns the ApiKey record if key belongs to admin user."""
    api_key = await require_api_key(authorization)
    if not is_admin_user_id(api_key.user_id):
        raise HTTPException(status_code=403, detail="Admin access required")
    return api_key


async def require_admin_any(authorization: str = Header(None)) -> str:
    """Accepts either API key (rw_...) or Supabase JWT. Returns admin user_id."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing auth")

    token = authorization.removeprefix("Bearer ").strip()

    if token.startswith("rw_"):
        record = _lookup_key_cached(token)
        if record and record.user_id and is_admin_user_id(record.user_id):
            check_rate_limit(token)
            return record.user_id
        raise HTTPException(status_code=403, detail="Admin access required (API key)")

    user_id = await require_user(authorization)
    if not is_admin_user_id(user_id):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user_id


def is_admin_user_id(user_id: str | None) -> bool:
    """Check if a user_id belongs to the admin. Used for optional admin checks."""
    return bool(user_id) and user_id == ADMIN_USER_ID


async def require_any_auth(authorization: str = Header(None)):
    """Accepts either API key (rw_...) or Supabase JWT. Returns the auth identity."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing auth")

    token = authorization.removeprefix("Bearer ").strip()

    if token.startswith("rw_"):
        record = _lookup_key_cached(token)
        if record:
            check_rate_limit(token)
            return {"type": "api_key", "record": record, "user_id": record.user_id}
        raise HTTPException(status_code=401, detail="Invalid API key")

    user_id = await require_user(authorization)
    return {"type": "jwt", "record": None, "user_id": user_id}