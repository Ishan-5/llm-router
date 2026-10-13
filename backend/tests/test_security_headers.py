"""Baseline security headers must reach every surface.

The middleware is pure ASGI, so the property worth locking in is that streaming
(SSE) still streams while carrying the headers.
"""
from unittest.mock import patch

from fastapi.testclient import TestClient

from router.db import SessionLocal, ApiKey
from router.main import app
from router.security import SECURITY_HEADERS

client = TestClient(app)


def _make_test_key(name="security-headers-test"):
    session = SessionLocal()
    key = ApiKey(key=f"rw_{name}", name=name, is_active=True)
    session.add(key)
    session.commit()
    session.refresh(key)
    session.close()
    return key.key


_AUTH = {"Authorization": f"Bearer {_make_test_key()}"}


def _assert_security_headers(resp):
    for name, value in SECURITY_HEADERS.items():
        assert resp.headers.get(name.lower()) == value, f"missing/wrong {name}"


def test_health_carries_security_headers():
    resp = client.get("/health")
    assert resp.status_code == 200
    _assert_security_headers(resp)


def test_prometheus_exposition_carries_security_headers():
    resp = client.get("/metrics/prometheus")
    assert resp.status_code == 200
    _assert_security_headers(resp)


def test_error_responses_carry_security_headers():
    # No API key: the 401 comes from a dependency, not a route handler.
    resp = client.post("/route", json={"query": "hello there"})
    assert resp.status_code == 401
    _assert_security_headers(resp)


def test_streaming_still_streams_and_carries_security_headers():
    with patch("router.openai_compat.check_cache", return_value=None), \
         patch("router.openai_compat.get_tier", return_value=(1.0, "cheap", 3.4, 4.6)), \
         patch("router.openai_compat.stream_model_with_failover") as mock_stream:
        def fake_stream(tier, query, user_config=None, messages=None, max_tokens=None, temperature=None):
            yield "Hi"
            yield {"tier": "cheap", "model_id": "test-model",
                   "input_tokens": 1, "output_tokens": 1, "cost_usd": 0.0}

        mock_stream.side_effect = fake_stream
        resp = client.post(
            "/v1/chat/completions",
            json={"model": "auto", "messages": [{"role": "user", "content": "hi"}], "stream": True},
            headers=_AUTH,
        )

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "text/event-stream; charset=utf-8"
    assert "[DONE]" in resp.text
    _assert_security_headers(resp)


def test_hsts_is_absent_over_plain_http():
    # Browsers ignore HSTS over http; sending it anyway would be misleading.
    assert "strict-transport-security" not in client.get("/health").headers
