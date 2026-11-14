"""Per-key BYOM: the key carries the provider, model and credential.

The interesting part is not the CRUD, it is the two promises: the credential is
encrypted at rest and never comes back out, and a request that switches
provider cannot carry the stored secret to the new provider.
"""

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from unittest.mock import patch

from router import secret_store
from router.db import SessionLocal, KeyProviderConfig
from router.main import app
from router.auth import invalidate_key_cache
from router.budgets import UNLIMITED
from router.model_config_loader import get_active_config
from router.routes import keys as keys_module
from router.routes.route import _apply_byom_overrides

client = TestClient(app)

USER_ID = "byom-user-1"
OTHER_USER_ID = "byom-user-2"
RAW_KEY = "gsk_supersecretvalue1234"


@pytest.fixture(autouse=True)
def _encryption_key(monkeypatch):
    monkeypatch.setattr(secret_store, "BYOM_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr(secret_store, "SUPABASE_SERVICE_KEY", "")
    yield


@pytest.fixture(autouse=True)
def _as_signed_in_user():
    app.dependency_overrides[keys_module.require_user] = lambda: USER_ID
    yield
    app.dependency_overrides.clear()
    invalidate_key_cache()


def _create_key(**fields) -> dict:
    return client.post("/keys", json={"name": "byom-test", **fields}).json()


def _put_byom(key_id, **tiers):
    return client.put(f"/keys/{key_id}/byom", json=tiers)


def _row(key_id, tier):
    session = SessionLocal()
    try:
        return session.query(KeyProviderConfig).filter(
            KeyProviderConfig.api_key_id == key_id, KeyProviderConfig.tier == tier
        ).first()
    finally:
        session.close()


# --- write / read ----------------------------------------------------------

def test_saving_a_tier_returns_a_hint_not_the_credential():
    key = _create_key()
    response = _put_byom(
        key["id"],
        cheap={"provider": "groq", "model_id": "llama-3.1-8b-instant", "api_key": RAW_KEY},
    )

    assert response.status_code == 200
    tier = response.json()["byom"]["cheap"]
    assert tier["provider"] == "groq"
    assert tier["model_id"] == "llama-3.1-8b-instant"
    assert tier["api_key_masked"] == "gsk…1234"
    assert tier["has_api_key"] is True
    assert RAW_KEY not in response.text


def test_credential_is_encrypted_at_rest():
    key = _create_key()
    _put_byom(key["id"], cheap={"provider": "groq", "model_id": "m", "api_key": RAW_KEY})

    row = _row(key["id"], "cheap")
    assert row.api_key_encrypted
    assert RAW_KEY not in row.api_key_encrypted
    assert row.api_key_hint == "gsk…1234"


def test_a_key_with_no_byom_reports_an_empty_map():
    key = _create_key()
    response = client.get(f"/keys/{key['id']}/byom")
    assert response.status_code == 200
    assert response.json()["byom"] == {}


def test_put_replaces_the_whole_config():
    key = _create_key()
    _put_byom(
        key["id"],
        cheap={"provider": "groq", "model_id": "a", "api_key": "gsk_aaaaaaaaaaaa"},
        mid={"provider": "groq", "model_id": "b", "api_key": "gsk_bbbbbbbbbbbb"},
    )
    cleared = _put_byom(
        key["id"],
        mid={"provider": "groq", "model_id": "b", "api_key": "gsk_bbbbbbbbbbbb"},
    )

    assert cleared.status_code == 200
    assert set(cleared.json()["byom"]) == {"mid"}
    assert _row(key["id"], "cheap") is None


def test_omitting_the_credential_keeps_the_stored_one():
    key = _create_key()
    _put_byom(key["id"], cheap={"provider": "groq", "model_id": "a", "api_key": RAW_KEY})
    before = _row(key["id"], "cheap").api_key_encrypted

    response = _put_byom(key["id"], cheap={"provider": "groq", "model_id": "a-renamed"})

    assert response.status_code == 200
    row = _row(key["id"], "cheap")
    assert row.model_id == "a-renamed"
    assert row.api_key_encrypted == before


def test_changing_provider_without_a_credential_is_rejected():
    key = _create_key()
    _put_byom(key["id"], cheap={"provider": "groq", "model_id": "a", "api_key": RAW_KEY})

    response = _put_byom(key["id"], cheap={"provider": "openai", "model_id": "gpt-5"})

    assert response.status_code == 400
    assert "api_key is required" in response.json()["detail"]


def test_unknown_provider_is_rejected():
    key = _create_key()
    response = _put_byom(
        key["id"], cheap={"provider": "not-a-provider", "model_id": "m", "api_key": RAW_KEY}
    )
    assert response.status_code == 422


def test_ollama_needs_no_credential():
    key = _create_key()
    response = _put_byom(key["id"], cheap={"provider": "ollama", "model_id": "llama3"})
    assert response.status_code == 200
    assert response.json()["byom"]["cheap"]["has_api_key"] is False


def test_another_users_key_is_not_found():
    key = _create_key()
    app.dependency_overrides[keys_module.require_user] = lambda: OTHER_USER_ID
    try:
        assert _put_byom(key["id"], cheap={"provider": "groq", "model_id": "m", "api_key": RAW_KEY}).status_code == 404
    finally:
        app.dependency_overrides[keys_module.require_user] = lambda: USER_ID


def test_write_is_refused_when_no_encryption_secret_is_configured(monkeypatch):
    monkeypatch.setattr(secret_store, "BYOM_ENCRYPTION_KEY", "")
    monkeypatch.setattr(secret_store, "SUPABASE_SERVICE_KEY", "")
    key = _create_key()

    response = _put_byom(key["id"], cheap={"provider": "groq", "model_id": "m", "api_key": RAW_KEY})

    assert response.status_code == 503
    assert _row(key["id"], "cheap") is None


# --- routing ---------------------------------------------------------------

def test_routing_config_uses_the_keys_own_model_and_credential():
    key = _create_key()
    _put_byom(
        key["id"],
        cheap={
            "provider": "openai",
            "model_id": "gpt-4o-mini",
            "api_key": RAW_KEY,
            "price_per_m_input": 0.15,
            "price_per_m_output": 0.6,
        },
    )

    cfg = get_active_config(USER_ID, key["id"])
    assert cfg["cheap"]["provider"] == "openai"
    assert cfg["cheap"]["model_id"] == "gpt-4o-mini"
    assert cfg["cheap"]["api_key"] == RAW_KEY
    assert cfg["cheap"]["price_per_m_input"] == 0.15
    assert cfg["cheap"]["price_per_m_output"] == 0.6


def test_other_keys_do_not_inherit_the_byom_credential():
    key = _create_key()
    _put_byom(key["id"], cheap={"provider": "openai", "model_id": "gpt-4o-mini", "api_key": RAW_KEY})

    other = _create_key()
    assert "api_key" not in get_active_config(USER_ID, other["id"])["cheap"]


def test_request_switching_provider_drops_the_stored_credential():
    user_config = {
        "cheap": {
            "provider": "openai",
            "model_id": "gpt-4o-mini",
            "api_key": RAW_KEY,
            "price_per_m_input": 0.0,
            "price_per_m_output": 0.0,
        }
    }

    _apply_byom_overrides(user_config, {"cheap": {"provider": "groq", "model_id": "llama-3.1-8b-instant"}})

    assert user_config["cheap"]["provider"] == "groq"
    assert user_config["cheap"]["api_key"] == ""


def test_request_keeping_provider_keeps_the_stored_credential():
    user_config = {
        "cheap": {
            "provider": "openai",
            "model_id": "gpt-4o-mini",
            "api_key": RAW_KEY,
            "price_per_m_input": 0.0,
            "price_per_m_output": 0.0,
        }
    }

    _apply_byom_overrides(user_config, {"cheap": {"model_id": "gpt-4o"}})

    assert user_config["cheap"]["model_id"] == "gpt-4o"
    assert user_config["cheap"]["api_key"] == RAW_KEY


# --- a credential that stopped decrypting ----------------------------------
#
# The failure this guards against: rotate the server encryption key, and every
# saved tier still reports a hint, still reads as configured, while routing
# silently uses the account model. Worse, re-saving the form without retyping
# the key used to keep the undecryptable ciphertext forever.

def _rotate_encryption_key(monkeypatch):
    monkeypatch.setattr(secret_store, "BYOM_ENCRYPTION_KEY", Fernet.generate_key().decode())


def test_summary_marks_a_credential_that_no_longer_decrypts(monkeypatch):
    key = _create_key()
    _put_byom(key["id"], cheap={"provider": "groq", "model_id": "m", "api_key": RAW_KEY})

    _rotate_encryption_key(monkeypatch)

    tier = client.get(f"/keys/{key['id']}/byom").json()["byom"]["cheap"]
    # The row is still there and still holds ciphertext, but it is unusable.
    assert tier["has_api_key"] is True
    assert tier["credential_ok"] is False

    # The router falls back to the account config rather than sending a key it
    # cannot read -- that is the silent part the summary now makes visible.
    assert get_active_config(USER_ID, key["id"])["cheap"]["model_id"] != "m"


def test_resaving_without_the_key_is_rejected_after_a_key_change(monkeypatch):
    key = _create_key()
    _put_byom(key["id"], cheap={"provider": "groq", "model_id": "m", "api_key": RAW_KEY})
    before = _row(key["id"], "cheap").api_key_encrypted

    _rotate_encryption_key(monkeypatch)

    response = _put_byom(key["id"], cheap={"provider": "groq", "model_id": "m"})

    assert response.status_code == 400
    assert "decrypted" in response.json()["detail"]
    # The dead ciphertext is not silently kept as if the save had worked.
    assert _row(key["id"], "cheap").api_key_encrypted == before


def test_resaving_with_a_fresh_credential_repairs_the_tier(monkeypatch):
    key = _create_key()
    _put_byom(key["id"], cheap={"provider": "groq", "model_id": "m", "api_key": RAW_KEY})

    _rotate_encryption_key(monkeypatch)
    repaired = _put_byom(
        key["id"], cheap={"provider": "groq", "model_id": "m", "api_key": "gsk_secondsecret9999"}
    )

    assert repaired.status_code == 200
    assert repaired.json()["byom"]["cheap"]["credential_ok"] is True
    assert get_active_config(USER_ID, key["id"])["cheap"]["api_key"] == "gsk_secondsecret9999"


def test_route_reports_the_provider_that_served_the_request():
    """The response names the provider, so a BYOM override is verifiable without
    inferring it from model_id (which can match the account default)."""
    key = _create_key()
    _put_byom(key["id"], cheap={"provider": "groq", "model_id": "qwen/qwen3-32b", "api_key": RAW_KEY})

    captured = {}

    def _capture(intended_tier, query, user_api_keys=None, messages=None,
                 max_tokens=None, temperature=None, user_config=None):
        captured["user_config"] = user_config
        return {
            "text": "ok", "tier": "cheap", "model_id": "qwen/qwen3-32b",
            "input_tokens": 5, "output_tokens": 3, "cost_usd": 0.0,
            "intended_tier": "cheap", "fallback_used": False,
        }

    with patch("router.routes.route.check_cache", return_value=None), \
         patch("router.routes.route.get_tier", return_value=(1.0, "cheap", 3.4, 4.6)), \
         patch("router.routes.route.add_to_cache"), \
         patch("router.routes.route.budget_status", return_value=UNLIMITED), \
         patch("router.routes.route.call_with_failover", side_effect=_capture):
        response = client.post(
            "/route",
            json={"query": "hi", "override_tier": "cheap"},
            headers={"Authorization": f"Bearer {key['key']}"},
        )

    assert response.status_code == 200
    assert captured["user_config"]["cheap"]["provider"] == "groq"
    assert response.json()["provider"] == "groq"
    assert response.json()["model_id"] == "qwen/qwen3-32b"
