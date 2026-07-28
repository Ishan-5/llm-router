import logging
from datetime import datetime
from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator
from router.db import SessionLocal, UserSettings
from router.auth import require_user

router = APIRouter()
log = logging.getLogger("routewise")

DEFAULT_THRESHOLD = 1.0


@router.get("/settings")
def get_settings(user_id: str = Depends(require_user)):
    session = SessionLocal()
    try:
        settings = session.query(UserSettings).filter(UserSettings.user_id == user_id).first()
        if settings is None:
            return {"router_threshold": DEFAULT_THRESHOLD}
        return {"router_threshold": settings.router_threshold}
    finally:
        session.close()


class SettingsRequest(BaseModel):
    router_threshold: float

    @field_validator("router_threshold")
    @classmethod
    def validate_threshold(cls, v):
        if v < 0.0 or v > 2.0:
            raise ValueError("router_threshold must be between 0.0 and 2.0")
        return v


@router.post("/settings")
def save_settings(req: SettingsRequest, user_id: str = Depends(require_user)):
    session = SessionLocal()
    try:
        settings = session.query(UserSettings).filter(UserSettings.user_id == user_id).first()
        if settings:
            settings.router_threshold = req.router_threshold
            settings.updated_at = datetime.utcnow()
        else:
            session.add(UserSettings(user_id=user_id, router_threshold=req.router_threshold))
        session.commit()
        return {"router_threshold": req.router_threshold}
    finally:
        session.close()
