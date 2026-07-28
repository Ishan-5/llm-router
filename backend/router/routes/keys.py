import secrets
import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from router.db import SessionLocal, ApiKey
from router.auth import require_user, invalidate_key_cache

router = APIRouter()
log = logging.getLogger("routewise")


class KeyCreateRequest(BaseModel):
    name: str


@router.get("/keys")
def get_keys(user_id: str = Depends(require_user)):
    session = SessionLocal()
    try:
        rows = session.query(ApiKey).filter(ApiKey.user_id == user_id, ApiKey.is_active == True).all()
        return [{"id": r.id, "key": r.key, "name": r.name, "created_at": r.created_at.isoformat()} for r in rows]
    finally:
        session.close()


@router.post("/keys")
def create_key(req: KeyCreateRequest, user_id: str = Depends(require_user)):
    key = "rw_" + secrets.token_urlsafe(32)
    session = SessionLocal()
    try:
        record = ApiKey(key=key, name=req.name.strip(), user_id=user_id)
        session.add(record)
        session.commit()
        return {"key": key, "name": record.name, "created_at": record.created_at.isoformat()}
    finally:
        session.close()


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
