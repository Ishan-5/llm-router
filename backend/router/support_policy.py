"""Support-mode difficulty scoring.

The live RouteWise path uses predict_difficulty.score_to_tier and is untouched
by this module. Support mode is opt-in per request: when support_mode is None or
"generic", get_tier() behaves exactly as before. Only when a caller passes
support_mode="2tier" or "3tier" do we load a customer-support policy.

Selecting a support policy costs no extra LLM call and no extra embedding pass.
Both policies reuse the one MiniLM embedder already resident in memory, via
predict_difficulty.get_embedder(), and produce a single score that is mapped to
a tier by the policy's own declared rule.

If a policy is requested but unavailable or invalid, we raise rather than
silently fall back, so a routing decision is never attributed to a model that
did not produce it.
"""

import os
import sys
from pathlib import Path

import numpy as np

# Append src/ for predict_difficulty, following the same path convention
# classifier.py already uses.
_HERE = os.path.dirname(__file__)
sys.path.append(os.path.join(_HERE, "..", "src"))


def _find_support_root() -> Path:
    """Locate the customer-support package regardless of where this file runs.

    The local repo nests this file at <root>/backend/router/ while the Docker
    image flattens backend/ to /app/router, so walk up from this file until the
    sibling customer-support/routing directory is found instead of assuming a
    fixed depth.
    """
    here = Path(_HERE).resolve()
    for parent in here.parents:
        if (parent / "customer-support" / "routing").is_dir():
            return parent
    raise RuntimeError("could not locate customer-support/routing from " + str(here))


sys.path.append(str(_find_support_root() / "customer-support" / "routing"))

from predict_difficulty import get_embedder, score_to_tier  # noqa: E402

import feature_builder as fb  # noqa: E402

GENERIC = "generic"
SUPPORT_MODES = (GENERIC, "2tier", "3tier")

_policy_cache: dict[str, "fb.Policy"] = {}


def _get_policy(policy_id: str) -> "fb.Policy":
    """Cached policy lookup so requests do not re-read the joblib from disk."""
    if policy_id not in _policy_cache:
        _policy_cache[policy_id] = fb.load_policy(policy_id)
    return _policy_cache[policy_id]


def available_support_modes() -> list[str]:
    """Support modes whose artifacts load and validate right now."""
    out = [GENERIC]
    for pid in fb.VALID_POLICIES:
        try:
            _get_policy(pid)
            out.append(pid)
        except Exception:
            continue
    return out


def preload_support_policies() -> list[str]:
    """Warm the policy cache at startup. Returns the modes that loaded."""
    return available_support_modes()


def _score_and_tier(query: str, support_mode: str) -> tuple[float, str, float, float]:
    """Single scoring pass shared by score_support and get_tier_with_mode."""
    policy = _get_policy(support_mode)
    embed = get_embedder().encode([query])
    domain = fb.classify_domain(query)
    features = fb.build_support_features(embed, [query], [domain])
    score = float(policy.predict(features)[0])
    return score, policy.tier_for(score), policy.cheap_ceil, policy.frontier_floor


def score_support(query: str, support_mode: str = "3tier") -> tuple[str, str, float, float]:
    """Score one query under a support policy.

    Returns (tier, support_mode, cheap_ceil, frontier_floor) so callers can use
    it as a drop-in for get_tier's score/tier/cut shape.
    """
    if support_mode == GENERIC:
        raise ValueError("score_support called with generic mode; use get_tier instead")
    tier, mode, cheap_ceil, frontier_floor = _score_and_tier(query, support_mode)
    return tier, mode, cheap_ceil, frontier_floor


def get_tier_with_mode(query: str, margin: float = 0.3, support_mode: str | None = None) -> tuple:
    """Unified entry point used by the route handler.

    Returns (score, tier, cheap_ceil, frontier_floor, mode). For generic mode
    this is exactly get_tier()'s result, so default behaviour is unchanged.
    One support request scores once: no duplicate embed, no second model pass.
    """
    if not support_mode or support_mode == GENERIC:
        score, tier, cheap_ceil, frontier_floor = _generic_get_tier(query, margin)
        return score, tier, cheap_ceil, frontier_floor, GENERIC
    score, tier, cheap_ceil, frontier_floor = _score_and_tier(query, support_mode)
    return score, tier, cheap_ceil, frontier_floor, support_mode


def score_query(query: str, support_mode: str | None = None) -> float:
    """Score a string under the active policy without mapping it to a tier.

    Used by the multi-turn path, which needs a score for the conversation
    transcript and then decides for itself which score to keep.
    """
    if not support_mode or support_mode == GENERIC:
        from predict_difficulty import predict_difficulty
        return float(predict_difficulty(query))

    policy = _get_policy(support_mode)
    embed = get_embedder().encode([query])
    domain = fb.classify_domain(query)
    features = fb.build_support_features(embed, [query], [domain])
    return float(policy.predict(features)[0])


def tier_for_score(score: float, margin: float = 0.3, support_mode: str | None = None) -> tuple[str, float, float]:
    """Map an already-computed score to a tier using the active policy's own cuts."""
    if not support_mode or support_mode == GENERIC:
        from predict_difficulty import score_to_tier
        return score_to_tier(score, margin=margin)

    policy = _get_policy(support_mode)
    return policy.tier_for(score), policy.cheap_ceil, policy.frontier_floor


def _generic_get_tier(query: str, margin: float = 0.3):
    from predict_difficulty import predict_difficulty

    score = predict_difficulty(query)
    tier, cheap_ceil, frontier_floor = score_to_tier(score, margin=margin)
    return score, tier, cheap_ceil, frontier_floor
