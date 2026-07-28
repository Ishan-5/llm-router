from fastapi.testclient import TestClient
from unittest.mock import patch
from router.main import app
from router.db import SessionLocal, ApiKey

client = TestClient(app)


def _make_test_key(name="test-key", budget=None):
    session = SessionLocal()
    key = ApiKey(key=f"rw_{name}", name=name, daily_budget_usd=budget, is_active=True)
    session.add(key)
    session.commit()
    session.refresh(key)
    session.close()
    return key.key


def test_route_without_auth_header_returns_401():
    response = client.post("/route", json={"query": "hi"})
    assert response.status_code == 401


def test_route_with_invalid_key_returns_401():
    response = client.post(
        "/route", json={"query": "hi"},
        headers={"Authorization": "Bearer not-a-real-key"},
    )
    assert response.status_code == 401


def test_route_rejects_empty_query():
    key = _make_test_key("empty-query-test")
    response = client.post(
        "/route", json={"query": ""},
        headers={"Authorization": f"Bearer {key}"},
    )
    assert response.status_code == 422


def test_route_success_with_mocked_model_and_provider():
    key = _make_test_key("happy-path-test")
    with patch("router.routes.route.check_cache", return_value=None), \
         patch("router.routes.route.get_tier", return_value=(1.5, "cheap", 3.4, 4.6)), \
         patch("router.routes.route.add_to_cache"), \
         patch("router.routes.route.call_with_failover") as mock_call:
        mock_call.return_value = {
            "text": "Paris", "tier": "cheap", "model_id": "test-model",
            "input_tokens": 5, "output_tokens": 3, "cost_usd": 0.0,
            "intended_tier": "cheap", "fallback_used": False,
        }
        response = client.post(
            "/route", json={"query": "capital of france"},
            headers={"Authorization": f"Bearer {key}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["response"] == "Paris"
        assert data["routed_to"] == "cheap"
        assert data["cache_hit"] is False


def test_route_uses_cache_when_available():
    key = _make_test_key("cache-hit-test")
    with patch("router.routes.route.check_cache") as mock_cache, \
         patch("router.routes.route.get_tier", return_value=(1.0, "cheap", 3.4, 4.6)):
        mock_cache.return_value = {
            "response": "cached answer", "tier": "cheap",
            "model_id": "test-model", "similarity": 0.99,
            "input_tokens": 10, "output_tokens": 5,
        }
        response = client.post(
            "/route", json={"query": "anything"},
            headers={"Authorization": f"Bearer {key}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["cache_hit"] is True
        assert data["cost_usd"] == 0.0