"""Teams and monthly budgets: who is allowed to spend what, and why a request
was downgraded.

A cap that only exists in the database is not a cap, so these tests drive the
whole path: create a team, put keys under it, push spend past the limit, and
check that routing falls back to cheap *and* says which budget caused it.
"""
from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from router.auth import invalidate_key_cache, require_user
from router.budgets import invalidate_team_cache
from router.db import ApiKey, RequestLog, SessionLocal, Team
from router.main import app

client = TestClient(app)

USER_ID = "finops-user-1"
OTHER_USER_ID = "finops-user-2"

_counter = {"n": 0}


def _unique(prefix):
    _counter["n"] += 1
    return f"{prefix}-{_counter['n']}"


@pytest.fixture(autouse=True)
def _fresh_caches():
    app.dependency_overrides[require_user] = lambda: USER_ID
    invalidate_key_cache()
    invalidate_team_cache()
    yield
    app.dependency_overrides.clear()
    invalidate_key_cache()
    invalidate_team_cache()


def _make_team(name=None, budget=None, user_id=USER_ID):
    name = name or _unique("team")
    session = SessionLocal()
    team = Team(user_id=user_id, name=name, monthly_budget_usd=budget, is_active=True)
    session.add(team)
    session.commit()
    session.refresh(team)
    team_id = team.id
    session.close()
    return team_id, name


def _make_key(name=None, **kwargs):
    name = name or _unique("key")
    kwargs.setdefault("user_id", USER_ID)
    session = SessionLocal()
    key = ApiKey(key=f"rw_finops_{name}", name=name, is_active=True, **kwargs)
    session.add(key)
    session.commit()
    session.refresh(key)
    key_id, key_string = key.id, key.key
    session.close()
    return key_id, key_string


def _seed_spend(key_id, cost, days_ago=0):
    session = SessionLocal()
    session.add(RequestLog(
        api_key_id=key_id,
        query="seed",
        response="seed",
        difficulty_score=1.0,
        intended_tier="cheap",
        tier="cheap",
        fallback_used=False,
        cache_hit=False,
        model_id="test-model",
        input_tokens=0,
        output_tokens=0,
        cost_usd=cost,
        latency_ms=1.0,
        created_at=datetime.utcnow(),
    ))
    session.commit()
    session.close()


def _fake_result(tier="cheap"):
    return {
        "text": "Paris", "tier": tier, "model_id": "test-model",
        "input_tokens": 5, "output_tokens": 3, "cost_usd": 0.001,
        "intended_tier": tier, "fallback_used": False, "latency_ms": 12.0,
    }


def _route(key_string, query="capital of france", headers=None):
    with patch("router.routes.route.check_cache", return_value=None), \
         patch("router.routes.route.get_tier", return_value=(5.0, "frontier", 3.4, 4.6)), \
         patch("router.routes.route.call_with_failover", return_value=_fake_result()) as call:
        res = client.post(
            "/route",
            json={"query": query},
            headers={"Authorization": f"Bearer {key_string}", **(headers or {})},
        )
    return res, call


# --- teams -------------------------------------------------------------------

def test_create_team_and_list_it():
    response = client.post("/teams", json={"name": "growth", "monthly_budget_usd": 20})
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "growth"
    assert body["monthly_budget_usd"] == 20
    assert body["spent_this_month"] == 0
    assert body["remaining_usd"] == 20
    assert body["state"] == "ok"
    assert body["key_count"] == 0

    listed = client.get("/teams").json()
    assert any(team["id"] == body["id"] for team in listed)


def test_duplicate_team_name_is_rejected():
    client.post("/teams", json={"name": "collision"})
    response = client.post("/teams", json={"name": "Collision"})
    assert response.status_code == 409


