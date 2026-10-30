"""Per-key routing defaults.

A key is what a team actually hands to a person or service, so the routing
policy, the tier ceiling and the cache switch belong on the key rather than in
one browser's local storage. The same key then behaves the same from the
dashboard, the SDK and the CLI.

A request may still override any of these; the key only supplies what the
request left unset. The tier ceiling is the exception: it is a governance
control, so a key capped at `cheap` stays cheap even if the caller asks for
frontier. The budget owner already decided not to pay for it.

Kept free of ORM imports so both the route handlers and the tests can use it
without pulling in the database.
"""

POLICIES = ("generic", "2tier", "3tier")
TIERS = ("cheap", "mid", "frontier")
TIER_RANK = {"cheap": 0, "mid": 1, "frontier": 2}


def key_support_mode(api_key, requested: str | None = None) -> str | None:
    """Explicit request wins, then the key's saved policy, then no policy."""
    if requested:
        return requested
    return getattr(api_key, "default_policy", None) or None


def key_threshold(api_key, fallback: float) -> float:
    """The key's sensitivity, or the caller's fallback (user setting)."""
    saved = getattr(api_key, "default_threshold", None)
    return float(saved) if saved is not None else fallback


def key_cache_bypassed(api_key, requested: bool = False) -> bool:
    """True when this call or this key asks for no cache read/write."""
    if requested:
        return True
    return getattr(api_key, "cache_enabled", None) is False


def allowed_tiers(support_mode: str | None) -> list[str]:
    """The tier ladder a policy can actually route to."""
    return ["cheap", "frontier"] if support_mode == "2tier" else list(TIERS)


def available_tiers_for_key(api_key, support_mode: str | None) -> list[str]:
    """The policy's ladder, cut at the key's ceiling. Never empty."""
    ladder = allowed_tiers(support_mode)
    ceiling = getattr(api_key, "max_tier", None)
    if not ceiling:
        return ladder
    capped = [t for t in ladder if TIER_RANK[t] <= TIER_RANK[ceiling]]
    return capped or [ladder[0]]


def clamp_tier_to_key(api_key, tier: str, support_mode: str | None) -> tuple[str, str | None]:
    """Return (tier to use, ceiling that bound) for this key.

    A ceiling that has no matching band under the policy collapses downward:
    `mid` under 2tier means "never frontier", which is cheap.
    """
    ceiling = getattr(api_key, "max_tier", None)
    if not ceiling or tier not in TIER_RANK:
        return tier, None
    ladder = available_tiers_for_key(api_key, support_mode)
    target = ladder[-1]
    if TIER_RANK[tier] > TIER_RANK[target]:
        return target, ceiling
    return tier, None


def cached_tier_allowed(api_key, tier: str, support_mode: str | None) -> bool:
    """False when a cached answer used a tier this key is no longer allowed."""
    final, _ = clamp_tier_to_key(api_key, tier, support_mode)
    return final == tier
