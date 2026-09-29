"""Tests for the customer-support difficulty policies.

Two of these are regression tests for defects that shipped in an earlier
artifact, so they are written to fail loudly if the bugs are reintroduced:

  - the 2-tier artifact used to route the dead (4.0, 4.5) band to "mid",
    making it a 3-tier policy wearing a 2-tier filename;
  - the 3-tier manifest declared "domain3" while carrying 4 domain columns.
"""

import os
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "customer-support", "routing"))
sys.path.insert(0, os.path.join(ROOT, "backend", "router"))
sys.path.insert(0, os.path.join(ROOT, "backend", "src"))

import feature_builder as fb  # noqa: E402


# --------------------------------------------------------------------------
# feature layout
# --------------------------------------------------------------------------


def test_feature_count_is_392():
    assert fb.FEATURE_COUNT == 392


def test_build_features_shape():
    embed = np.zeros((3, fb.EMBED_DIM), dtype=np.float32)
    X = fb.build_support_features(embed, ["a", "b", "c"], ["technical"] * 3)
    assert X.shape == (3, 392)


def test_build_features_rejects_wrong_embed_dim():
    embed = np.zeros((1, 256), dtype=np.float32)
    with pytest.raises(ValueError, match="embed shape"):
        fb.build_support_features(embed, ["a"], ["technical"])


def test_build_features_rejects_unknown_domain():
    embed = np.zeros((1, fb.EMBED_DIM), dtype=np.float32)
    with pytest.raises(ValueError, match="unknown domain"):
        fb.build_support_features(embed, ["a"], ["not_a_domain"])


def test_build_features_rejects_row_count_mismatch():
    embed = np.zeros((2, fb.EMBED_DIM), dtype=np.float32)
    with pytest.raises(ValueError, match="domains"):
        fb.build_support_features(embed, ["a", "b"], ["technical"])


def test_domain_block_is_one_hot_over_four_domains():
    block = fb.domain_block(["technical", "account_access"])
    assert block.shape == (2, 4)
    assert block.sum() == 2.0, "each row must have exactly one active domain"
    assert block[0].tolist() == [0, 0, 0, 1]
    assert block[1].tolist() == [1, 0, 0, 0]


# --------------------------------------------------------------------------
# domain classification
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query,expected",
    [
        ("I forgot my password and cannot log in", "account_access"),
        ("The app crashes with a 500 error", "technical"),
        ("Can I get a refund on my invoice?", "orders_billing"),
        ("How do I track my package delivery?", "delivery_general"),
    ],
)
def test_classify_domain_known_buckets(query, expected):
    assert fb.classify_domain(query) == expected


def test_classify_domain_falls_back_rather_than_all_zeros():
    assert fb.classify_domain("zzzz qqqq") == fb.DOMAIN_FALLBACK
    assert fb.classify_domain("") == fb.DOMAIN_FALLBACK


# --------------------------------------------------------------------------
# artifact manifests load and validate
# --------------------------------------------------------------------------


@pytest.mark.parametrize("pid", ["2tier", "3tier"])
def test_policy_loads(pid):
    p = fb.load_policy(pid)
    assert p.id == pid
    assert p.feature_count == fb.FEATURE_COUNT
    assert len(p.models) == 3


def test_manifest_feature_order_matches_builder():
    """Regression: 3-tier manifest said domain3 while carrying 4 columns."""
    for pid in fb.VALID_POLICIES:
        p = fb.load_policy(pid)
        assert p.domain_order == fb.DOMAIN_ORDER


def test_tier_rule_matches_tier_count():
    p2 = fb.load_policy("2tier")
    p3 = fb.load_policy("3tier")
    assert p2.n_tiers == 2 and p2.tier_rule == fb.TIER2
    assert p3.n_tiers == 3 and p3.tier_rule == fb.TIER3


def test_load_policy_rejects_unknown_id():
    with pytest.raises(ValueError, match="unknown support policy"):
        fb.load_policy("nope")


def test_load_policy_reports_missing_artifact(monkeypatch):
    monkeypatch.setitem(fb.POLICY_FILES, "ghost", "does_not_exist.joblib")
    with pytest.raises(FileNotFoundError):
        fb.load_policy("ghost")


def test_validate_rejects_contradictory_tier_rule():
    """A manifest whose rule and n_tiers disagree must not load."""
    bad = {
        "feature_count": fb.FEATURE_COUNT,
        "feature_order": fb.FEATURE_ORDER,
        "domain_order": list(fb.DOMAIN_ORDER),
        "tier_rule": fb.TIER2,
        "n_tiers": 3,
        "thr": {"cheap_ceil": 4.0},
    }
    with pytest.raises(ValueError, match="contradicts n_tiers"):
        fb._validate(bad, "fake")


def test_validate_rejects_missing_tier_rule():
    bad = {
        "feature_count": fb.FEATURE_COUNT,
        "feature_order": fb.FEATURE_ORDER,
        "domain_order": list(fb.DOMAIN_ORDER),
        "n_tiers": 2,
        "thr": {"cheap_ceil": 4.0},
    }
    with pytest.raises(ValueError, match="unknown tier_rule"):
        fb._validate(bad, "fake")


def test_validate_rejects_feature_drift():
    bad = {
        "feature_count": 388,
        "feature_order": fb.FEATURE_ORDER,
        "domain_order": list(fb.DOMAIN_ORDER),
        "tier_rule": fb.TIER3,
        "n_tiers": 3,
        "thr": {"cheap_ceil": 2.0, "frontier_floor": 4.5},
    }
    with pytest.raises(ValueError, match="drifted"):
        fb._validate(bad, "fake")


