import secrets
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, field_validator
from router.db import SessionLocal, ApiKey, Team, KeyProviderConfig
from router.auth import require_user, invalidate_key_cache
from router.key_prefs import POLICIES, TIERS
from router.config import SUPPORTED_PROVIDERS
from router import secret_store
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


def _validate_price(v):
    if v is None:
        return None
    if v != v or v in (float("inf"), float("-inf")) or v < 0:
        raise ValueError("price must be a finite number, zero or greater")
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


class ByomTierRequest(BaseModel):
    """One tier's own model. ``api_key`` may be omitted to keep the stored one."""
    provider: str
    model_id: str
    api_key: str | None = None
    price_per_m_input: float | None = None
    price_per_m_output: float | None = None

    @field_validator("provider")
    @classmethod
    def check_provider(cls, v):
        if v not in SUPPORTED_PROVIDERS:
            raise ValueError(f"provider must be one of {SUPPORTED_PROVIDERS}")
        return v

    @field_validator("model_id")
    @classmethod
    def check_model_id(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("model_id cannot be empty")
        return v

    @field_validator("api_key")
    @classmethod
    def check_api_key(cls, v):
        if v is None:
            return None
        return v.strip() or None

    @field_validator("price_per_m_input", "price_per_m_output")
    @classmethod
    def check_price(cls, v):
        return _validate_price(v)


class KeyByomRequest(BaseModel):
    """Replace the key's BYOM config. A null or omitted tier uses the account default."""
    cheap: ByomTierRequest | None = None
    mid: ByomTierRequest | None = None
    frontier: ByomTierRequest | None = None


def _own_team(session, team_id, user_id) -> Team | None:
    if team_id is None:
        return None
    team = session.query(Team).filter(
        Team.id == team_id, Team.user_id == user_id, Team.is_active == True
    ).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return team


def _own_key(session, key_id, user_id) -> ApiKey:
    record = session.query(ApiKey).filter(
        ApiKey.id == key_id, ApiKey.user_id == user_id, ApiKey.is_active == True
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="Key not found")
    return record


def _byom_summary(session, key_id) -> dict:
    """Read-only view: provider/model/prices plus a hint, never the credential."""
    rows = session.query(KeyProviderConfig).filter(
        KeyProviderConfig.api_key_id == key_id
    ).all()
    return {
        row.tier: {
            "provider": row.provider,
            "model_id": row.model_id,
            "api_key_masked": row.api_key_hint or "",
            "has_api_key": bool(row.api_key_encrypted),
            "price_per_m_input": row.price_per_m_input,
            "price_per_m_output": row.price_per_m_output,
        }
        for row in rows
    }


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
        "byom": _byom_summary(session, record.id),
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


@router.get("/keys/{key_id}/byom")
def get_key_byom(key_id: int, user_id: str = Depends(require_user)):
    """The key's own models. Returns hints only, so the secret can be edited blind."""
    session = SessionLocal()
    try:
        _own_key(session, key_id, user_id)
        return {
            "byom": _byom_summary(session, key_id),
            "storage_ready": secret_store.available(),
        }
    finally:
        session.close()


@router.put("/keys/{key_id}/byom")
def set_key_byom(key_id: int, req: KeyByomRequest, user_id: str = Depends(require_user)):
    """Replace the key's BYOM config: a tier that is null or omitted uses the account default.

    Provider credentials are encrypted before they are stored and are never
    returned. Omitting ``api_key`` keeps the one already saved for that tier, so
    the dashboard can re-save a row without ever holding the secret in the page.
    """
    session = SessionLocal()
    try:
        _own_key(session, key_id, user_id)
        for tier in TIERS:
            cfg = getattr(req, tier)
            existing = session.query(KeyProviderConfig).filter(
                KeyProviderConfig.api_key_id == key_id, KeyProviderConfig.tier == tier
            ).first()
            if cfg is None:
                if existing:
                    session.delete(existing)
                continue

            keep_existing = (
                cfg.api_key is None
                and existing is not None
                and existing.provider == cfg.provider
                and bool(existing.api_key_encrypted)
            )
            if cfg.api_key is None and not keep_existing and cfg.provider != "ollama":
                raise HTTPException(
                    status_code=400,
                    detail=f"api_key is required for {tier} when the provider changes",
                )

            row = existing or KeyProviderConfig(api_key_id=key_id, tier=tier)
            if existing is None:
                session.add(row)
            row.provider = cfg.provider
            row.model_id = cfg.model_id
            row.price_per_m_input = cfg.price_per_m_input
            row.price_per_m_output = cfg.price_per_m_output
            if cfg.api_key is not None:
                encrypted = secret_store.encrypt(cfg.api_key)
                if encrypted is None:
                    raise HTTPException(
                        status_code=503,
                        detail="BYOM storage is not configured on this server (BYOM_ENCRYPTION_KEY)",
                    )
                row.api_key_encrypted = encrypted
                row.api_key_hint = secret_store.mask(cfg.api_key)
            elif cfg.provider == "ollama":
                # Ollama needs no credential; clearing it is the correct state.
                row.api_key_encrypted = None
                row.api_key_hint = ""
            row.updated_at = datetime.utcnow()

        session.commit()
        return {"byom": _byom_summary(session, key_id)}
    finally:
        session.close()
