import pytest
from fastapi import HTTPException
from router.auth import check_rate_limit, check_budget, RATE_LIMIT_PER_MINUTE
from router.db import ApiKey


def test_rate_limit_allows_requests_under_the_cap():
    key = "test-rate-limit-key-1"
    for _ in range(RATE_LIMIT_PER_MINUTE - 1):
        check_rate_limit(key)  # should not raise


def test_rate_limit_blocks_requests_over_the_cap():
    key = "test-rate-limit-key-2"
    for _ in range(RATE_LIMIT_PER_MINUTE):
        check_rate_limit(key)
    with pytest.raises(HTTPException) as exc_info:
        check_rate_limit(key)
    assert exc_info.value.status_code == 429


def test_no_budget_cap_means_always_under_budget():
    fake_key = ApiKey(id=99991, key="x", name="unlimited", daily_budget_usd=None)
    assert check_budget(fake_key) is True


def test_fresh_key_with_budget_starts_under_budget():
    # no requests logged yet for this key id in the test DB, so spend=0
    fake_key = ApiKey(id=99992, key="y", name="budgeted", daily_budget_usd=5.00)
    assert check_budget(fake_key) is True