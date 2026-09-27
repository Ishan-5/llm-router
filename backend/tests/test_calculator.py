"""Tests for the savings projection and the live price feed.

The projection is what a stranger trusts instead of the public dashboard, so
these pin the two things that would make it lie: arithmetic that disagrees with
itself, and a price row that fails a basic sanity check.
"""
from fastapi.testclient import TestClient
from router.main import app
from router.pricing_source import _plausible, _normalize
from router.config import MODEL_CONFIG
from router.providers_registry import PROVIDERS_REGISTRY
from router.db import ModelPricing, SessionLocal

client = TestClient(app)


# ---------------------------------------------------------------------------
# Sanity filter on the upstream feed
# ---------------------------------------------------------------------------

def test_rejects_rotated_pricing_block():
    """claude-haiku-3.5 ships cached > input and output < input. Both are impossible.

    A cached read is always cheaper than a fresh one, and generation is never
    cheaper than reading. If either flips, the record is field-rotated upstream
    and quoting it would produce a confidently wrong number.
    """
    assert not _plausible({"inputPerM": 0.8, "outputPerM": 0.08, "cachedInputPerM": 1.6})
    assert not _plausible({"inputPerM": 15, "outputPerM": 1.5, "cachedInputPerM": 30})


def test_accepts_normal_pricing():
    assert _plausible({"inputPerM": 3, "outputPerM": 15, "cachedInputPerM": 0.3})
    assert _plausible({"inputPerM": 0.15, "outputPerM": 0.6})
    assert _plausible({"inputPerM": 5, "outputPerM": 25, "cachedInputPerM": None})


def test_normalize_drops_inconsistent_and_unroutable():
    raw = {"models": [
        {"id": "good", "status": "active", "provider": "openai",
         "pricing": {"inputPerM": 2, "outputPerM": 10}},
        {"id": "rotated", "status": "active", "provider": "anthropic",
         "pricing": {"inputPerM": 0.8, "outputPerM": 0.08, "cachedInputPerM": 1.6}},
        {"id": "legacy", "status": "legacy", "provider": "openai",
         "pricing": {"inputPerM": 2, "outputPerM": 10}},
        {"id": "embedder", "status": "active", "provider": "cohere",
         "pricing": {"inputPerM": 0.1, "outputPerM": 0}},
        {"id": "suspended", "status": "active", "availability": "suspended", "provider": "openai",
         "pricing": {"inputPerM": 2, "outputPerM": 10}},
    ]}
    ids = {m["id"] for m in _normalize(raw)}
    assert ids == {"good"}


# ---------------------------------------------------------------------------
# /project
# ---------------------------------------------------------------------------

def _project(**overrides):
    body = {
        "requests_per_month": 3000,
        "input_tokens": 500,
        "output_tokens": 500,
        "tier_mix": {"cheap": 0.5, "mid": 0.3, "frontier": 0.2},
    }
    body.update(overrides)
    res = client.post("/project", json=body)
    assert res.status_code == 200, res.text
    return res.json()


def test_projection_is_always_labelled_an_estimate():
    """Never let this be read as a measurement."""
    assert _project()["is_estimate"] is True
    assert "estimate" in _project()["caveat"].lower()


def test_blended_cost_is_the_share_weighted_sum_of_tiers():
    d = _project()
    blended = sum(t["share_pct"] / 100 * t["cost_per_request"] for t in d["tiers"].values())
    assert abs(d["cost_per_request_routed"] - blended) < 1e-9


def test_savings_dollar_and_percent_share_one_baseline():
    """The regression that mattered on /stats: a $ figure and a % that disagree."""
    d = _project()
    implied = d["monthly_cost_baseline"] * d["savings_pct"] / 100
    assert abs(implied - d["monthly_saved"]) < 0.01


def test_all_frontier_mix_saves_exactly_nothing():
    d = _project(tier_mix={"cheap": 0, "mid": 0, "frontier": 1})
    assert d["savings_pct"] == 0.0
    assert d["monthly_saved"] == 0.0


