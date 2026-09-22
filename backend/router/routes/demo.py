"""
Admin-only controls: "simulate outage" mode for live presentations.

Trips the in-memory circuit breakers for a set of tiers so the real failover
machinery (tier chain -> Gemini last resort) runs in front of an audience
without waiting for an actual provider failure. Fully reversible and reset
on restart. Disabling/starting an outage requires admin access; the status
endpoint stays public so frontends can show the outage visually.
"""
import logging
from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator
from router.auth import require_admin_any
from router.circuit_breaker import set_chaos, get_chaos

router = APIRouter()
log = logging.getLogger("routewise.demo")

VALID_CHAOS_TIERS = ("cheap", "mid", "frontier", "gemini")


class ChaosRequest(BaseModel):
    active: bool
    tiers: list[str] | None = None

    @field_validator("tiers")
    @classmethod
    def validate_tiers(cls, v):
        if v is None:
            return v
        bad = [t for t in v if t not in VALID_CHAOS_TIERS]
        if bad:
            raise ValueError(f"unknown chaos tiers: {bad}")
        return v


@router.get("/demo/chaos")
def chaos_status():
    return get_chaos()


@router.post("/demo/chaos")
def chaos_control(req: ChaosRequest, _admin: str = Depends(require_admin_any)):
    set_chaos(req.active, req.tiers)
    return get_chaos()