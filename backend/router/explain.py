"""Turn a routing decision into a plain-language explanation.

Pure functions: they take an already-computed difficulty score, the policy cuts
and the per-tier pricing, and return a dict. There is no model call and no I/O --
explaining a route costs nothing beyond the score the router already produced.

The live ``/route`` path is untouched; this only ever *describes* a decision.
"""
from __future__ import annotations

# Sensitivity presets, matching predict_difficulty.score_to_tier's margin.
SENSITIVITY = (("economy", 0.0), ("balanced", 1.0), ("quality", 2.0))


def nearest_boundary(score: float, cheap_ceil: float, frontier_floor: float) -> dict:
    """The cut that decided the tier, and how much room the score had above/below it."""
    if score >= frontier_floor:
        return {
            "decided_by": "frontier_floor",
            "value": frontier_floor,
            "distance": round(score - frontier_floor, 3),
            "side": "above",
        }
    if score <= cheap_ceil:
        return {
            "decided_by": "cheap_ceil",
            "value": cheap_ceil,
            "distance": round(cheap_ceil - score, 3),
            "side": "below",
        }
    to_cheap = score - cheap_ceil
    to_frontier = frontier_floor - score
    if to_cheap <= to_frontier:
        return {
            "decided_by": "cheap_ceil",
            "value": cheap_ceil,
            "distance": round(to_cheap, 3),
            "side": "above",
        }
    return {
        "decided_by": "frontier_floor",
        "value": frontier_floor,
        "distance": round(to_frontier, 3),
        "side": "below",
    }


def slider_scenarios(score: float, policy: str | None) -> dict | None:
    """Which tier each sensitivity preset would pick for this score.

    Only meaningful for the generic policy: the support policies use their own
    fixed cuts and ignore the sensitivity margin, so every preset would return
    the same tier. Returning None there is more honest than implying a choice
    the policy does not offer.
    """
    if policy and policy != "generic":
        return None
    from router.support_policy import tier_for_score

    scenarios = {}
    for name, margin in SENSITIVITY:
        tier, cheap_ceil, frontier_floor = tier_for_score(score, margin, None)
        scenarios[name] = {
            "tier": tier,
            "cheap_ceil": cheap_ceil,
            "frontier_floor": frontier_floor,
        }
    return scenarios


def tier_price_table(available_tiers, user_config, chosen_tier) -> list[dict]:
    """Per-tier model and price, with input price relative to the chosen tier.

    Prices are the real per-million-token figures the router itself costs with,
    so the ratio is a like-for-like comparison rather than an invented estimate.
    """
    def price(tier):
        cfg = (user_config or {}).get(tier) or {}
        pin = cfg.get("price_per_m_input")
        pout = cfg.get("price_per_m_output")
        ok = (
            isinstance(pin, (int, float)) and not isinstance(pin, bool)
            and isinstance(pout, (int, float)) and not isinstance(pout, bool)
        )
        return (float(pin), float(pout)) if ok else (None, None)

    chosen_in = price(chosen_tier)[0]
    rows = []
    for tier in available_tiers:
        cfg = (user_config or {}).get(tier) or {}
        pin, pout = price(tier)
        rows.append({
            "tier": tier,
            "model_id": cfg.get("model_id"),
            "provider": cfg.get("provider"),
            "price_per_m_input": pin,
            "price_per_m_output": pout,
            "input_price_vs_chosen": (
                round(pin / chosen_in, 2) if (pin is not None and chosen_in) else None
            ),
            "chosen": tier == chosen_tier,
        })
    return rows


def _why(score: float, tier: str, cheap_ceil: float, frontier_floor: float) -> str:
    if tier == "cheap":
        return f"{score:.2f}/10 — at or below the cheap ceiling ({cheap_ceil:.2f})"
    if tier == "frontier":
        return f"{score:.2f}/10 — at or above the frontier floor ({frontier_floor:.2f})"
    return (
        f"{score:.2f}/10 — between the cheap ceiling ({cheap_ceil:.2f}) "
        f"and the frontier floor ({frontier_floor:.2f})"
    )


def _summary(score, tier, cheap_ceil, frontier_floor, policy, *, override=None,
             predicted_tier=None, multi_turn=False) -> str:
    if override:
        sentence = (
            f"You forced the {override} tier; the model's own choice was "
            f"{predicted_tier} ({_why(score, predicted_tier, cheap_ceil, frontier_floor)})."
        )
    else:
        prefix = f"[{policy} policy] " if policy and policy != "generic" else ""
        sentence = f"{prefix}{_why(score, tier, cheap_ceil, frontier_floor)}, so the {tier} tier answers it."
    if multi_turn:
        sentence += (
            " Conversation history was included: a follow-up is scored with its "
            "transcript too, and the higher of the two scores wins."
        )
    return sentence


def build_explanation(*, query, score, tier, cheap_ceil, frontier_floor, threshold,
                      policy, available_tiers, user_config, context=None,
                      predicted_tier=None, override=None) -> dict:
    """Assemble the explanation payload for one query."""
    predicted_tier = predicted_tier or tier
    return {
        "query": query,
        "difficulty_score": round(score, 3),
        "tier": tier,
        "predicted_tier": predicted_tier,
        "override": override,
        "policy": policy,
        "threshold": threshold,
        "cheap_ceil": cheap_ceil,
        "frontier_floor": frontier_floor,
        "summary": _summary(
            score, tier, cheap_ceil, frontier_floor, policy,
            override=override, predicted_tier=predicted_tier, multi_turn=bool(context),
        ),
        "boundary": nearest_boundary(score, cheap_ceil, frontier_floor),
        "slider": slider_scenarios(score, policy),
        "tiers": tier_price_table(available_tiers, user_config, tier),
        "multi_turn": bool(context),
        "note": "Scored locally by the difficulty model; explaining a route makes no model call.",
    }
