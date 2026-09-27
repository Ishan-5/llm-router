"""Savings projection for a visitor's own workload.

Answers "if I sent my traffic through this router, what would I save?" using
only the caller's inputs: their volume, their token counts, and the model they
consider frontier. It reads nothing from request_logs, so it can never inherit
the aggregate numbers shown on the public stats page.

The tier mix comes from either:

  - `queries`, scored by the real classifier, or
  - an explicit `tier_mix` the caller asserts themselves.

Both paths produce the same arithmetic. Responses carry `is_estimate` because
that is what every number here is: arithmetic on a sample or an assumption,
extrapolated. Only real routed traffic replaces an estimate with a measurement.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from router.config import MODEL_CONFIG
from router.pricing_source import get_models, find_model

router = APIRouter()

# One scored batch, per request. Each query costs a real embedding plus a
# forward pass, so an unbounded list here is a free compute endpoint.
MAX_SCORED_QUERIES = 50

# The router's own tiers are the default target set. A visitor can override any
# of them with any model from the live price list.
DEFAULT_TIER_MODELS = {
    tier: f"{cfg['provider']}/{cfg['model_id']}" for tier, cfg in MODEL_CONFIG.items()
}


# The mode names the UI shows, mapped to the numeric margin score_to_tier wants:
# 0.0 economy / 1.0 balanced (the app default) / 2.0 quality.
MODE_MARGINS = {"economy": 0.0, "balanced": 1.0, "quality": 2.0}


class ProjectRequest(BaseModel):
    requests_per_month: int = Field(..., gt=0, le=100_000_000)
    input_tokens: int = Field(..., ge=0, le=10_000_000)
    output_tokens: int = Field(..., ge=0, le=10_000_000)
    queries: list[str] | None = Field(default=None, max_length=MAX_SCORED_QUERIES)
    tier_mix: dict[str, float] | None = None
    tier_models: dict[str, str] | None = None
    mode: str = "balanced"

    @field_validator("mode")
    @classmethod
    def _known_mode(cls, v: str) -> str:
        if v not in MODE_MARGINS:
            raise ValueError(f"mode must be one of {sorted(MODE_MARGINS)}")
        return v


class CatalogResponse(BaseModel):
    models: list[dict]
    source: str
    attribution: str | None
    count: int


@router.get("/catalog", response_model=CatalogResponse)
def catalog():
    """Live per-model prices, for the picker. Falls back to our own tiers."""
    data = get_models()
    return {
        "models": data["models"],
        "source": data["source"],
        "attribution": data["attribution"],
        "count": len(data["models"]),
    }


@router.get("/tiers")
def tiers():
    """The tier ladder this router will actually use, resolved the same way /route resolves it.

    The landing page used to hardcode these prices, which is how cheap and
    frontier ended up mislabelled for a while after a re-tier: the page kept
    asserting numbers that no longer matched the running config. Anything that
    quotes our own pricing must read it from here instead.

    Uncached and unauthenticated on purpose - it is three rows of config, it
    must never be able to fail, and it must never be able to be stale.
    """
    from router.model_config_loader import get_active_config

    out = []
    for tier in ("cheap", "mid", "frontier"):
        cfg = get_active_config()[tier]
        out.append({
            "tier": tier,
            "provider": cfg["provider"],
            "model_id": cfg["model_id"],
            "input_per_m": cfg["price_per_m_input"],
            "output_per_m": cfg["price_per_m_output"],
        })
    return {"tiers": out}


def _tier_mix_from_queries(queries: list[str], mode: str) -> tuple[dict[str, float], list[dict]]:
    """Score real prompts and count which tier each lands in."""
    from predict_difficulty import predict_difficulty, score_to_tier
    margin = MODE_MARGINS.get(mode, 1.0)
    counts = {"cheap": 0, "mid": 0, "frontier": 0}
    detail = []
    for q in queries:
        score = predict_difficulty(q)
        tier = score_to_tier(score, margin=margin)[0]
        counts[tier] += 1
        detail.append({"query": q[:120], "difficulty_score": round(score, 3), "tier": tier})
    total = len(queries)
    return {k: v / total for k, v in counts.items()}, detail


def _tier_mix_from_input(mix: dict[str, float]) -> dict[str, float]:
    clean = {k: max(0.0, float(v)) for k, v in (mix or {}).items() if k in ("cheap", "mid", "frontier")}
    total = sum(clean.values())
    if total <= 0:
        raise HTTPException(400, "tier_mix must contain at least one positive share")
    return {k: v / total for k, v in clean.items()}


def _resolve_tier_prices(tier_models: dict[str, str] | None) -> tuple[dict[str, dict], list[str]]:
    """Map each tier to a price row, preferring the live catalog."""
    catalog = {m["id"].lower(): m for m in get_models()["models"]}
    out = {}
    missing = []
    for tier in ("cheap", "mid", "frontier"):
        wanted = (tier_models or {}).get(tier) or DEFAULT_TIER_MODELS[tier]
        row = catalog.get(wanted.strip().lower())
        if row is None:
            row = find_model(wanted)
        if row is None:
            # Fall back to our own configured rate for this tier so the whole
            # projection still resolves rather than erroring on one bad pick.
            cfg = MODEL_CONFIG[tier]
            row = {
                "id": f"{cfg['provider']}/{cfg['model_id']}",
                "name": cfg["model_id"],
                "input_per_m": float(cfg["price_per_m_input"]),
                "output_per_m": float(cfg["price_per_m_output"]),
            }
            missing.append(tier)
        out[tier] = row
    return out, missing


@router.post("/project")
def project(req: ProjectRequest):
    """Project monthly cost and savings for the caller's own workload."""
    if not (req.input_tokens or req.output_tokens):
        raise HTTPException(400, "input_tokens and output_tokens cannot both be zero")

    if req.queries:
        mix, detail = _tier_mix_from_queries(req.queries, req.mode)
        mix_source = "scored"
    else:
        mix = _tier_mix_from_input(req.tier_mix or {})
        detail = []
        mix_source = "asserted"

    prices, missing = _resolve_tier_prices(req.tier_models)
    frontier = prices["frontier"]

    per_request = {}
    routed_total = 0.0
    for tier, share in mix.items():
        if share <= 0:
            continue
        row = prices[tier]
        cost = (
            req.input_tokens / 1_000_000 * row["input_per_m"]
            + req.output_tokens / 1_000_000 * row["output_per_m"]
        )
        per_request[tier] = {
            "share_pct": round(share * 100, 1),
            "model": row["id"],
            "name": row.get("name"),
            "cost_per_request": cost,
        }
        routed_total += share * cost

    baseline = (
        req.input_tokens / 1_000_000 * frontier["input_per_m"]
        + req.output_tokens / 1_000_000 * frontier["output_per_m"]
    )
    saved_per_request = baseline - routed_total
    monthly_saved = saved_per_request * req.requests_per_month

    return {
        "is_estimate": True,
        "mix_source": mix_source,
        "scored_queries": len(req.queries or []),
        "inputs": {
            "requests_per_month": req.requests_per_month,
            "input_tokens": req.input_tokens,
            "output_tokens": req.output_tokens,
            "mode": req.mode,
        },
        "tier_mix": {k: round(v * 100, 1) for k, v in mix.items()},
        "tiers": per_request,
        "baseline_model": frontier["id"],
        "baseline_name": frontier.get("name"),
        "cost_per_request_baseline": baseline,
        "cost_per_request_routed": routed_total,
        "monthly_cost_baseline": baseline * req.requests_per_month,
        "monthly_cost_routed": routed_total * req.requests_per_month,
        "monthly_saved": monthly_saved,
        "yearly_saved": monthly_saved * 12,
        "daily_saved": monthly_saved / 30.0,
        "savings_pct": round(saved_per_request / baseline * 100, 1) if baseline > 0 else 0.0,
        "cheapest_tier": min(per_request, key=lambda t: per_request[t]["cost_per_request"]) if per_request else None,
        "unpriced_tiers_fell_back": missing,
        "scored_detail": detail[:25],
        "caveat": (
            "Projection from your inputs, not a measurement. Only real routed "
            "traffic turns an estimate into a verified saving."
        ),
    }
