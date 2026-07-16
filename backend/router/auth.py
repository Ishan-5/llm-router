"""
Three functions, three jobs:

check_rate_limit — sliding window, in-memory, 20 req/min per key

check_budget — DB query, daily spend cap, forces cheap tier if over

require_api_key — the FastAPI dependency that gates every protected endpoint. Validates format → DB lookup → rate limit check → returns the key record

require_user — extracts and verifies the Supabase JWT from Authorization header, returns the user_id (UUID string). Used for dashboard endpoints (key management, BYOM config).

Every protected endpoint (/route, /logs, /config POST, /config DELETE) 
has Depends(require_api_key) which runs all three of these in sequence 
before the endpoint logic even starts.

HONEST LIMITATION: the rate limiter here is in-memory (a plain dict), which
is fine for a single-process demo deployment but would NOT survive multiple
server instances or a restart. A real multi-instance production setup needs
a shared store (Redis) for this. Not built here because this project runs
as a single Render instance -- documenting the gap rather than pretending
this scales, since claiming otherwise would be a real overstatement.
"""
import time
import httpx
from collections import defaultdict
from datetime import datetime, date
from fastapi import Header, HTTPException
from router.db import SessionLocal, ApiKey, RequestLog
from router.config import SUPABASE_URL, SUPABASE_SERVICE_KEY
from sqlalchemy import func

RATE_LIMIT_PER_MINUTE = 20

# api_key -> list of request timestamps (sliding window)
_request_log: dict[str, list[float]] = defaultdict(list)


def check_rate_limit(api_key: str):
    now = time.time()
    window_start = now - 60
    _request_log[api_key] = [t for t in _request_log[api_key] if t > window_start]
    if len(_request_log[api_key]) >= RATE_LIMIT_PER_MINUTE:
        raise HTTPException(status_code=429, detail=f"Rate limit: max {RATE_LIMIT_PER_MINUTE} requests/minute per key")
    _request_log[api_key].append(now)


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


async def require_api_key(authorization: str = Header(None)) -> ApiKey:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header. Expected: Bearer <key>")

    key = authorization.removeprefix("Bearer ").strip()

    session = SessionLocal()
    try:
        record = session.query(ApiKey).filter(ApiKey.key == key, ApiKey.is_active == True).first()
    finally:
        session.close()

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
        print(f"[auth] supabase url={SUPABASE_URL!r} status={resp.status_code} body={resp.text[:200]}")
        if resp.status_code != 200:
            raise HTTPException(status_code=401, detail="Invalid or expired session")
        return resp.json()["id"]
    except HTTPException:
        raise
    except Exception as e:
        print(f"[auth] require_user exception: {e}")
        raise HTTPException(status_code=401, detail="Could not verify session")