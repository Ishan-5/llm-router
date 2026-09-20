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
    def side_effect(tier, query, user_config=None, messages=None, max_tokens=None, temperature=None):
        if tier == "frontier":
            raise Exception("simulated failure")
        return _fake_result(tier)

    with patch("router.rate_limiter.call_model", side_effect=side_effect), \
         patch("router.rate_limiter.time.sleep"):  # skip the real retry delay
        result = call_with_failover("frontier", "hello")
        assert result["fallback_used"] is True
        assert result["tier"] == "mid"  # first entry in frontier's fallback chain


def test_raises_when_every_provider_fails():
    with patch("router.rate_limiter.call_model", side_effect=Exception("simulated failure")), \
         patch("router.rate_limiter.call_gemini", side_effect=Exception("simulated Gemini failure")), \
         patch("router.rate_limiter.time.sleep"):
        with pytest.raises(AllTiersFailedError):
            call_with_failover("cheap", "hello")  # cheap has no fallback chain


def test_rate_limit_error_skips_retry_and_falls_back_immediately():
    def side_effect(tier, query, user_config=None, messages=None, max_tokens=None, temperature=None):
        if tier == "mid":
            raise Exception("Error code: 429 rate_limit_exceeded")
        return _fake_result(tier)

    with patch("router.rate_limiter.call_model", side_effect=side_effect) as mock_call, \
         patch("router.rate_limiter.time.sleep") as mock_sleep:
        result = call_with_failover("mid", "hello")
        assert result["fallback_used"] is True
        # rate limit errors should NOT trigger the one-retry path
        mock_sleep.assert_not_called()


def test_chaos_mode_skips_every_tier_and_serves_gemini_last_resort():
    from router.circuit_breaker import set_chaos, get_chaos
    try:
        set_chaos(True)  # simulates a provider-wide outage (cheap/mid/frontier down)
        with patch("router.rate_limiter.call_model") as mock_call, \
             patch("router.rate_limiter.call_gemini", return_value=_fake_result("gemini")) as mock_gemini:
            result = call_with_failover("mid", "hello")
            assert result["tier"] == "gemini"
            assert result["intended_tier"] == "mid"
            assert result["fallback_used"] is True
            assert result["cross_provider_fallback"] is True
            mock_call.assert_not_called()  # every tier was skipped via open breakers
            mock_gemini.assert_called_once()
    finally:
        set_chaos(False)
        assert get_chaos()["active"] is False