def test_validate_rejects_3tier_missing_frontier_floor():
    bad = {
        "feature_count": fb.FEATURE_COUNT,
        "feature_order": fb.FEATURE_ORDER,
        "domain_order": list(fb.DOMAIN_ORDER),
        "tier_rule": fb.TIER3,
        "n_tiers": 3,
        "thr": {"cheap_ceil": 2.0},
    }
    with pytest.raises(ValueError, match="frontier_floor"):
        fb._validate(bad, "fake")


# --------------------------------------------------------------------------
# tier boundaries
# --------------------------------------------------------------------------


def test_2tier_cheap_below_and_at_cut():
    p = fb.load_policy("2tier")
    assert p.tier_for(0.0) == "cheap"
    assert p.tier_for(p.cheap_ceil) == "cheap"


def test_2tier_never_returns_mid():
    """Regression: the dead (4.0, 4.5) band used to return 'mid'."""
    p = fb.load_policy("2tier")
    for s in np.arange(0.0, 10.0, 0.01):
        assert p.tier_for(float(s)) in ("cheap", "frontier")


def test_2tier_above_cut_is_frontier():
    p = fb.load_policy("2tier")
    assert p.tier_for(4.0001) == "frontier"
    assert p.tier_for(4.2) == "frontier"
    assert p.tier_for(9.9) == "frontier"


def test_3tier_boundaries():
    p = fb.load_policy("3tier")
    assert p.tier_for(0.0) == "cheap"
    assert p.tier_for(p.cheap_ceil) == "cheap"
    assert p.tier_for(p.cheap_ceil + 0.0001) == "mid"
    assert p.tier_for(3.0) == "mid"
    assert p.tier_for(p.frontier_floor) == "frontier"
    assert p.tier_for(9.9) == "frontier"


def test_2tier_tiers_property():
    assert fb.load_policy("2tier").tiers == ("cheap", "frontier")
    assert fb.load_policy("3tier").tiers == ("cheap", "mid", "frontier")


# --------------------------------------------------------------------------
# shipped artifact honesty
# --------------------------------------------------------------------------


def test_2tier_artifact_reports_zero_mid_traffic():
    """The artifact's own eval must show no mid traffic, matching its rule."""
    ev = fb.load_policy("2tier").honest_eval
    assert ev["traffic"]["mid"] == 0.0


def test_2tier_sends_more_to_frontier_than_3tier():
    """Dropping the mid band has to move traffic somewhere: onto frontier."""
    t2 = fb.load_policy("2tier").honest_eval["traffic"]
    t3 = fb.load_policy("3tier").honest_eval["traffic"]
    assert t2["frontier"] > t3["frontier"]


def test_2tier_has_better_frontier_recall_than_3tier():
    ev2 = fb.load_policy("2tier").honest_eval
    ev3 = fb.load_policy("3tier").honest_eval
    assert ev2["recall_frontier"] > ev3["recall_frontier"]


# --------------------------------------------------------------------------
# policy manifest for the frontend
# --------------------------------------------------------------------------


def test_manifest_lists_both_policies_as_available():
    ids = {m["id"] for m in fb.policy_manifest() if m.get("available")}
    assert ids == {"2tier", "3tier"}


def test_manifest_marks_unloadable_policy_unavailable(monkeypatch):
    monkeypatch.setitem(fb.POLICY_FILES, "broken", "does_not_exist.joblib")
    entry = next(m for m in fb.policy_manifest() if m["id"] == "broken")
    assert entry["available"] is False
    assert "error" in entry


# --------------------------------------------------------------------------
# // evaluate endpoint now also scores every product (emma/lisa/kate)
# --------------------------------------------------------------------------


def test_evaluate_includes_support_mode_columns(monkeypatch):
    """Regression: /evaluate must expose the per-model tiers so the CLI and
    docs can show what emma/lisa/kate would each pick for the same query."""
    def fake_predict(q):
        return 5.0

    def fake_score_to_tier(score, margin=0.0):
        assert margin in (0.0, 1.0, 2.0)
        if score >= 6.0:
            return "frontier", 4.5, 6.0
        if score >= 4.5:
            return "mid", 4.5, 6.0
        return "cheap", 4.5, 6.0

    def fake_get_tier_with_mode(q, margin=0.3, support_mode="generic"):
        if support_mode == "2tier":
            return 5.0, "frontier", 4.0, 4.0, support_mode
        if support_mode == "3tier":
            return 5.0, "mid", 2.0, 4.5, support_mode
        return 5.0, "mid", 4.5, 6.0, support_mode

    import predict_difficulty as pd_mod
    from router import support_policy as sp_mod
    monkeypatch.setattr(pd_mod, "predict_difficulty", fake_predict)
    monkeypatch.setattr(pd_mod, "score_to_tier", fake_score_to_tier)
    monkeypatch.setattr(sp_mod, "get_tier_with_mode", fake_get_tier_with_mode)

    from fastapi.testclient import TestClient
    from router.main import app
    res = TestClient(app).post("/evaluate", json={"queries": ["refund please"]})
    assert res.status_code == 200
    entry = res.json()["results"][0]
    assert entry["mode_generic"] == "mid"
    assert entry["mode_3tier"] == "mid"
    assert entry["mode_2tier"] == "frontier"
