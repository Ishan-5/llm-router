"""Observability surface: health probes and the Prometheus exposition.

These lock in the contract other tooling depends on — the probes a container
orchestrator calls, and the series a Prometheus scrape reads.
"""
from fastapi.testclient import TestClient

from router.main import app

client = TestClient(app)


def _counter_value(name: str, label_fragment: str) -> float:
    """Read one sample of a counter from the Prometheus exposition."""
    text = client.get("/metrics/prometheus").text
    for line in text.splitlines():
        if line.startswith(name + "{") and label_fragment in line:
            return float(line.rsplit(" ", 1)[1])
    return 0.0


def test_health_endpoint_is_unchanged():
    assert client.get("/health").json() == {"status": "ok"}


def test_liveness_probe_reports_ok():
    res = client.get("/health/live")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_readiness_probe_checks_the_database():
    res = client.get("/health/ready")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ready"
    assert body["checks"]["database"] == "ok"


def test_prometheus_endpoint_returns_text_exposition():
    res = client.get("/metrics/prometheus")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/plain")
    body = res.text
    assert "# HELP routewise_requests_total" in body
    assert "# TYPE routewise_requests_total counter" in body
    assert "# TYPE routewise_request_duration_seconds histogram" in body
    assert "# TYPE routewise_tier_decisions_total counter" in body
    assert "routewise_build_info" in body


def test_request_metrics_increment_per_request():
    before = _counter_value("routewise_requests_total", 'path="/health/live"')
    client.get("/health/live")
    after = _counter_value("routewise_requests_total", 'path="/health/live"')
    assert after == before + 1


def test_cache_events_are_exposed():
    before = _counter_value("routewise_cache_events_total", 'result="skipped"')
    from router.cache import check_cache
    # Too short to cache: counted as "skipped" without touching the embedder.
    assert check_cache("yes", api_key_id=1) is None
    after = _counter_value("routewise_cache_events_total", 'result="skipped"')
    assert after == before + 1


def test_json_metrics_rollup_still_works():
    res = client.get("/metrics")
    assert res.status_code == 200
    body = res.json()
    for key in ("requests_total", "error_rate_1h_pct", "tier_counts_1h", "circuit_breakers"):
        assert key in body
