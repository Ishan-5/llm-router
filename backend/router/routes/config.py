import asyncio
import logging
import httpx
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel, field_validator
from router.db import SessionLocal, UserConfig, ModelPricing
from router.auth import require_user
from router.config import SUPPORTED_PROVIDERS, SUPABASE_URL, SUPABASE_SERVICE_KEY
from router.providers import validate_key
from router.providers_registry import PROVIDERS_REGISTRY
from router.model_config_loader import get_active_config

router = APIRouter()
log = logging.getLogger("routewise")
executor = ThreadPoolExecutor()


# Validation timeout for API key checks (in seconds)
KEY_VALIDATION_TIMEOUT = 5


class TierConfig(BaseModel):
    model_config = {"protected_namespaces": ()}

    provider: str
    model_id: str
    api_key: str

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v):
        if v not in SUPPORTED_PROVIDERS:
            raise ValueError(f"Unsupported provider '{v}'. Must be one of: {SUPPORTED_PROVIDERS}")
        return v

    @field_validator("model_id")
    @classmethod
    def validate_model_id(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("model_id cannot be empty")
        return v


class UserConfigRequest(BaseModel):
    cheap: TierConfig | None = None
    mid: TierConfig | None = None
    frontier: TierConfig | None = None


@router.get("/pricing")
def get_pricing():
    session = SessionLocal()
    try:
        rows = session.query(ModelPricing).filter(ModelPricing.is_active == True).order_by(ModelPricing.provider, ModelPricing.model_id).all()
        return [
            {
                "provider": r.provider, "model_id": r.model_id, "display_name": r.display_name,
                "price_per_m_input": r.price_per_m_input, "price_per_m_output": r.price_per_m_output,
                "notes": r.notes,
            }
            for r in rows
        ]
    finally:
        session.close()


@router.get("/providers")
def get_providers():
    return PROVIDERS_REGISTRY


@router.get("/config")
def get_config(authorization: str | None = Header(default=None)):
    user_id = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        try:
            resp = httpx.get(
                f"{SUPABASE_URL}/auth/v1/user",
                headers={"Authorization": f"Bearer {token}", "apikey": SUPABASE_SERVICE_KEY},
                timeout=5,
            )
            if resp.status_code == 200:
                user_id = resp.json()["id"]
        except Exception as e:
            log.debug("JWT verification failed for /config: %s", e)
    config = get_active_config(user_id)
    return {
        tier: {k: v for k, v in cfg.items() if k != "api_key"}
        for tier, cfg in config.items()
    }


@router.post("/config")
async def save_config(req: UserConfigRequest, user_id: str = Depends(require_user)):
    tiers = {"cheap": req.cheap, "mid": req.mid, "frontier": req.frontier}
    loop = asyncio.get_event_loop()
    results = {}
    session = SessionLocal()
    try:
        for tier, cfg in tiers.items():
            if cfg is None:
                continue
            try:
                await asyncio.wait_for(
                    loop.run_in_executor(executor, validate_key, cfg.provider, cfg.model_id, cfg.api_key),
                    timeout=KEY_VALIDATION_TIMEOUT,
                )
            except asyncio.TimeoutError:
                raise HTTPException(status_code=408, detail=f"Key validation timed out for {tier} tier")
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Key validation failed for {tier} tier: {e}")

            existing = session.query(UserConfig).filter(
                UserConfig.user_id == user_id, UserConfig.tier == tier
            ).first()
            if existing:
                existing.provider = cfg.provider
                existing.model_id = cfg.model_id
                existing.updated_at = datetime.utcnow()
            else:
                session.add(UserConfig(user_id=user_id, tier=tier, provider=cfg.provider, model_id=cfg.model_id))
            results[tier] = {"provider": cfg.provider, "model_id": cfg.model_id, "status": "saved"}
        session.commit()
    finally:
        session.close()
    return {"saved": results}


@router.delete("/config")
def reset_config(user_id: str = Depends(require_user)):
    session = SessionLocal()
    try:
        session.query(UserConfig).filter(UserConfig.user_id == user_id).delete()
        session.commit()
    finally:
        session.close()
    return {"reset": True}
