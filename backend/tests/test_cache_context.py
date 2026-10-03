"""The cache must never answer one conversation with another's response.

The cache used to key on the newest user message alone. Two unrelated
conversations that both said "yes" embed to ~0.97 similarity, comfortably above
the 0.95 match threshold, so the lookup would serve one conversation's answer to
another. The scorer already reads conversation context; the cache now reads the
same context and refuses short queries outright.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from router.cache import MIN_CACHE_QUERY_CHARS, cache_lookup_key
from router.main import app
from router.db import SessionLocal, ApiKey

client = TestClient(app)

# The request's `messages` carries the full transcript including the newest user
# turn, with `query` repeating that newest turn -- that is the existing
# multi-turn contract the scorer already relies on.
CONVERSATION = [
    {"role": "user", "content": "Design a rate limiter for a multi-tenant API"},
    {"role": "assistant", "content": "Use a token bucket per tenant key."},
    {"role": "user", "content": "now add retries"},
]
FOLLOWUP = "now add retries"
CONVERSATION_TEXT = (
    "user: Design a rate limiter for a multi-tenant API\n"
    "assistant: Use a token bucket per tenant key.\n"
    "user: now add retries"
)


def _make_test_key(name="cache-context-test", budget=None):
    session = SessionLocal()
    key = ApiKey(key=f"rw_{name}", name=name, daily_budget_usd=budget, is_active=True)
    session.add(key)
    session.commit()
    session.refresh(key)
    session.close()
    return key.key


# --- cache_lookup_key -------------------------------------------------------

@pytest.mark.parametrize("short", ["yes", "ok", "do it", "continue", "sure thing", "  y  "])
def test_short_queries_are_never_cacheable(short):
    assert cache_lookup_key(short) is None


def test_ordinary_single_turn_query_is_cacheable():
    query = "How do I center a div in CSS?"
    assert cache_lookup_key(query) == query


def test_cache_key_prefers_context_over_bare_followup():
    context = "user: Design a rate limiter\nuser: now add retries"
    assert cache_lookup_key("now add retries", context) == context


def test_context_itself_too_short_is_not_cacheable():
    # The floor applies to whatever text is actually embedded, context included.
    assert cache_lookup_key("do it", "user: do it") is None


def test_empty_query_is_not_cacheable():
    assert cache_lookup_key("") is None
    assert cache_lookup_key("   ") is None


def test_floor_is_documented_consistently():
    assert MIN_CACHE_QUERY_CHARS == 12


# --- the lookup never touches the embedder for short queries ----------------

def test_check_cache_short_query_skips_embedder_entirely():
    embedder = MagicMock()
    with patch("router.cache.get_embedder", return_value=embedder):
        from router.cache import check_cache
        assert check_cache("yes", api_key_id=1) is None
    embedder.encode.assert_not_called()


def test_check_cache_embeds_context_when_given():
    embedder = MagicMock()
    embedder.encode.return_value = [[0.0] * 384]
    session = MagicMock()
    session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
    with patch("router.cache.get_embedder", return_value=embedder), \
         patch("router.cache.SessionLocal", return_value=session):
        from router.cache import check_cache
        assert check_cache(FOLLOWUP, api_key_id=1, context=CONVERSATION_TEXT) is None
    embedded = embedder.encode.call_args[0][0][0]
    assert "Design a rate limiter" in embedded
    assert embedded != FOLLOWUP


def test_add_to_cache_skips_short_query():
    embedder = MagicMock()
    with patch("router.cache.get_embedder", return_value=embedder):
        from router.cache import add_to_cache
        add_to_cache("yes", "an answer", "cheap", "m", 0.0, 1, 1, api_key_id=1)
    embedder.encode.assert_not_called()


# --- end-to-end behaviour ---------------------------------------------------

def test_multiturn_request_skips_cache_by_default():
    key = _make_test_key("multiturn-default")
    with patch("router.routes.route.check_cache") as mock_cache, \
         patch("router.routes.route.get_tier", return_value=(1.0, "cheap", 3.4, 4.6)), \
         patch("router.routes.route.call_with_failover") as mock_call:
        mock_call.return_value = {
            "text": "ok", "tier": "cheap", "model_id": "m", "input_tokens": 1,
            "output_tokens": 1, "cost_usd": 0.0, "intended_tier": "cheap",
            "fallback_used": False,
        }
        response = client.post(
            "/route",
            json={"query": FOLLOWUP, "messages": CONVERSATION},
            headers={"Authorization": f"Bearer {key}"},
        )
        assert response.status_code == 200
        assert response.json()["cache_hit"] is False
    mock_cache.assert_not_called()


def test_multiturn_request_can_opt_into_context_cache():
    key = _make_test_key("multiturn-optin")
    with patch("router.routes.route.check_cache") as mock_cache, \
         patch("router.routes.route.get_tier", return_value=(1.0, "cheap", 3.4, 4.6)), \
         patch("router.routes.route.call_with_failover"):
        mock_cache.return_value = None
        client.post(
            "/route",
            json={
                "query": FOLLOWUP,
                "messages": CONVERSATION,
                "allow_context_cache": True,
            },
            headers={"Authorization": f"Bearer {key}"},
        )
    assert mock_cache.call_count == 1
    # The lookup must be handed the transcript, not the bare follow-up.
    assert "Design a rate limiter" in mock_cache.call_args.kwargs["context"]


def test_single_turn_request_still_uses_the_cache():
    key = _make_test_key("singleturn-still-cached")
    with patch("router.routes.route.check_cache") as mock_cache, \
         patch("router.routes.route.get_tier", return_value=(1.0, "cheap", 3.4, 4.6)):
        mock_cache.return_value = {
            "response": "cached answer", "tier": "cheap", "model_id": "m",
            "similarity": 0.99, "input_tokens": 10, "output_tokens": 5,
        }
        response = client.post(
            "/route", json={"query": "How do I center a div?"},
            headers={"Authorization": f"Bearer {key}"},
        )
        assert response.status_code == 200
        assert response.json()["cache_hit"] is True
    assert mock_cache.call_count == 1
    assert mock_cache.call_args.kwargs["context"] is None


def test_bypass_cache_still_wins():
    key = _make_test_key("bypass-still-wins")
    with patch("router.routes.route.check_cache") as mock_cache, \
         patch("router.routes.route.get_tier", return_value=(1.0, "cheap", 3.4, 4.6)), \
         patch("router.routes.route.call_with_failover") as mock_call:
        mock_call.return_value = {
            "text": "ok", "tier": "cheap", "model_id": "m", "input_tokens": 1,
            "output_tokens": 1, "cost_usd": 0.0, "intended_tier": "cheap",
            "fallback_used": False,
        }
        client.post(
            "/route",
            json={
                "query": FOLLOWUP,
                "messages": CONVERSATION,
                "bypass_cache": True,
                "allow_context_cache": True,
            },
            headers={"Authorization": f"Bearer {key}"},
        )
    mock_cache.assert_not_called()


def test_openai_multiturn_skips_cache_by_default():
    key = _make_test_key("oai-multiturn")
    with patch("router.openai_compat.check_cache") as mock_cache, \
         patch("router.openai_compat.get_tier", return_value=(1.0, "cheap", 3.4, 4.6)), \
         patch("router.openai_compat.call_with_failover") as mock_call:
        mock_call.return_value = {
            "text": "ok", "tier": "cheap", "model_id": "m", "input_tokens": 1,
            "output_tokens": 1, "cost_usd": 0.0, "intended_tier": "cheap",
            "fallback_used": False,
        }
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "auto",
                "messages": [
                    {"role": "user", "content": "Design a rate limiter for a multi-tenant API"},
                    {"role": "assistant", "content": "Use a token bucket per tenant key."},
                    {"role": "user", "content": "now add retries"},
                ],
            },
            headers={"Authorization": f"Bearer {key}"},
        )
        assert response.status_code == 200
    mock_cache.assert_not_called()