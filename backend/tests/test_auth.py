import pytest
from fastapi import HTTPException
from router.auth import (
    RATE_LIMIT_PER_MINUTE,
    READ_RATE_LIMIT_PER_MINUTE,
    check_budget,
    check_rate_limit,
    rate_limit_bucket,
)
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


def test_read_and_call_buckets_are_independent_budgets():
    """Free preview/poll traffic must never spend the provider-call budget.

    They used to share one budget, so the dashboard's own polling emptied it
    and real questions came back 429.
    """
    key = "test-rate-limit-buckets"
    for _ in range(RATE_LIMIT_PER_MINUTE):
        check_rate_limit(key, "call")
    with pytest.raises(HTTPException) as exc_info:
        check_rate_limit(key, "call")
    assert exc_info.value.status_code == 429

    # Exhausting the call budget left the read budget untouched.
    check_rate_limit(key, "read")


def test_read_bucket_reports_its_own_higher_cap():
    key = "test-rate-limit-read-cap"
    for _ in range(READ_RATE_LIMIT_PER_MINUTE):
        check_rate_limit(key, "read")
    with pytest.raises(HTTPException) as exc_info:
        check_rate_limit(key, "read")
    assert exc_info.value.status_code == 429
    assert str(READ_RATE_LIMIT_PER_MINUTE) in exc_info.value.detail


def test_read_budget_outruns_the_dashboards_own_polling():
    """Two minutes of the fastest observed /stats poll (every 12s)."""
    assert READ_RATE_LIMIT_PER_MINUTE > RATE_LIMIT_PER_MINUTE
    assert READ_RATE_LIMIT_PER_MINUTE >= 120


@pytest.mark.parametrize(
    "path,expected",
    [
        ("/route/explain", "read"),
        ("/route/policies", "read"),
        ("/route/feedback", "read"),
        ("/stats", "read"),
        ("/logs", "read"),
        ("/logs/42", "read"),
        ("/config", "read"),
        ("/demo/chaos", "read"),
        # Dashboard reads the frontend also polls: every one of these must
        # spend the read budget, never the model budget.
        ("/settings", "read"),
        ("/analytics", "read"),
        ("/policy-analytics", "read"),
        ("/calibrate", "read"),
        ("/compare", "read"),
        ("/keys", "read"),
        ("/admin/stats", "read"),
        ("/project", "read"),
        ("/evaluate", "read"),
        # Anything reaching a model stays on the tight budget, including
        # routes added later and not yet listed above.
        ("/route", "call"),
        ("/route/stream", "call"),
        ("/openai/v1/chat/completions", "call"),
    ],
)
def test_rate_limit_bucket_classification(path, expected):
    assert rate_limit_bucket(path) == expected


def test_no_budget_cap_means_always_under_budget():
    fake_key = ApiKey(id=99991, key="x", name="unlimited", daily_budget_usd=None)
    assert check_budget(fake_key) is True


def test_fresh_key_with_budget_starts_under_budget():
    # no requests logged yet for this key id in the test DB, so spend=0
    fake_key = ApiKey(id=99992, key="y", name="budgeted", daily_budget_usd=5.00)
    assert check_budget(fake_key) is True