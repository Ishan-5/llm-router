"""GET /metrics/prometheus stays open locally but is gated when configured.

Grafana Cloud's Metrics Endpoint integration refuses to scrape a URL that
answers unauthenticated requests, so the deployed instance sets METRICS_BASIC_
USER/PASSWORD and the endpoint must then challenge with 401 + Basic. Because the
gate reads the module-level config names, these tests flip them with monkeypatch
rather than relying on the ambient environment.
"""
import base64

from fastapi.testclient import TestClient

import router.main as main
from router.main import app

client = TestClient(app)


def _header(user: str, password: str) -> dict:
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def test_metrics_are_open_when_no_credentials_are_configured(monkeypatch):
    monkeypatch.setattr(main, "METRICS_BASIC_USER", "")
    res = client.get("/metrics/prometheus")
    assert res.status_code == 200
    assert "routewise_build_info" in res.text


def test_metrics_challenge_when_credentials_are_configured(monkeypatch):
    monkeypatch.setattr(main, "METRICS_BASIC_USER", "grafanacloud")
    monkeypatch.setattr(main, "METRICS_BASIC_PASSWORD", "s3cret")
    res = client.get("/metrics/prometheus")
    assert res.status_code == 401
    assert res.headers["www-authenticate"].lower().startswith("basic")


def test_metrics_reject_wrong_credentials(monkeypatch):
    monkeypatch.setattr(main, "METRICS_BASIC_USER", "grafanacloud")
    monkeypatch.setattr(main, "METRICS_BASIC_PASSWORD", "s3cret")
    res = client.get("/metrics/prometheus", headers=_header("grafanacloud", "nope"))
    assert res.status_code == 401


def test_metrics_accept_correct_credentials(monkeypatch):
    monkeypatch.setattr(main, "METRICS_BASIC_USER", "grafanacloud")
    monkeypatch.setattr(main, "METRICS_BASIC_PASSWORD", "s3cret")
    res = client.get("/metrics/prometheus", headers=_header("grafanacloud", "s3cret"))
    assert res.status_code == 200
    assert "routewise_build_info" in res.text


def test_basic_auth_ok_rejects_malformed_and_missing_headers():
    from router.metrics import basic_auth_ok

    assert not basic_auth_ok(None, "u", "p")
    assert not basic_auth_ok("Bearer abc", "u", "p")
    # Not valid base64: the header must be rejected, not raise.
    assert not basic_auth_ok("Basic !!!not-base64!!!", "u", "p")
    assert basic_auth_ok(_header("u", "p")["Authorization"], "u", "p")
