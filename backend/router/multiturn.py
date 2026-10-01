"""Multi-turn difficulty scoring.

The router has always scored only the newest user message. That is correct for a
standalone query and wrong for a follow-up: "now draw it in python" reads as
trivial on its own, even though answering it means reasoning about the
architecture from several turns earlier.

This module scores the newest message twice -- alone, and together with the
recent turns before it -- and keeps whichever score is higher. Taking the max
means a follow-up can only ever escalate, never de-escalate, so this can fix
misrouting without introducing over-routing on genuinely cheap questions.

Single-turn requests produce no context string and take the original path
unchanged, so unscored behaviour is byte-for-byte what it was.
"""

MAX_CONTEXT_TURNS = 4
MAX_CONTEXT_CHARS = 1500


def _field(message, name):
    """Read a field from either a plain dict or a pydantic ChatMessage."""
    if isinstance(message, dict):
        return message.get(name)
    return getattr(message, name, None)


def build_scoring_context(messages, last_query: str) -> str | None:
    """Build a compact transcript ending in the newest user message.

    Returns None when there is no prior turn to consider, in which case callers
    must score the message alone exactly as they did before.
    """
    if not messages or not last_query:
        return None

    # The newest user message is the one being scored; everything before it is
    # the history that gives a follow-up its meaning.
    idx = None
    for i in range(len(messages) - 1, -1, -1):
        if _field(messages[i], "role") == "user":
            idx = i
            break
    if idx is None or idx == 0:
        return None

    parts = []
    for message in messages[:idx][-MAX_CONTEXT_TURNS:]:
        role = "user" if _field(message, "role") == "user" else "assistant"
        content = (_field(message, "content") or "").strip()
        if content:
            parts.append(f"{role}: {content}")
    if not parts:
        return None

    parts.append(f"user: {last_query}")
    context = "\n".join(parts)
    # Keep the newest turns intact: the tail is what carries the reference.
    if len(context) > MAX_CONTEXT_CHARS:
        context = context[-MAX_CONTEXT_CHARS:]
    return None if context == last_query else context


def score_with_context(
    query: str,
    margin: float = 0.3,
    support_mode: str | None = None,
    context: str | None = None,
) -> tuple:
    """Score a query, using its conversation context when that scores higher.

    Returns the same (score, tier, cheap_ceil, frontier_floor, mode) shape as
    get_tier_with_mode so it is a drop-in for the single-pass callers.
    """
    from router.support_policy import get_tier_with_mode

    if not context or context == query:
        return get_tier_with_mode(query, margin, support_mode=support_mode)

    score, tier, cheap_ceil, frontier_floor, mode = get_tier_with_mode(
        query, margin, support_mode=support_mode
    )
    # Already on the strongest tier: a higher score cannot change the routing,
    # so skip the second scoring pass entirely.
    if tier == "frontier":
        return score, tier, cheap_ceil, frontier_floor, mode

    from router.support_policy import score_query, tier_for_score

    context_score = score_query(context, support_mode)
    if context_score <= score:
        return score, tier, cheap_ceil, frontier_floor, mode

    new_tier, cheap_ceil, frontier_floor = tier_for_score(
        context_score, margin, support_mode
    )
    return context_score, new_tier, cheap_ceil, frontier_floor, mode