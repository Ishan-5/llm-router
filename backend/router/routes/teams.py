"""Teams are the budget bucket a key belongs to.

One monthly cap on the team covers every key under it, so a customer can hand
out one shared key or one key per member and still have a single number the
finance owner recognises. A team also gives its keys a default spend tag, so
requests show up under the team without anyone sending a header.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import func

from router.auth import require_user
from router.budgets import invalidate_team_cache, month_start, team_spend
from router.db import ApiKey, SessionLocal, Team

router = APIRouter()
log = logging.getLogger("routewise.teams")

TEAM_NAME_MAX = 80


def _validate_budget(v):
    if v is None:
        return None
    if v < 0:
        raise ValueError("monthly_budget_usd must be zero or greater")
    if v != v or v in (float("inf"), float("-inf")):
        raise ValueError("monthly_budget_usd must be a finite number")
    return v


class TeamCreateRequest(BaseModel):
    name: str
    monthly_budget_usd: float | None = None

    @field_validator("monthly_budget_usd")
    @classmethod
    def check_budget(cls, v):
        return _validate_budget(v)


class TeamUpdateRequest(BaseModel):
    name: str | None = None
    monthly_budget_usd: float | None = None

    @field_validator("monthly_budget_usd")
    @classmethod
    def check_budget(cls, v):
        return _validate_budget(v)


def _clean_name(name: str | None) -> str:
    cleaned = (name or "").strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="name cannot be empty")
    if len(cleaned) > TEAM_NAME_MAX:
        raise HTTPException(
            status_code=400, detail=f"name must be {TEAM_NAME_MAX} characters or fewer"
        )
    return cleaned


def _serialize(session, team: Team) -> dict:
    spent = team_spend(session, team.id, month_start())
    budget = team.monthly_budget_usd
    key_count = (
        session.query(func.count(ApiKey.id))
        .filter(ApiKey.team_id == team.id, ApiKey.is_active == True)
        .scalar()
        or 0
    )

    if budget is None:
        percent = None
        state = "unlimited"
    else:
        percent = round(spent / budget * 100, 1) if budget > 0 else 100.0
        if spent >= budget:
            state = "exhausted"
        elif percent >= 80:
            state = "warning"
        else:
            state = "ok"

    return {
        "id": team.id,
        "name": team.name,
        "monthly_budget_usd": budget,
        "spent_this_month": round(spent, 6),
        "remaining_usd": round(max(0.0, budget - spent), 6) if budget is not None else None,
        "percent_used": percent,
        "state": state,
        "key_count": int(key_count),
        "created_at": team.created_at.isoformat() if team.created_at else None,
    }


@router.get("/teams")
def list_teams(user_id: str = Depends(require_user)):
    session = SessionLocal()
    try:
        rows = (
            session.query(Team)
            .filter(Team.user_id == user_id, Team.is_active == True)
            .order_by(Team.created_at.asc())
            .all()
        )
        return [_serialize(session, team) for team in rows]
    finally:
        session.close()


@router.post("/teams")
def create_team(req: TeamCreateRequest, user_id: str = Depends(require_user)):
    name = _clean_name(req.name)
    session = SessionLocal()
    try:
        exists = session.query(Team).filter(
            Team.user_id == user_id, Team.is_active == True, func.lower(Team.name) == name.lower()
        ).first()
        if exists:
            raise HTTPException(status_code=409, detail="A team with that name already exists")
        team = Team(user_id=user_id, name=name, monthly_budget_usd=req.monthly_budget_usd)
        session.add(team)
        session.commit()
        session.refresh(team)
        return _serialize(session, team)
    finally:
        session.close()


@router.patch("/teams/{team_id}")
def update_team(team_id: int, req: TeamUpdateRequest, user_id: str = Depends(require_user)):
    session = SessionLocal()
    try:
        team = session.query(Team).filter(
            Team.id == team_id, Team.user_id == user_id, Team.is_active == True
        ).first()
        if not team:
            raise HTTPException(status_code=404, detail="Team not found")

        fields = req.model_dump(exclude_unset=True)
        if "name" in fields:
            name = _clean_name(fields["name"])
            clash = session.query(Team).filter(
                Team.user_id == user_id,
                Team.is_active == True,
                Team.id != team.id,
                func.lower(Team.name) == name.lower(),
            ).first()
            if clash:
                raise HTTPException(status_code=409, detail="A team with that name already exists")
            team.name = name
        if "monthly_budget_usd" in fields:
            team.monthly_budget_usd = fields["monthly_budget_usd"]

        session.commit()
        session.refresh(team)
        payload = _serialize(session, team)
    finally:
        session.close()
    invalidate_team_cache(team_id)
    return payload


@router.delete("/teams/{team_id}")
def delete_team(team_id: int, user_id: str = Depends(require_user)):
    """Retire a team without breaking its keys.

    Keys are detached instead of deleted: they may be baked into a member's
    config or CI secret, and silently invalidating them would look like an
    outage. Without a team they simply have no shared budget.
    """
    session = SessionLocal()
    try:
        team = session.query(Team).filter(
            Team.id == team_id, Team.user_id == user_id, Team.is_active == True
        ).first()
        if not team:
            raise HTTPException(status_code=404, detail="Team not found")
        detached = session.query(ApiKey).filter(ApiKey.team_id == team.id).update(
            {ApiKey.team_id: None}
        )
        team.is_active = False
        session.commit()
    finally:
        session.close()
    # Budgets and default tags are cached per key; a detach changes both.
    from router.auth import invalidate_key_cache

    invalidate_key_cache()
    invalidate_team_cache(team_id)
    return {"deleted": team_id, "detached_keys": int(detached)}
