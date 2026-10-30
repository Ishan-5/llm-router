"""Budget resolution: what a request is allowed to spend, and why it was capped.

A cap lives on the key (daily or monthly) or on the team the key belongs to
(monthly). All three are checked on every request, because a team budget that
only applies to some keys is not a budget.

Exhausting a cap does NOT reject the request. It downgrades routing to the
cheap tier -- the same behaviour the daily cap already had -- and the response,
the log row and the dashboard all say which cap did it. A caller who is told
"cheap because the team budget is gone" can act; a caller who only sees a
cheaper model cannot.
"""
import logging
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime

from sqlalchemy import func

from router.db import ApiKey, RequestLog, SessionLocal, Team

log = logging.getLogger("routewise.budgets")

# Team rows change rarely but are read on every request. Same TTL as the API
# key cache, and invalidated explicitly whenever a team is edited.
_TEAM_CACHE_TTL = 30
_team_cache: dict[int, tuple["TeamInfo | None", float]] = {}

WARNING_PERCENT = 80.0


@dataclass(frozen=True)
class TeamInfo:
    """A team's budget-relevant fields, detached from the session on purpose.

    Caching the ORM object would keep a reference to a closed session; this is
    just the three values a budget check needs.
    """

    id: int
    name: str
    monthly_budget_usd: float | None


def invalidate_team_cache(team_id: int | None = None) -> None:
    if team_id is None:
        _team_cache.clear()
    else:
        _team_cache.pop(team_id, None)


def month_start(now: datetime | None = None) -> datetime:
    n = now or datetime.utcnow()
    return datetime(n.year, n.month, 1)


def day_start(now: datetime | None = None) -> datetime:
    n = now or datetime.utcnow()
    return datetime.combine(n.date() if isinstance(n, datetime) else date.today(), datetime.min.time())


def get_team(session, team_id: int | None) -> TeamInfo | None:
    """Load an active team's budget fields, with a short cache. Misses cached too."""
    if team_id is None:
        return None
    now = time.time()
    if team_id in _team_cache:
        team, ts = _team_cache[team_id]
        if now - ts < _TEAM_CACHE_TTL:
            return team
    row = (
        session.query(Team)
        .filter(Team.id == team_id, Team.is_active == True)
        .first()
    )
    team = (
        TeamInfo(id=row.id, name=row.name, monthly_budget_usd=row.monthly_budget_usd)
        if row
        else None
    )
    _team_cache[team_id] = (team, now)
    return team


def team_for_key(api_key: ApiKey) -> TeamInfo | None:
    session = SessionLocal()
    try:
        return get_team(session, getattr(api_key, "team_id", None))
    finally:
        session.close()


def _spend(session, key_id: int, since: datetime) -> float:
    return float(
        session.query(func.sum(RequestLog.cost_usd))
        .filter(RequestLog.api_key_id == key_id, RequestLog.created_at >= since)
        .scalar()
        or 0.0
    )


def key_spend(session, key_id: int, since: datetime) -> float:
    """Spend by one key since a timestamp. Single round trip."""
    return _spend(session, key_id, since)


def team_spend(session, team_id: int, since: datetime) -> float:
    """Spend by every key in a team since a timestamp."""
    return float(
        session.query(func.sum(RequestLog.cost_usd))
        .join(ApiKey, RequestLog.api_key_id == ApiKey.id)
        .filter(ApiKey.team_id == team_id, RequestLog.created_at >= since)
        .scalar()
        or 0.0
    )


@dataclass(frozen=True)
class BudgetStatus:
    """The binding cap for one key, plus whether it stopped the request.

    scope is the cap that decides the answer: the tightest one, or the one that
    ran out. It is None only when no cap is configured anywhere.
    """

    allowed: bool
    capped: bool
    scope: str | None
    period: str | None
    budget_usd: float | None
    spent_usd: float
    remaining_usd: float | None
    percent_used: float | None
    state: str
    team_id: int | None = None
    team_name: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


UNLIMITED = BudgetStatus(
    allowed=True,
    capped=False,
    scope=None,
    period=None,
    budget_usd=None,
    spent_usd=0.0,
    remaining_usd=None,
    percent_used=None,
    state="unlimited",
)


def _ratio(spent: float, budget: float) -> float:
    if budget <= 0:
        return 100.0
    return spent / budget * 100.0


def budget_status(api_key: ApiKey, session=None) -> BudgetStatus:
    """Resolve every cap that applies to this key and pick the binding one.

    Order matters only for breaking ties: daily key cap, then monthly key cap,
    then the team's monthly cap, because that is the order in which a caller
    would want to hear about them.
    """
    own_session = session is None
    if own_session:
        session = SessionLocal()
    try:
        team = get_team(session, getattr(api_key, "team_id", None))
        daily = getattr(api_key, "daily_budget_usd", None)
        monthly = getattr(api_key, "monthly_budget_usd", None)
        team_monthly = team.monthly_budget_usd if team else None

        if daily is None and monthly is None and team_monthly is None:
            return BudgetStatus(
                allowed=True,
                capped=False,
                scope=None,
                period=None,
                budget_usd=None,
                spent_usd=0.0,
                remaining_usd=None,
                percent_used=None,
                state="unlimited",
                team_id=team.id if team else None,
                team_name=team.name if team else None,
            )

        needs_day = daily is not None
        spent_day = _spend(session, api_key.id, day_start()) if needs_day else 0.0
        spent_key_month = _spend(session, api_key.id, month_start()) if monthly is not None else 0.0
        spent_team_month = (
            team_spend(session, team.id, month_start()) if team_monthly is not None else 0.0
        )

        candidates = []
        if daily is not None:
            candidates.append(("key_daily", "day", float(daily), spent_day, team))
        if monthly is not None:
            candidates.append(("key_monthly", "month", float(monthly), spent_key_month, team))
        if team_monthly is not None:
            candidates.append(("team_monthly", "month", float(team_monthly), spent_team_month, team))

        tripped = next((c for c in candidates if c[3] >= c[2]), None)
        if tripped:
            chosen = tripped
        else:
            # Nothing tripped: report the cap closest to its limit, which is the
            # one the owner should be warned about.
            chosen = max(candidates, key=lambda c: _ratio(c[3], c[2]))

        scope, period, budget_usd, spent_usd, team = chosen
        percent = round(_ratio(spent_usd, budget_usd), 1)
        capped = tripped is not None
        if capped:
            state = "exhausted"
        elif percent >= WARNING_PERCENT:
            state = "warning"
        else:
            state = "ok"

        return BudgetStatus(
            allowed=not capped,
            capped=capped,
            scope=scope,
            period=period,
            budget_usd=round(budget_usd, 6),
            spent_usd=round(spent_usd, 6),
            remaining_usd=round(max(0.0, budget_usd - spent_usd), 6),
            percent_used=percent,
            state=state,
            team_id=team.id if team else None,
            team_name=team.name if team else None,
        )
    finally:
        if own_session:
            session.close()


SCOPE_LABELS = {
    "key_daily": "This key's daily budget",
    "key_monthly": "This key's monthly budget",
    "team_monthly": "Team monthly budget",
}
