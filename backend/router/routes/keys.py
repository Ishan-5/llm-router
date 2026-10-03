import secrets
import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, field_validator
from router.db import SessionLocal, ApiKey
from router.auth import require_user, invalidate_key_cache

router = APIRouter()
log = logging.getLogger("routewise")


def _validate_budget(v):
    """None means unlimited. A budget of zero is legitimate -- it means spend nothing."""
    if v is None:
        return None
    if v < 0:
        raise ValueError("daily_budget_usd must be zero or greater")
    if v != v or v in (float("inf"), float("-inf")):
        raise ValueError("daily_budget_usd must be a finite number")
    return v


class KeyCreateRequest(BaseModel):
    name: str
    daily_budget_usd: float | None = None

    @field_validator("daily_budget_usd")
    @classmethod
    def check_budget(cls, v):
        return _validate_budget(v)


class KeyBudgetRequest(BaseModel):
    daily_budget_usd: float | None

    @field_validator("daily_budget_usd")
    @classmethod
    def check_budget(cls, v):
        return _validate_budget(v)


def _serialize(record: ApiKey) -> dict:
    return {
        "id": record.id,
        "key": record.key,
        "name": record.name,
        "daily_budget_usd": record.daily_budget_usd,
        "created_at": record.created_at.isoformat(),
    }


@router.get("/keys")
def get_keys(user_id: str = Depends(require_user)):
    session = SessionLocal()
    try:
        rows = session.query(ApiKey).filter(ApiKey.user_id == user_id, ApiKey.is_active == True).all()
        return [_serialize(r) for r in rows]
    finally:
        session.close()


@router.post("/keys")
def create_key(req: KeyCreateRequest, user_id: str = Depends(require_user)):
    key = "rw_" + secrets.token_urlsafe(32)
    session = SessionLocal()
    try:
        record = ApiKey(
            key=key,
            name=req.name.strip(),
            user_id=user_id,
            daily_budget_usd=req.daily_budget_usd,
        )
        session.add(record)
        session.commit()
        return {"key": key, "name": record.name, "daily_budget_usd": record.daily_budget_usd, "created_at": record.created_at.isoformat()}
    finally:
        session.close()


@router.patch("/keys/{key_id}")
def update_key_budget(key_id: int, req: KeyBudgetRequest, user_id: str = Depends(require_user)):
    """Set or clear a key's daily spend cap.

    The auth layer caches each key record for 30 seconds, so a budget change must
    invalidate that entry or the old cap keeps being enforced until the TTL lapses.
    """
    session = SessionLocal()
    try:
        record = session.query(ApiKey).filter(ApiKey.id == key_id, ApiKey.user_id == user_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="Key not found")
        record.daily_budget_usd = req.daily_budget_usd
        session.commit()
        key_string = record.key
    finally:
        session.close()
    invalidate_key_cache(key_string)
    return {"id": key_id, "daily_budget_usd": req.daily_budget_usd}


@router.delete("/keys/{key_id}")
def revoke_key(key_id: int, user_id: str = Depends(require_user)):
    session = SessionLocal()
    try:
        record = session.query(ApiKey).filter(ApiKey.id == key_id, ApiKey.user_id == user_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="Key not found")
        record.is_active = False
        session.commit()
        invalidate_key_cache(record.key)
    finally:
        session.close()
    return {"revoked": key_id}