def test_all_cheap_can_cost_more_than_frontier():
    """Not a rounding artifact.

    When the cheap rung is priced above the baseline (which was the shipped
    default before the ladder was un-inverted), the endpoint must report the
    loss honestly rather than clamping the number to zero.

    The inversion is now forced explicitly through tier_models so this keeps
    testing the arithmetic, not the current default config.
    """
    d = _project(
        tier_mix={"cheap": 1, "mid": 0, "frontier": 0},
        # Force the inversion explicitly: price the "cheap" rung at the most
        # expensive model in the catalog and set the baseline to the cheapest.
        tier_models={
            "cheap": "gpt-6-astra",
            "frontier": "ministral-3b",
        },
    )
    assert d["savings_pct"] < 0
    assert d["monthly_saved"] < 0


def test_default_ladder_now_saves_money_on_cheap():
    """After the un-inversion, the shipped defaults must produce positive savings."""
    d = _project(tier_mix={"cheap": 1, "mid": 0, "frontier": 0})
    assert d["savings_pct"] > 0, (
        f"default cheap tier is not cheaper than the default baseline "
        f"({d['savings_pct']}%) - the ladder inverted again"
    )


def test_negative_shares_are_normalised_not_subtracted():
    d = _project(tier_mix={"cheap": 1, "mid": -0.5, "frontier": 0.5})
    assert abs(sum(d["tier_mix"].values()) - 100.0) < 0.11


def test_zero_token_workload_is_rejected():
    res = client.post("/project", json={
        "requests_per_month": 100, "input_tokens": 0, "output_tokens": 0,
        "tier_mix": {"cheap": 1},
    })
    assert res.status_code == 400


def test_empty_mix_is_rejected():
    res = client.post("/project", json={
        "requests_per_month": 100, "input_tokens": 500, "output_tokens": 500,
        "tier_mix": {"cheap": 0, "mid": 0, "frontier": 0},
    })
    assert res.status_code == 400


def test_projection_does_not_read_request_logs():
    """A stranger's projection must be independent of the public dashboard."""
    d = _project()
    assert "request_logs" not in str(d).lower()
    assert d["mix_source"] == "asserted"


# ---------------------------------------------------------------------------
# mode -> margin mapping
# ---------------------------------------------------------------------------

def test_unknown_mode_is_rejected():
    """The mode name has to reach score_to_tier as a float margin.

    Passing the string through made score_to_tier try to multiply a str, which
    only surfaces on the scored path at request time.
    """
    res = client.post("/project", json={
        "requests_per_month": 100, "input_tokens": 500, "output_tokens": 500,
        "queries": ["hello"], "mode": "turbo",
    })
    assert res.status_code == 422


def test_scored_path_returns_a_mix_summing_to_100():
    d = _project(
        queries=["What is the capital of France?", "Fix this typo in my function name"],
        mode="balanced",
    )
    assert d["mix_source"] == "scored"
    assert d["scored_queries"] == 2
    assert abs(sum(d["tier_mix"].values()) - 100.0) < 0.11


def test_quality_mode_downroutes_less_than_economy():
    """A wider frontier threshold must not increase the cheap share."""
    def cheap_share(mode):
        d = _project(queries=[
            "Explain how a B-tree index works and when to use it over a hash index.",
            "Write a function to reverse a linked list in place.",
        ], mode=mode)
        return d["tier_mix"].get("cheap", 0.0)

    assert cheap_share("quality") <= cheap_share("economy")


# ---------------------------------------------------------------------------
# /catalog and the evaluate cap
# ---------------------------------------------------------------------------

def test_catalog_always_returns_something():
    d = client.get("/catalog").json()
    assert d["count"] == len(d["models"]) > 0
    assert d["source"] in ("aipricing.guru", "fallback")


