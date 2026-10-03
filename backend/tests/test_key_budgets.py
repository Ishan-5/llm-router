"""Per-key daily budgets: create with one, change one, clear one.

The column and the enforcement already existed -- check_budget reads it and the
router downgrades to cheap when a key is over. Nothing could write it, so the cap
was unreachable without hand-running SQL. These tests cover the write path, the
ownership check, and the 30-second auth-cache invalidation that keeps a new cap
from being ignored for half a minute.
"""

import pytest
from fastapi.testclient import TestClient

from router.db import SessionLocal, ApiKey
from router.main import app
from router.auth import invalidate_key_cache
from router.routes import keys as keys_module

client = TestClient(app)

USER_ID = "budget-user-1"
OTHER_USER_ID = "budget-user-2"


@pytest.fixture(autouse=True)
def _as_signed_in_user():
    """These endpoints need a Supabase JWT; swap require_user for a fixed id."""
    app.dependency_overrides[keys_module.require_user] = lambda: USER_ID
    yield
    app.dependency_overrides.clear()
    invalidate_key_cache()


def _owned_key(name, budget=None, user_id=USER_ID):
    session = SessionLocal()
    key = ApiKey(key=f"rw_owned_{name}", name=name, user_id=user_id, daily_budget_usd=budget, is_active=True)
    session.add(key)
    session.commit()
    session.refresh(key)
    session.close()
    return key.id


def _read_budget(key_id):
    session = SessionLocal()
    try:
        row = session.query(ApiKey).filter(ApiKey.id == key_id).first()
        return None if row is None else row.daily_budget_usd
    finally:
        session.close()


# --- create ----------------------------------------------------------------

def test_create_key_without_budget_is_unlimited():
    response = client.post("/keys", json={"name": "plain"})
    assert response.status_code == 200
    assert response.json()["daily_budget_usd"] is None


def test_create_key_with_budget():
    response = client.post("/keys", json={"name": "staging", "daily_budget_usd": 2.0})
    assert response.status_code == 200
    assert response.json()["daily_budget_usd"] == 2.0


def test_create_key_rejects_negative_budget():
    response = client.post("/keys", json={"name": "bad", "daily_budget_usd": -1.0})
    assert response.status_code == 422


def test_create_key_accepts_zero_budget():
    # Zero is a real choice: spend nothing.
    response = client.post("/keys", json={"name": "frozen", "daily_budget_usd": 0})
    assert response.status_code == 200
    assert response.json()["daily_budget_usd"] == 0


def test_create_key_accepts_a_large_budget():
    # Not capped on purpose: a very high cap is just "effectively unlimited",
    # and inventing a ceiling would only surprise someone with a real contract.
    response = client.post("/keys", json={"name": "big", "daily_budget_usd": 1e12})
    assert response.status_code == 200
    assert response.json()["daily_budget_usd"] == 1e12


@pytest.mark.parametrize("bad", [float("inf"), float("-inf"), float("nan")])
def test_non_finite_budgets_are_rejected_at_the_model(bad):
    # Guarded in the validator. Checked here rather than over HTTP because
    # `Infinity` is not valid JSON, so FastAPI cannot even serialize the 422 body.
    from router.routes.keys import KeyCreateRequest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        KeyCreateRequest(name="x", daily_budget_usd=bad)


# --- list ------------------------------------------------------------------

def test_list_keys_includes_budget():
    key_id = _owned_key("listed", budget=7.5)
    response = client.get("/keys")
    assert response.status_code == 200
    row = next(r for r in response.json() if r["id"] == key_id)
    assert row["daily_budget_usd"] == 7.5


def test_list_keys_hides_other_users_keys():
    mine = _owned_key("mine-visible", budget=1.0)
    theirs = _owned_key("theirs-hidden", budget=99.0, user_id=OTHER_USER_ID)
    ids = {r["id"] for r in client.get("/keys").json()}
    assert mine in ids
    assert theirs not in ids


# --- update ----------------------------------------------------------------

def test_patch_sets_budget():
    key_id = _owned_key("patch-target")
    response = client.patch(f"/keys/{key_id}", json={"daily_budget_usd": 5.0})
    assert response.status_code == 200
    assert response.json()["daily_budget_usd"] == 5.0
    assert _read_budget(key_id) == 5.0


def test_patch_clears_budget_back_to_unlimited():
    key_id = _owned_key("clear-target", budget=5.0)
    response = client.patch(f"/keys/{key_id}", json={"daily_budget_usd": None})
    assert response.status_code == 200
    assert _read_budget(key_id) is None


def test_patch_rejects_negative_budget():
    key_id = _owned_key("neg-target", budget=1.0)
    response = client.patch(f"/keys/{key_id}", json={"daily_budget_usd": -0.01})
    assert response.status_code == 422
    assert _read_budget(key_id) == 1.0


def test_patch_cannot_touch_another_users_key():
    key_id = _owned_key("not-yours", budget=3.0, user_id=OTHER_USER_ID)
    response = client.patch(f"/keys/{key_id}", json={"daily_budget_usd": 0.01})
    assert response.status_code == 404
    assert _read_budget(key_id) == 3.0


def test_patch_unknown_key_is_404():
    assert client.patch("/keys/99999999", json={"daily_budget_usd": 1.0}).status_code == 404


def test_patch_invalidates_the_auth_cache():
    """A stale cached record would keep enforcing the old cap for up to 30s."""
    key_id = _owned_key("cache-invalidation")
    with pytest.MonkeyPatch.context() as mp:
        called = []
        mp.setattr(keys_module, "invalidate_key_cache", lambda k=None: called.append(k))
        client.patch(f"/keys/{key_id}", json={"daily_budget_usd": 4.0})
    assert len(called) == 1
    assert called[0] == f"rw_owned_cache-invalidation"


# --- enforcement wiring ----------------------------------------------------

def test_persisted_budget_actually_reaches_check_budget():
    """End of the chain: a budget written over the API is the one auth reads."""
    from router.auth import check_budget

    key_id = _owned_key("enforced", budget=None)
    session = SessionLocal()
    record = session.query(ApiKey).filter(ApiKey.id == key_id).first()
    session.close()
    assert check_budget(record) is True

    client.patch(f"/keys/{key_id}", json={"daily_budget_usd": 0.0})

    session = SessionLocal()
    record = session.query(ApiKey).filter(ApiKey.id == key_id).first()
    session.close()
    assert check_budget(record) is False