def test_team_budget_update_and_warning_state():
    team_id, _ = _make_team(budget=10)
    key_id, _ = _make_key(team_id=team_id)
    _seed_spend(key_id, 8.5)

    response = client.patch(f"/teams/{team_id}", json={"monthly_budget_usd": 12})
    assert response.status_code == 200
    body = response.json()
    assert body["monthly_budget_usd"] == 12
    assert body["spent_this_month"] == 8.5
    assert body["percent_used"] == 70.8
    assert body["state"] == "ok"

    # Lower the cap below spend: the same team is now exhausted, not just warned.
    body = client.patch(f"/teams/{team_id}", json={"monthly_budget_usd": 8}).json()
    assert body["state"] == "exhausted"
    assert body["remaining_usd"] == 0


def test_team_requires_a_non_empty_name():
    assert client.post("/teams", json={"name": "   "}).status_code == 400


def test_delete_team_detaches_keys_but_keeps_them_working():
    team_id, _ = _make_team(budget=1)
    key_id, key_string = _make_key(team_id=team_id)

    response = client.delete(f"/teams/{team_id}")
    assert response.status_code == 200
    assert response.json()["detached_keys"] == 1

    session = SessionLocal()
    try:
        assert session.query(ApiKey).filter(ApiKey.id == key_id).one().team_id is None
    finally:
        session.close()

    # The key itself still routes; it just has no team budget any more.
    res, _ = _route(key_string)
    assert res.status_code == 200
    assert res.json()["budget"]["state"] == "unlimited"


# --- keys belong to teams ----------------------------------------------------

def test_key_reports_its_team_and_month_spend():
    team_id, team_name = _make_team(budget=10)
    key_id, key_string = _make_key(team_id=team_id, monthly_budget_usd=2)
    _seed_spend(key_id, 1.25)

    row = next(r for r in client.get("/keys").json() if r["id"] == key_id)
    assert row["team_id"] == team_id
    assert row["team_name"] == team_name
    assert row["monthly_budget_usd"] == 2
    assert row["spent_this_month"] == 1.25
    assert row["budget"]["scope"] == "key_monthly"
    assert row["budget"]["allowed"] is True


def test_cannot_attach_a_key_to_someone_elses_team():
    other_team_id, _ = _make_team(user_id=OTHER_USER_ID)
    response = client.post("/keys", json={"name": "stolen", "team_id": other_team_id})
    assert response.status_code == 404


# --- enforcement -------------------------------------------------------------

def test_team_budget_exhausted_downgrades_to_cheap():
    team_id, _ = _make_team(budget=1)
    key_id, key_string = _make_key(team_id=team_id)
    _seed_spend(key_id, 2.0)

    res, call = _route(key_string)
    assert res.status_code == 200
    body = res.json()
    assert body["routed_to"] == "cheap"
    assert body["budget_capped"] is True
    assert body["budget"]["scope"] == "team_monthly"
    assert body["budget"]["state"] == "exhausted"
    assert "$2.00 of $1.00" in body["route_reason"]
    assert "team monthly budget" in body["route_reason"].lower()
    # The provider call really was made against the cheap tier.
    assert call.call_args.args[0] == "cheap"


def test_one_shared_team_budget_covers_every_key_in_it():
    team_id, _ = _make_team(budget=1)
    alice_id, alice_key = _make_key(team_id=team_id, name="alice")
    bob_id, bob_key = _make_key(team_id=team_id, name="bob")
    _seed_spend(alice_id, 0.4)
    _seed_spend(bob_id, 0.7)

    # Bob alone is under any per-key cap, but the team is over.
    res, call = _route(bob_key)
    assert res.json()["budget_capped"] is True
    assert res.json()["budget"]["scope"] == "team_monthly"
    assert call.call_args.args[0] == "cheap"


def test_key_monthly_budget_reports_its_own_scope():
    key_id, key_string = _make_key(monthly_budget_usd=1)
    _seed_spend(key_id, 1.5)

    res, _ = _route(key_string)
    body = res.json()
    assert body["budget_capped"] is True
    assert body["budget"]["scope"] == "key_monthly"