def test_catalog_rows_are_sorted_and_usable():
    rows = client.get("/catalog").json()["models"]
    prices = [r["input_per_m"] for r in rows]
    assert prices == sorted(prices)
    assert all(r["output_per_m"] > 0 for r in rows)


def test_evaluate_caps_batch_size():
    """Unauthenticated, and each query costs a real forward pass."""
    res = client.post("/evaluate", json={"queries": ["hi"] * 51})
    assert res.status_code == 422


def test_default_tier_ladder_is_ordered():
    """cheap < mid < frontier, or the whole savings premise inverts.

    Regression guard: deepseek-chat once sat in "cheap" at $0.28/$1.10 while
    gpt-oss-120b sat in "frontier" at $0.15/$0.60, so downrouting cost 1.84x
    MORE than calling frontier and every savings claim came out negative.
    """
    def per_request(cfg, i=500, o=500):
        return (cfg["price_per_m_input"] * i + cfg["price_per_m_output"] * o) / 1_000_000

    cheap = per_request(MODEL_CONFIG["cheap"])
    mid = per_request(MODEL_CONFIG["mid"])
    frontier = per_request(MODEL_CONFIG["frontier"])
    assert cheap < mid, f"cheap ({cheap:.7f}) must be cheaper than mid ({mid:.7f})"
    assert mid < frontier, f"mid ({mid:.7f}) must be cheaper than frontier ({frontier:.7f})"


def test_default_tiers_are_routable():
    """Every default tier must be in its provider's declared model list.

    _resolve_key() only returns a key for groq/openrouter/gemini, and a model
    absent from PROVIDERS_REGISTRY is only reachable through the "custom"
    escape hatch, so a typo here fails silently at request time.
    """
    for tier, cfg in MODEL_CONFIG.items():
        provider = cfg["provider"]
        assert provider in PROVIDERS_REGISTRY, f"{tier}: unknown provider {provider}"
        assert cfg["model_id"] in PROVIDERS_REGISTRY[provider]["models"], (
            f"{tier}: {cfg['model_id']!r} not in {provider!r} model list"
        )


def test_default_tiers_are_not_retired_models():
    """Guard against the AI Pricing Guru feed resurrecting decommissioned models.

    It still lists groq llama-3.1-8b-instant / llama-3.3-70b-versatile as
    active, but Groq shut them down on 2026-08-16 (see
    backend/scripts/load_test_pricing.sql). Availability there is not reliable;
    treat the feed as a price source only.
    """
    session = SessionLocal()
    try:
        for tier, cfg in MODEL_CONFIG.items():
            row = (
                session.query(ModelPricing)
                .filter(
                    ModelPricing.provider == cfg["provider"],
                    ModelPricing.model_id == cfg["model_id"],
                )
                .first()
            )
            if row is not None:
                assert row.is_active, (
                    f"{tier}: {cfg['model_id']!r} is marked retired in model_pricing"
                )
    finally:
        session.close()


def test_retired_models_are_excluded_from_the_public_catalog():
    """The feed still lists Groq's dead llama models as active.

    A visitor must not be able to pick one as their savings baseline, so the
    blocklist has to be applied on the normalize path (not just the defaults).
    """
    retired = {"llama-3.1-8b-instant", "llama-3.3-70b-versatile"}
    raw = {
        "models": [
            {
                "id": mid, "name": mid, "provider": "groq", "status": "active",
                "pricing": {"inputPerM": 0.05, "outputPerM": 0.08},
            }
            for mid in sorted(retired)
        ]
    }
    assert _normalize(raw) == [], "retired models leaked into the catalog"


def test_live_models_still_pass_normalize():
    """Guard the blocklist against over-blocking."""
    raw = {
        "models": [{
            "id": "ministral-3b", "name": "Ministral 3B", "provider": "mistral",
            "status": "active",
            "pricing": {"inputPerM": 0.1, "outputPerM": 0.1},
        }]
    }
    out = _normalize(raw)
    assert len(out) == 1 and out[0]["id"] == "ministral-3b"
