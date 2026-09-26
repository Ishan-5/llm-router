"""Regression tests for the /stats aggregates shown on the public site.

Each of these pins a metric that was previously computed in the frontend with a
formula that disagreed with the backend or with the dollar figure beside it.
"""
from fastapi.testclient import TestClient
from router.main import app
from router.db import SessionLocal, ApiKey, RequestLog
from datetime import datetime, timedelta

client = TestClient(app)


def _make_key(name):
    session = SessionLocal()
    key = ApiKey(key=f"rw_stats_{name}", name=name, is_active=True)
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
    """Insert one request_logs row with sensible defaults for anything unset."""
    fields = {
        "api_key_id": key.id, "query": "q", "tier": "cheap", "model_id": "m",
        "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "latency_ms": 0.0,
        "cache_hit": False, "fallback_used": False, "tokens_saved_usd": 0.0,
        "quality_judged": False, "created_at": datetime.utcnow(),
    }
    fields.update(kw)
    session = SessionLocal()
    session.add(RequestLog(**fields))
    session.commit()
    session.close()


def _stats(key):
    res = client.get("/stats", headers={"Authorization": f"Bearer {key.key}"})
    assert res.status_code == 200
    return res.json()


def test_success_rate_ignores_successful_fallbacks():
    """A fallback is a successful answer from another tier, not a failure."""
    key = _make_key("success-fallback")
    _clear(key)
    for _ in range(9):
        _log(key, tier="cheap", latency_ms=100, cost_usd=0.001, input_tokens=100, output_tokens=100)
    _log(key, tier="frontier", latency_ms=100, cost_usd=0.001,
         input_tokens=100, output_tokens=100, fallback_used=True)

    s = _stats(key)
    assert s["fallback_count"] == 1
    assert s["failed_count"] == 0
    # 10/10 succeeded. The old frontend formula (total - fallbacks)/total
    # reported 90% here, scoring a successful fallback as a failure.
    assert s["success_rate_pct"] == 100.0
    old_buggy = round((s["total_requests"] - s["fallback_count"]) / s["total_requests"] * 100, 1)
    assert old_buggy == 90.0
    assert s["success_rate_pct"] != old_buggy


def test_success_rate_counts_only_hard_failures():
    key = _make_key("success-failed")
    _clear(key)
    for _ in range(8):
        _log(key, tier="cheap", latency_ms=100, cost_usd=0.001, input_tokens=100, output_tokens=100)
    for _ in range(2):
        _log(key, tier="failed", latency_ms=50, cost_usd=0.0)

    s = _stats(key)
    assert s["failed_count"] == 2
    assert s["success_rate_pct"] == 80.0


def test_avg_latency_is_weighted_by_request_count():
    """100 fast requests + 1 slow one must not average to the midpoint."""
    key = _make_key("latency-weighting")
    _clear(key)
    for _ in range(100):
        _log(key, tier="cheap", latency_ms=100)
    _log(key, tier="frontier", latency_ms=5000)

    s = _stats(key)
    # request-weighted: (100*100 + 1*5000)/101 = 148.5
    assert s["avg_latency_ms"] == 148.5
    # the unweighted mean of the two tier means was 2550
    tier_means = list(s["avg_latency_by_tier"].values())
    unweighted = sum(tier_means) / len(tier_means)
    assert unweighted == 2550.0
    assert s["avg_latency_ms"] != unweighted


def test_savings_pct_agrees_with_total_savings_dollars():
    """savings_pct must be the percentage form of total_savings_usd."""
    key = _make_key("savings-consistency")
    _clear(key)
    _log(key, tier="frontier", latency_ms=100, cost_usd=1.0,
         input_tokens=1_000_000, output_tokens=0)          # hypothetical $0.15
    _log(key, tier="cheap", cache_hit=True, latency_ms=5, cost_usd=0.0,
         input_tokens=0, output_tokens=0, tokens_saved_usd=0.85)

    s = _stats(key)
    baseline = s["total_hypothetical_cost"] + s["cache_savings_usd"]
    expected_pct = round((1 - s["total_actual_cost"] / baseline) * 100, 1)
    assert s["savings_pct"] == expected_pct
    # the dollar figure is the same quantity, so the two must not contradict
    assert s["total_savings_usd"] == round(s["cache_savings_usd"] + s["routing_savings_usd"], 6)
    # the old percentage form ignored cache savings, so it understated the headline
    old_buggy = round((1 - s["total_actual_cost"] / s["total_hypothetical_cost"]) * 100, 1)
    assert s["savings_pct"] != old_buggy


def test_savings_pct_includes_cache_savings():
    """Cache savings count toward the headline percentage, not just the dollars."""
    key = _make_key("savings-includes-cache")
    _clear(key)
    _log(key, tier="frontier", latency_ms=100, cost_usd=0.0,
         input_tokens=1_000_000, output_tokens=0)   # hypothetical $0.15, paid $0
    _log(key, tier="cheap", cache_hit=True, latency_ms=5, cost_usd=0.0,
         input_tokens=0, output_tokens=0, tokens_saved_usd=0.15)

    s = _stats(key)
    # baseline = 0.15 hypothetical + 0.15 cache = 0.30, actual 0.0 -> 100%
    assert s["savings_pct"] == 100.0
    assert s["total_savings_usd"] == 0.3


def test_savings_pct_is_zero_when_no_traffic():
    key = _make_key("savings-empty")
    _clear(key)
    s = _stats(key)
    assert s["total_requests"] == 0
    assert s["savings_pct"] == 0.0
    assert s["success_rate_pct"] == 100.0