def test_daily_budget_reports_its_own_scope():
    key_id, key_string = _make_key(daily_budget_usd=0.5)
    _seed_spend(key_id, 0.75)

    res, _ = _route(key_string)
    body = res.json()
    assert body["budget_capped"] is True
    assert body["budget"]["scope"] == "key_daily"
    assert body["budget"]["period"] == "day"


def test_zero_team_budget_blocks_spending_immediately():
    team_id, _ = _make_team(budget=0)
    _, key_string = _make_key(team_id=team_id)

    body = _route(key_string)[0].json()
    assert body["budget_capped"] is True
    assert body["budget"]["scope"] == "team_monthly"
    assert body["budget"]["remaining_usd"] == 0


def test_unlimited_key_reports_no_budget():
    _, key_string = _make_key()
    body = _route(key_string)[0].json()
    assert body["budget_capped"] is False
    assert body["budget"]["state"] == "unlimited"
    assert body["budget"]["budget_usd"] is None


# --- tags follow the team ----------------------------------------------------

def test_team_tag_is_inherited_without_a_header():
    team_id, team_name = _make_team()
    _, key_string = _make_key(team_id=team_id)

    res, _ = _route(key_string)
    assert res.status_code == 200

    session = SessionLocal()
    try:
        key = session.query(ApiKey).filter(ApiKey.key == key_string).one()
        row = (
            session.query(RequestLog)
            .filter(RequestLog.api_key_id == key.id, RequestLog.query == "capital of france")
            .one()
        )
        assert row.team_id == team_name.replace("_", "-").lower()
    finally:
        session.close()


def test_an_explicit_header_still_wins_over_the_team_default():
    team_id, team_name = _make_team()
    _, key_string = _make_key(team_id=team_id)

    _route(key_string, headers={"X-RouteWise-Team": "marketing"})

    session = SessionLocal()
    try:
        key = session.query(ApiKey).filter(ApiKey.key == key_string).one()
        row = (
            session.query(RequestLog)
            .filter(RequestLog.api_key_id == key.id, RequestLog.query == "capital of france")
            .one()
        )
        assert row.team_id == "marketing"
        assert row.team_id != team_name
    finally:
        session.close()


# --- visibility --------------------------------------------------------------

def test_analytics_reports_budget_and_how_many_requests_were_downgraded():
    team_id, _ = _make_team(budget=1)
    key_id, key_string = _make_key(team_id=team_id)
    _seed_spend(key_id, 2.0)

    _route(key_string, query="first")
    _route(key_string, query="second")

    body = client.get("/analytics", headers={"Authorization": f"Bearer {key_string}"}).json()
    assert body["budget"]["state"] == "exhausted"
    assert body["budget"]["scope"] == "team_monthly"
    assert body["budget_downgrades_this_month"] == 2


def test_analytics_reports_a_warning_before_the_budget_runs_out():
    team_id, _ = _make_team(budget=10)
    key_id, key_string = _make_key(team_id=team_id)
    _seed_spend(key_id, 8.5)

    body = client.get("/analytics", headers={"Authorization": f"Bearer {key_string}"}).json()
    assert body["budget"]["state"] == "warning"
    assert body["budget"]["allowed"] is True
    assert body["budget"]["percent_used"] == 85.0


def test_logs_carry_the_budget_scope_that_caused_the_downgrade():
    team_id, _ = _make_team(budget=1)
    key_id, key_string = _make_key(team_id=team_id)
    _seed_spend(key_id, 2.0)

    _route(key_string, query="why cheap")

    logs = client.get("/logs", headers={"Authorization": f"Bearer {key_string}"}).json()
    capped = [row for row in logs if row["query"] == "why cheap"]
    assert len(capped) == 1
    assert capped[0]["budget_capped"] is True
    assert capped[0]["budget_scope"] == "team_monthly"
