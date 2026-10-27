"""Tests for GET /stats/reliability, the difficulty-classifier calibration report.

The point of the endpoint is that routing turns a score into a price, so the
numbers here are pinned: a bin must report the mean predicted score and the
mean labelled score for the same requests, and unlabelled rows must not move
the calibration figures.
"""
from datetime import datetime

from fastapi.testclient import TestClient

from router.db import ApiKey, RequestLog, SessionLocal
from router.main import app

client = TestClient(app)


def _make_key(name):
    session = SessionLocal()
    key = ApiKey(key=f"rw_rel_{name}", name=name, is_active=True)
    session.add(key)
    session.commit()
    session.refresh(key)
    session.close()
    return key


def _clear(key):
    session = SessionLocal()
    session.query(RequestLog).filter(RequestLog.api_key_id == key.id).delete()
    session.commit()
    session.close()


def _log(key, **kw):
    fields = {
        "api_key_id": key.id, "query": "q", "tier": "cheap", "model_id": "m",
        "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "latency_ms": 0.0,
        "cache_hit": False, "fallback_used": False, "created_at": datetime.utcnow(),
    }
    fields.update(kw)
    session = SessionLocal()
    session.add(RequestLog(**fields))
    session.commit()
    session.close()


def _get(key):
    res = client.get(
        "/stats/reliability", headers={"Authorization": f"Bearer {key.key}"}
    )
    assert res.status_code == 200
    return res.json()


def test_empty_history_explains_itself():
    key = _make_key("empty")
    _clear(key)

    data = _get(key)

    assert data["sample"]["total"] == 0
    assert "message" in data


def test_calibration_error_uses_labelled_rows_only():
    key = _make_key("calib")
    _clear(key)
    # Four requests the classifier called 2/10 while the labeler said 4/10.
    for _ in range(4):
        _log(key, difficulty_score=2.0, llm_difficulty_score=4.0, tier="cheap",
             cost_usd=0.0001, latency_ms=100)
    # Unlabelled traffic must not move MAE/ECE in either direction.
    _log(key, difficulty_score=9.5, llm_difficulty_score=None, tier="frontier")

    data = _get(key)

    assert data["sample"]["total"] == 5
    assert data["sample"]["labeled"] == 4
    assert data["mae"] == 2.0
    assert data["ece"] == 2.0
    bin_row = next(r for r in data["reliability"] if r["n"] == 4)
    assert bin_row["predicted"] == 2.0
    assert bin_row["actual"] == 4.0


def test_thresholds_match_the_balanced_default():
    key = _make_key("thresholds")
    _clear(key)
    _log(key, difficulty_score=5.0, tier="mid")

    data = _get(key)

    assert data["thresholds"] == {"cheap_ceil": 4.5, "frontier_floor": 6.0}


def test_borderline_share_flags_scores_next_to_a_threshold():
    key = _make_key("borderline")
    _clear(key)
    for _ in range(3):
        _log(key, difficulty_score=4.4, tier="cheap")  # 0.1 below cheap_ceil
    _log(key, difficulty_score=8.0, tier="frontier")   # far from both boundaries

    data = _get(key)

    assert data["borderline_share"] == 0.75


def test_tier_rows_carry_cost_quality_and_feedback():
    key = _make_key("tiers")
    _clear(key)
    _log(key, difficulty_score=2.0, tier="cheap", cost_usd=0.0002, latency_ms=200,
         quality_score=8.0, quality_judged=True, feedback="up")
    _log(key, difficulty_score=2.5, tier="cheap", cost_usd=0.0004, latency_ms=400,
         quality_score=6.0, quality_judged=True, feedback="down")

    row = _get(key)["tiers"][0]

    assert row["tier"] == "cheap"
    assert row["requests"] == 2
    assert row["avg_cost"] == 0.0003
    assert row["avg_latency_ms"] == 300
    assert row["avg_quality"] == 7.0
    assert (row["feedback_up"], row["feedback_down"]) == (1, 1)


def test_confusion_counts_intended_against_served_tier():
    key = _make_key("confusion")
    _clear(key)
    _log(key, difficulty_score=9.0, intended_tier="frontier", tier="mid", fallback_used=True)

    data = _get(key)

    assert data["confusion"] == [{"intended": "frontier", "served": "mid", "requests": 1}]
    assert data["tiers"][0]["fallback_rate"] == 1.0


def test_cache_hits_and_web_tier_are_excluded():
    key = _make_key("excluded")
    _clear(key)
    _log(key, difficulty_score=2.0, tier="cheap")
    _log(key, difficulty_score=2.0, tier="cheap", cache_hit=True)
    _log(key, difficulty_score=None, tier="web", intended_tier="web")

    data = _get(key)

    assert data["sample"]["total"] == 1
