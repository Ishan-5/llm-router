"""Caller-supplied tags that give spend a shape.

A router that only reports "you spent $4" cannot be acted on. Money needs
names: which team, which feature, which customer. Callers attach them with two
headers, so no request body has to change:

    X-RouteWise-Team:    growth
    X-RouteWise-Feature: onboarding-copy

Both are optional and neither can fail a request. They are normalised to a
small alphabet because they end up in GROUP BY queries and in a report a human
reads, where "Growth ", "growth" and "growth!" must not become three rows.
"""
import re

TEAM_HEADER = "x-routewise-team"
FEATURE_HEADER = "x-routewise-feature"

TAG_MAX_LEN = 64  # long enough for "customer-support-eu", short enough to index

_UNSAFE = re.compile(r"[^a-z0-9.-]+")

EMPTY_TAGS = {"team_id": None, "feature_tag": None}


def clean_tag(value: str | None) -> str | None:
    """Normalise one label, or return None if nothing usable is left.

    Hyphen is the only separator on purpose: "onboarding_copy",
    "Onboarding Copy" and "onboarding-copy" all have to land in one bucket, or
    the report fragments the very spend it is meant to explain.
    """
    if not value:
        return None
    cleaned = _UNSAFE.sub("-", value.strip().lower()).strip("-.")
    return cleaned[:TAG_MAX_LEN] or None


def request_tags(request) -> dict:
    """The two log columns for a request. Never raises, never rejects."""
    headers = getattr(request, "headers", None)
    if headers is None:
        return dict(EMPTY_TAGS)
    return {
        "team_id": clean_tag(headers.get(TEAM_HEADER)),
        "feature_tag": clean_tag(headers.get(FEATURE_HEADER)),
    }
