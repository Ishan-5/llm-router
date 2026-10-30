"""Per-key routing defaults.

A key used to be only a spend cap. These tests cover the write path for the
routing profile (policy, tier ceiling, sensitivity, cache) and the rules that
apply it: a request may override the defaults, but a tier ceiling always wins.
"""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from router.db import SessionLocal, ApiKey
from router.main import app
from router.auth import invalidate_key_cache
from router.routes import keys as keys_module
from router.key_prefs import (
    cached_tier_allowed,
    clamp_tier_to_key,
    key_cache_bypassed,
    key_support_mode,
    key_threshold,
)

client = TestClient(app)

USER_ID = "routing-defaults-user-1"


@pytest.fixture(autouse=True)
def _as_signed_in_user():
    app.dependency_overrides[keys_module.require_user] = lambda: USER_ID
    yield
    app.dependency_overrides.clear()
    invalidate_key_cache()


def _create(**fields):
    payload = {"name": "routing-test", **fields}
    return client.post("/keys", json=payload)


# --- create / update -------------------------------------------------------

def test_create_key_with_routing_defaults():
    response = _create(
        default_policy="3tier",
        max_tier="mid",
        default_threshold=0.8,
        cache_enabled=False,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["default_policy"] == "3tier"
    assert body["max_tier"] == "mid"
    assert body["default_threshold"] == 0.8
    assert body["cache_enabled"] is False


def test_create_key_without_routing_defaults_uses_generic_and_cache():
    body = _create().json()
    assert body["default_policy"] is None
    assert body["max_tier"] is None
    assert body["default_threshold"] is None
    assert body["cache_enabled"] is True


def test_unknown_policy_is_rejected():
    assert _create(default_policy="turbo").status_code == 422


def test_unknown_tier_ceiling_is_rejected():
    assert _create(max_tier="ultra").status_code == 422


def test_threshold_outside_range_is_rejected():
    assert _create(default_threshold=2.5).status_code == 422


def test_patch_updates_and_clears_routing_defaults():
    key_id = _create(max_tier="cheap", default_threshold=1.4).json()["id"]

    updated = client.patch(f"/keys/{key_id}", json={"max_tier": "frontier", "cache_enabled": False})
    assert updated.status_code == 200
    assert updated.json()["max_tier"] == "frontier"
    assert updated.json()["cache_enabled"] is False

    cleared = client.patch(f"/keys/{key_id}", json={"max_tier": None, "default_threshold": None})
    assert cleared.status_code == 200
    assert cleared.json()["max_tier"] is None
    assert cleared.json()["default_threshold"] is None


# --- enforcement rules -----------------------------------------------------

def test_request_policy_wins_over_key_policy():
    key = SimpleNamespace(default_policy="3tier", default_threshold=0.5, cache_enabled=False)
    assert key_support_mode(key, "2tier") == "2tier"
    assert key_support_mode(key, None) == "3tier"
    assert key_threshold(key, 1.0) == 0.5
    assert key_threshold(SimpleNamespace(default_threshold=None), 1.0) == 1.0
    assert key_cache_bypassed(key) is True
    assert key_cache_bypassed(SimpleNamespace(cache_enabled=True), True) is True


def test_cheap_ceiling_beats_an_explicit_frontier_request():
    key = SimpleNamespace(max_tier="cheap")
    tier, ceiling = clamp_tier_to_key(key, "frontier", None)
    assert (tier, ceiling) == ("cheap", "cheap")
    assert cached_tier_allowed(key, "mid", None) is False
    assert cached_tier_allowed(key, "cheap", None) is True


def test_mid_ceiling_under_two_tier_policy_collapses_to_cheap():
    key = SimpleNamespace(max_tier="mid")
    assert clamp_tier_to_key(key, "frontier", "2tier")[0] == "cheap"
    assert clamp_tier_to_key(key, "frontier", "3tier")[0] == "mid"
    assert clamp_tier_to_key(key, "cheap", "3tier") == ("cheap", None)
