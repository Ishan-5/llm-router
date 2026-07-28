import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, field_validator
from router.db import SessionLocal, AlertRule
from router.auth import require_user
from datetime import datetime

router = APIRouter()
log = logging.getLogger("routewise")


def _validate_webhook_url(url: str):
    import ipaddress
    from urllib.parse import urlparse
    _PRIVATE_RANGES = [
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("169.254.0.0/16"),
        ipaddress.ip_network("::1/128"),
        ipaddress.ip_network("fc00::/7"),
    ]
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("Webhook URL must use https://")
    host = parsed.hostname
    if not host:
        raise ValueError("Invalid webhook URL")
    try:
        addr = ipaddress.ip_address(host)
        for net in _PRIVATE_RANGES:
            if addr in net:
                raise ValueError("Webhook URL must not point to a private/internal address")
    except ValueError as e:
        if "private" in str(e) or "internal" in str(e):
            raise
        if host.lower() in ("localhost", "metadata.google.internal"):
            raise ValueError("Webhook URL must not point to a private/internal address")


class AlertRuleRequest(BaseModel):
    alert_type: str
    threshold: float
    webhook_url: str

    @field_validator("alert_type")
    @classmethod
    def validate_alert_type(cls, v):
        if v not in ("daily_spend", "error_rate", "latency"):
            raise ValueError("alert_type must be daily_spend, error_rate, or latency")
        return v

    @field_validator("threshold")
    @classmethod
    def validate_threshold_positive(cls, v):
        if v <= 0:
            raise ValueError("threshold must be positive")
        return v

    @field_validator("webhook_url")
    @classmethod
    def validate_webhook(cls, v):
        _validate_webhook_url(v)
        return v


@router.get("/alerts")
def get_alerts(user_id: str = Depends(require_user)):
    session = SessionLocal()
    try:
        rows = session.query(AlertRule).filter(AlertRule.user_id == user_id, AlertRule.is_active == True).all()
        return [
            {
                "id": r.id, "alert_type": r.alert_type, "threshold": r.threshold,
                "webhook_url": r.webhook_url,
                "last_fired_at": r.last_fired_at.isoformat() if r.last_fired_at else None,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
    finally:
        session.close()


@router.post("/alerts")
def create_alert(req: AlertRuleRequest, user_id: str = Depends(require_user)):
    session = SessionLocal()
    try:
        rule = AlertRule(user_id=user_id, alert_type=req.alert_type, threshold=req.threshold, webhook_url=req.webhook_url)
        session.add(rule)
        session.commit()
        session.refresh(rule)
        return {"id": rule.id, "alert_type": rule.alert_type, "threshold": rule.threshold, "webhook_url": rule.webhook_url}
    finally:
        session.close()


@router.delete("/alerts/{alert_id}")
def delete_alert(alert_id: int, user_id: str = Depends(require_user)):
    session = SessionLocal()
    try:
        rule = session.query(AlertRule).filter(AlertRule.id == alert_id, AlertRule.user_id == user_id).first()
        if not rule:
            raise HTTPException(status_code=404, detail="Alert rule not found")
        rule.is_active = False
        session.commit()
        return {"deleted": alert_id}
    finally:
        session.close()
