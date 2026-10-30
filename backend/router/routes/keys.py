import secrets
import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, field_validator
from router.db import SessionLocal, ApiKey, Team
from router.auth import require_user, invalidate_key_cache
from router.key_prefs import POLICIES, TIERS
from router.budgets import (
    budget_status,
    get_team,
    invalidate_team_cache,
    key_spend,
    month_start,
)

router = APIRouter()
log = logging.getLogger("routewise")


def _validate_budget(v):
    """None means unlimited. A budget of zero is legitimate -- it means spend nothing."""
    if v is None:
        return None
    if v < 0:
        raise ValueError("budget must be zero or greater")
    if v != v or v in (float("inf"), float("-inf")):
        raise ValueError("budget must be a finite number")
    return v


def _validate_policy(v):
    """Empty means 'no key-level policy'; the request or generic wins."""
    if v is None or v == "":
        return None
    if v not in POLICIES:
        raise ValueError(f"default_policy must be one of {list(POLICIES)}")
    return v


def _validate_max_tier(v):
    """Empty means no ceiling. 'frontier' is accepted as an explicit no-op."""
    if v is None or v == "":
        return None
    if v not in TIERS:
        raise ValueError(f"max_tier must be one of {list(TIERS)}")
    return v


def _validate_threshold(v):
    if v is None:
        return None
    if v < 0.0 or v > 2.0:
        raise ValueError("default_threshold must be between 0.0 and 2.0")
    return v


class KeyCreateRequest(BaseModel):
    name: str
    daily_budget_usd: float | None = None
    monthly_budget_usd: float | None = None
    team_id: int | None = None
    default_policy: str | None = None
    max_tier: str | None = None
    default_threshold: float | None = None
    cache_enabled: bool | None = None

    @field_validator("daily_budget_usd", "monthly_budget_usd")
    @classmethod
    def check_budget(cls, v):
        return _validate_budget(v)

    @field_validator("default_policy")
    @classmethod
    def check_policy(cls, v):
        return _validate_policy(v)

    @field_validator("max_tier")
    @classmethod
    def check_max_tier(cls, v):
        return _validate_max_tier(v)

    @field_validator("default_threshold")
    @classmethod
    def check_threshold(cls, v):
        return _validate_threshold(v)


class KeyUpdateRequest(BaseModel):
    """Any subset of fields. Unset fields are left alone, explicit null clears."""
    name: str | None = None
    daily_budget_usd: float | None = None
    monthly_budget_usd: float | None = None
    team_id: int | None = None
    default_policy: str | None = None
    max_tier: str | None = None
    default_threshold: float | None = None
    cache_enabled: bool | None = None

    @field_validator("daily_budget_usd", "monthly_budget_usd")
    @classmethod
    def check_budget(cls, v):
        return _validate_budget(v)

    @field_validator("default_policy")
    @classmethod
    def check_policy(cls, v):
        return _validate_policy(v)

    @field_validator("max_tier")
    @classmethod
    def check_max_tier(cls, v):
        return _validate_max_tier(v)

    @field_validator("default_threshold")
    @classmethod
    def check_threshold(cls, v):
        return _validate_threshold(v)


def _own_team(session, team_id, user_id) -> Team | None:
    if team_id is None:
        return None
    team = session.query(Team).filter(
        Team.id == team_id, Team.user_id == user_id, Team.is_active == True
    ).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return team


def _serialize(record: ApiKey, session) -> dict:
    team = get_team(session, record.team_id)
    status = budget_status(record, session)
    spent_month = key_spend(session, record.id, month_start())
    return {
        "id": record.id,
        "key": record.key,
        "name": record.name,
        "team_id": record.team_id,
        "team_name": team.name if team else None,
        "daily_budget_usd": record.daily_budget_usd,
        "monthly_budget_usd": record.monthly_budget_usd,
        "default_policy": record.default_policy,
        "max_tier": record.max_tier,
        "default_threshold": record.default_threshold,
        "cache_enabled": record.cache_enabled is not False,
        "spent_this_month": round(spent_month, 6),
        "budget": status.as_dict(),
        "created_at": record.created_at.isoformat(),
    }


@router.get("/keys")
def get_keys(user_id: str = Depends(require_user)):
    session = SessionLocal()
    try:
        rows = session.query(ApiKey).filter(ApiKey.user_id == user_id, ApiKey.is_active == True).all()
        return [_serialize(r, session) for r in rows]
    finally:
        session.close()


@router.post("/keys")
def create_key(req: KeyCreateRequest, user_id: str = Depends(require_user)):
    key = "rw_" + secrets.token_urlsafe(32)
    session = SessionLocal()
    try:
        team = _own_team(session, req.team_id, user_id)
        record = ApiKey(
            key=key,
            name=req.name.strip(),
            user_id=user_id,
            team_id=team.id if team else None,
            daily_budget_usd=req.daily_budget_usd,
            monthly_budget_usd=req.monthly_budget_usd,
            default_policy=req.default_policy,
            max_tier=req.max_tier,
            default_threshold=req.default_threshold,
            cache_enabled=True if req.cache_enabled is None else req.cache_enabled,
        )
        session.add(record)
        session.commit()
        session.refresh(record)
        return _serialize(record, session)
    finally:
        session.close()


@router.patch("/keys/{key_id}")
def update_key(key_id: int, req: KeyUpdateRequest, user_id: str = Depends(require_user)):
    """Edit a key's caps, team or name.

    The auth layer caches each key record for 30 seconds, so a budget change must
    invalidate that entry or the old cap keeps being enforced until the TTL lapses.
    """
    session = SessionLocal()
    try:
        record = session.query(ApiKey).filter(ApiKey.id == key_id, ApiKey.user_id == user_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="Key not found")

        fields = req.model_dump(exclude_unset=True)
        if "team_id" in fields:
            team = _own_team(session, fields["team_id"], user_id)
            record.team_id = team.id if team else None
        if "name" in fields:
            name = (fields["name"] or "").strip()
            if not name:
                raise HTTPException(status_code=400, detail="name cannot be empty")
            record.name = name
        if "daily_budget_usd" in fields:
            record.daily_budget_usd = fields["daily_budget_usd"]
        if "monthly_budget_usd" in fields:
            record.monthly_budget_usd = fields["monthly_budget_usd"]
        if "default_policy" in fields:
            record.default_policy = fields["default_policy"]
        if "max_tier" in fields:
            record.max_tier = fields["max_tier"]
        if "default_threshold" in fields:
            record.default_threshold = fields["default_threshold"]
        if "cache_enabled" in fields:
            record.cache_enabled = True if fields["cache_enabled"] is None else fields["cache_enabled"]

        session.commit()
        session.refresh(record)
        key_string = record.key
        payload = _serialize(record, session)
    finally:
        session.close()
    invalidate_key_cache(key_string)
    invalidate_team_cache()
    return payload


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
