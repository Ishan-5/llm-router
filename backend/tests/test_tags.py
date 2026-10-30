"""Spend tags: X-RouteWise-Team / X-RouteWise-Feature.

The point of these columns is that money can be grouped. So the tests pin the
normalisation (one team must not become three rows) and the fact that a tag can
never break a routing request.
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from router.db import ApiKey, RequestLog, SessionLocal
from router.main import app
from router.tags import TAG_MAX_LEN, clean_tag, request_tags

client = TestClient(app)


def _key(name):
    session = SessionLocal()
    key = ApiKey(key=f"rw_tag_{name}", name=name, is_active=True)
    session.add(key)
    session.commit()
    session.refresh(key)
    session.close()
    return key.key


def _logged_tags(key_string):
    """The (team_id, feature_tag) pairs logged for this key, oldest first."""
    session = SessionLocal()
    try:
        key = session.query(ApiKey).filter(ApiKey.key == key_string).one()
        rows = (
            session.query(RequestLog)
            .filter(RequestLog.api_key_id == key.id)
            .order_by(RequestLog.id)
            .all()
        )
        return [(row.team_id, row.feature_tag) for row in rows]
    finally:
        session.close()


def _fake_result(text="Paris"):
    return {
        "text": text, "tier": "cheap", "model_id": "test-model",
        "input_tokens": 5, "output_tokens": 3, "cost_usd": 0.0,
        "intended_tier": "cheap", "fallback_used": False, "latency_ms": 12.0,
    }


# --- normalisation -----------------------------------------------------------

def test_clean_tag_lowercases_and_replaces_runs_of_punctuation():
    assert clean_tag("  Growth Team! ") == "growth-team"
    assert clean_tag("Customer_Support/eu") == "customer-support-eu"


def test_clean_tag_collapses_every_separator_to_a_hyphen():
    assert clean_tag("support.eu_west-1") == "support.eu-west-1"


def test_clean_tag_rejects_empty_input():
    assert clean_tag(None) is None
    assert clean_tag("") is None
    assert clean_tag("   ") is None
    assert clean_tag("!!!") is None


def test_clean_tag_truncates_to_the_indexed_width():
    assert len(clean_tag("a" * 500)) == TAG_MAX_LEN


def test_request_tags_reads_both_headers():
    class FakeRequest:
        headers = {"x-routewise-team": "Growth", "x-routewise-feature": "Onboarding Copy"}

    assert request_tags(FakeRequest()) == {
        "team_id": "growth",
        "feature_tag": "onboarding-copy",
    }


# --- capture -----------------------------------------------------------------

def test_late_schema_upgrades_a_table_that_predates_the_columns(tmp_path, monkeypatch):
    """Production is an old table, not a fresh one.

    create_all() would never add team_id/feature_tag to a database that already
    has request_logs, so the ALTER path is what actually ships these columns.
    This test builds a deliberately old table and upgrades it, twice, so a
    failed second boot would also show up here.
    """
    from sqlalchemy import create_engine, inspect, text

    import router.db as db

    old = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with old.begin() as conn:
        conn.execute(text("CREATE TABLE request_logs (id INTEGER PRIMARY KEY, query VARCHAR)"))

    monkeypatch.setattr(db, "engine", old)
    db._apply_late_schema()
    db._apply_late_schema()  # every boot after the first

    columns = {column["name"] for column in inspect(old).get_columns("request_logs")}
    assert {"team_id", "feature_tag"} <= columns


def test_route_records_the_tags_it_was_given():
    key = _key("recorded")
    with patch("router.routes.route.check_cache", return_value=None), \
         patch("router.routes.route.get_tier", return_value=(1.5, "cheap", 3.4, 4.6)), \
         patch("router.routes.route.call_with_failover") as mock_call:
        mock_call.return_value = _fake_result()
        res = client.post(
            "/route",
            json={"query": "capital of france"},
            headers={
                "Authorization": f"Bearer {key}",
                "X-RouteWise-Team": "Growth",
                "X-RouteWise-Feature": "onboarding_copy",
            },
        )
        assert res.status_code == 200

    assert _logged_tags(key) == [("growth", "onboarding-copy")]


def test_route_without_tags_logs_nulls_not_empty_strings():
    key = _key("untagged")
    with patch("router.routes.route.check_cache", return_value=None), \
         patch("router.routes.route.get_tier", return_value=(1.5, "cheap", 3.4, 4.6)), \
         patch("router.routes.route.call_with_failover") as mock_call:
        mock_call.return_value = _fake_result()
        res = client.post(
            "/route", json={"query": "capital of france"},
            headers={"Authorization": f"Bearer {key}"},
        )
        assert res.status_code == 200

    assert _logged_tags(key) == [(None, None)]


def test_a_hostile_tag_cannot_fail_a_request():
    """Tags are caller input on a public endpoint, so they never reject."""
    key = _key("hostile")
    with patch("router.routes.route.check_cache", return_value=None), \
         patch("router.routes.route.get_tier", return_value=(1.5, "cheap", 3.4, 4.6)), \
         patch("router.routes.route.call_with_failover") as mock_call:
        mock_call.return_value = _fake_result()
        res = client.post(
            "/route", json={"query": "capital of france"},
            headers={
                "Authorization": f"Bearer {key}",
                "X-RouteWise-Team": "'; DROP TABLE request_logs; --",
                "X-RouteWise-Feature": "x" * 500,
            },
        )
        assert res.status_code == 200

    team, feature = _logged_tags(key)[0]
    assert team == "drop-table-request-logs"
    assert len(feature) == TAG_MAX_LEN


# --- reporting ---------------------------------------------------------------

def _seed(key_string, rows):
    """Insert log rows directly: these tests are about aggregation, not routing."""
    session = SessionLocal()
    try:
        key = session.query(ApiKey).filter(ApiKey.key == key_string).one()
        for row in rows:
            session.add(RequestLog(
                api_key_id=key.id, query="seeded", tier="cheap",
                model_id="test-model", latency_ms=10.0, **row,
            ))
        session.commit()
    finally:
        session.close()


def _analytics(key_string):
    res = client.get("/analytics", headers={"Authorization": f"Bearer {key_string}"})
    assert res.status_code == 200
    return res.json()


def test_analytics_groups_spend_by_team_most_expensive_first():
    key = _key("teams")
    _seed(key, [
        {"team_id": "growth", "input_tokens": 1_000_000, "output_tokens": 0, "cost_usd": 0.075},
        {"team_id": "growth", "input_tokens": 0, "output_tokens": 1_000_000, "cost_usd": 0.30},
        {"team_id": "support", "input_tokens": 100_000, "output_tokens": 0, "cost_usd": 0.0075},
        {"team_id": None, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0},
    ])

    teams = _analytics(key)["teams"]
    assert [team["team_id"] for team in teams] == ["growth", "support", None]

    growth = teams[0]
    assert growth["requests"] == 2
    assert growth["cost_usd"] == pytest.approx(0.375)
    assert growth["hypothetical_cost_usd"] == pytest.approx(1.37)
    assert growth["saved_usd"] == pytest.approx(0.995)
    assert growth["savings_pct"] == pytest.approx(72.6, abs=0.1)


def test_analytics_cache_hits_cannot_invent_team_savings():
    """A cache hit logs $0 and 0 tokens, so it adds nothing to either side."""
    key = _key("cache-team")
    _seed(key, [
        {"team_id": "growth", "input_tokens": 0, "output_tokens": 0,
         "cost_usd": 0.0, "cache_hit": True},
    ])

    team = _analytics(key)["teams"][0]
    assert team["team_id"] == "growth"
    assert team["cache_hits"] == 1
    assert team["saved_usd"] == 0.0
    assert team["savings_pct"] == 0.0


def test_analytics_with_no_requests_has_no_team_rows():
    key = _key("empty-teams")
    body = _analytics(key)
    assert body["teams"] == []
    assert body["team_count"] == 0


def test_logs_return_the_tags_so_the_dashboard_can_show_them():
    key = _key("logs-tags")
    _seed(key, [{
        "team_id": "growth", "feature_tag": "onboarding-copy",
        "input_tokens": 10, "output_tokens": 5, "cost_usd": 0.001,
    }])

    res = client.get("/logs", headers={"Authorization": f"Bearer {key}"})
    assert res.status_code == 200
    row = res.json()[0]
    assert (row["team_id"], row["feature_tag"]) == ("growth", "onboarding-copy")


def test_openai_compatible_endpoint_records_tags_too():
    key = _key("openai")
    with patch("router.openai_compat.check_cache", return_value=None), \
         patch("router.openai_compat.get_tier", return_value=(1.5, "cheap", 3.4, 4.6)), \
         patch("router.openai_compat.call_with_failover") as mock_call:
        mock_call.return_value = _fake_result()
        res = client.post(
            "/v1/chat/completions",
            json={"model": "routewise-auto", "messages": [{"role": "user", "content": "hi"}]},
            headers={
                "Authorization": f"Bearer {key}",
                "X-RouteWise-Team": "support",
                "X-RouteWise-Feature": "ticket-triage",
            },
        )
        assert res.status_code == 200

    assert _logged_tags(key) == [("support", "ticket-triage")]
