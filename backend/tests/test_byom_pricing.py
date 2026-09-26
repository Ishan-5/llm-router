"""BYOM overrides must be costed with the overridden model's prices.

get_active_config resolves prices from the tier *default* model, so applying a
BYOM provider/model override without repricing would bill a BYOM request at the
default tier's rates. These tests pin the reprice behaviour.
"""
from fastapi.testclient import TestClient
from unittest.mock import patch
from router.main import app
from router.db import SessionLocal, ApiKey, ModelPricing

client = TestClient(app)

MOCK_RESULT = {
    "text": "ok", "tier": "cheap", "model_id": "x",
    "input_tokens": 5, "output_tokens": 3, "cost_usd": 0.0,
    "intended_tier": "cheap", "fallback_used": False,
}


def _make_test_key(name):
    session = SessionLocal()
    key = ApiKey(key=f"rw_{name}", name=name, is_active=True)
    session.add(key)
    session.commit()
    session.refresh(key)
    session.close()
    return key.key


def _seed_pricing(provider, model_id, price_in, price_out):
    session = SessionLocal()
    existing = session.query(ModelPricing).filter(
        ModelPricing.provider == provider, ModelPricing.model_id == model_id
    ).first()
    if existing:
        existing.price_per_m_input = price_in
        existing.price_per_m_output = price_out
        existing.is_active = True
    else:
        session.add(ModelPricing(
            provider=provider, model_id=model_id, display_name=model_id,
            price_per_m_input=price_in, price_per_m_output=price_out, is_active=True,
        ))
    session.commit()
    session.close()


def _route_with_byom(key, byom_config):
    """Run /route and return the user_config that reached the provider layer."""
    captured = {}

    def _capture(intended_tier, query, user_api_keys=None, messages=None,
                 max_tokens=None, temperature=None, user_config=None):
        captured["user_config"] = user_config
        return MOCK_RESULT

    with patch("router.routes.route.check_cache", return_value=None), \
         patch("router.routes.route.get_tier", return_value=(1.0, "cheap", 3.4, 4.6)), \
         patch("router.routes.route.add_to_cache"), \
         patch("router.routes.route.check_budget", return_value=True), \
         patch("router.routes.route.call_with_failover", side_effect=_capture):
        response = client.post(
            "/route",
            json={"query": "hi", "override_tier": "cheap", "byom_config": byom_config},
            headers={"Authorization": f"Bearer {key}"},
        )
    assert response.status_code == 200
    return captured["user_config"]


def test_byom_override_is_priced_from_model_pricing_table():
    """A BYOM model present in model_pricing must not inherit the default tier price."""
    _seed_pricing("byomprov", "byom-listed", 7.5, 22.5)
    key = _make_test_key("byom-listed-test")

    cfg = _route_with_byom(key, {"cheap": {"provider": "byomprov", "model_id": "byom-listed"}})["cheap"]

    assert cfg["provider"] == "byomprov"
    assert cfg["model_id"] == "byom-listed"
    # cheap default is 0.28/1.10 -- these must be the BYOM model's real rates
    assert cfg["price_per_m_input"] == 7.5
    assert cfg["price_per_m_output"] == 22.5


def test_byom_pricing_is_matched_on_provider_not_just_model_id():
    """Same model_id under a different provider must not borrow another provider's price."""
    _seed_pricing("provA", "shared-slug", 1.0, 2.0)
    key = _make_test_key("byom-provider-scope-test")

    cfg = _route_with_byom(key, {"cheap": {"provider": "provB", "model_id": "shared-slug"}})["cheap"]

    # provB/shared-slug is not in the table, so it keeps the cheap default rather
    # than silently adopting provA's price.
    assert cfg["provider"] == "provB"
    assert cfg["price_per_m_input"] == 0.28
    assert cfg["price_per_m_output"] == 1.10


def test_user_supplied_custom_prices_win_for_unlisted_model():
    """Custom models carry client-supplied prices, which take precedence."""
    key = _make_test_key("byom-custom-price-test")

    cfg = _route_with_byom(key, {"cheap": {
        "provider": "customprov", "model_id": "my-own-model",
        "price_per_m_input": 3.25, "price_per_m_output": 9.75,
    }})["cheap"]

    assert cfg["price_per_m_input"] == 3.25
    assert cfg["price_per_m_output"] == 9.75


def test_repricing_one_tier_leaves_other_tiers_untouched():
    _seed_pricing("byomprov", "byom-isolate", 5.0, 6.0)
    key = _make_test_key("byom-isolation-test")

    user_config = _route_with_byom(key, {"cheap": {"provider": "byomprov", "model_id": "byom-isolate"}})

    assert user_config["cheap"]["price_per_m_input"] == 5.0
    # mid/frontier must keep their own resolved rates (0.075/0.30, 0.15/0.60)
    assert user_config["mid"]["price_per_m_input"] == 0.075
    assert user_config["frontier"]["price_per_m_input"] == 0.15


def test_non_numeric_prices_are_ignored_not_crashing():
    """Garbage price strings must not poison cost accounting."""
    key = _make_test_key("byom-bad-price-test")

    cfg = _route_with_byom(key, {"cheap": {
        "provider": "customprov", "model_id": "bad-price-model",
        "price_per_m_input": "free", "price_per_m_output": None,
    }})["cheap"]

    assert cfg["price_per_m_input"] == 0.28
    assert cfg["price_per_m_output"] == 1.10


def test_api_key_only_override_keeps_default_tier_pricing():
    """Sending just a key must not disturb pricing."""
    _seed_pricing("byomprov", "byom-keyonly", 9.0, 9.0)
    key = _make_test_key("byom-keyonly-test")

    captured = {}

    def _capture(intended_tier, query, user_api_keys=None, messages=None,
                 max_tokens=None, temperature=None, user_config=None):
        captured["user_config"] = user_config
        return MOCK_RESULT

    with patch("router.routes.route.check_cache", return_value=None), \
         patch("router.routes.route.get_tier", return_value=(1.0, "cheap", 3.4, 4.6)), \
         patch("router.routes.route.add_to_cache"), \
         patch("router.routes.route.check_budget", return_value=True), \
         patch("router.routes.route.call_with_failover", side_effect=_capture):
        response = client.post(
            "/route",
            json={"query": "hi", "override_tier": "cheap",
                  "user_api_keys": {"cheap": "sk-user-supplied"}},
            headers={"Authorization": f"Bearer {key}"},
        )
    assert response.status_code == 200
    cfg = captured["user_config"]["cheap"]
    assert cfg["api_key"] == "sk-user-supplied"
    assert cfg["model_id"] == "deepseek/deepseek-chat"
    assert cfg["price_per_m_input"] == 0.28
