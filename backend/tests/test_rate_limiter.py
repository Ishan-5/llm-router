import pytest
from unittest.mock import patch
from router.rate_limiter import call_with_failover, AllTiersFailedError


def _fake_result(tier):
    return {"text": "ok", "tier": tier, "model_id": "test-model",
            "input_tokens": 1, "output_tokens": 1, "cost_usd": 0.0}


def test_succeeds_on_intended_tier_no_fallback():
    with patch("router.rate_limiter.call_model", return_value=_fake_result("mid")):
        result = call_with_failover("mid", "hello")
        assert result["fallback_used"] is False
        assert result["tier"] == "mid"


def test_falls_back_to_next_tier_when_intended_fails():
    def side_effect(tier, query, user_config=None):
        if tier == "frontier":
            raise Exception("simulated failure")
        return _fake_result(tier)

    with patch("router.rate_limiter.call_model", side_effect=side_effect), \
         patch("router.rate_limiter.time.sleep"):  # skip the real retry delay
        result = call_with_failover("frontier", "hello")
        assert result["fallback_used"] is True
        assert result["tier"] == "mid"  # first entry in frontier's fallback chain


def test_raises_when_every_tier_in_chain_fails():
    with patch("router.rate_limiter.call_model", side_effect=Exception("simulated failure")), \
         patch("router.rate_limiter.time.sleep"):
        with pytest.raises(AllTiersFailedError):
            call_with_failover("cheap", "hello")  # cheap has no fallback chain


def test_rate_limit_error_skips_retry_and_falls_back_immediately():
    def side_effect(tier, query, user_config=None):
        if tier == "mid":
            raise Exception("Error code: 429 rate_limit_exceeded")
        return _fake_result(tier)

    with patch("router.rate_limiter.call_model", side_effect=side_effect) as mock_call, \
         patch("router.rate_limiter.time.sleep") as mock_sleep:
        result = call_with_failover("mid", "hello")
        assert result["fallback_used"] is True
        # rate limit errors should NOT trigger the one-retry path
        mock_sleep.assert_not_called()