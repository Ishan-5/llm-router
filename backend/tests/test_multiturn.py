import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from router.multiturn import build_scoring_context, score_with_context
from router.support_policy import get_tier_with_mode
from router.openai_compat import ChatMessage

TIER_ORDER = {"cheap": 0, "mid": 1, "frontier": 2}


def _turns(*pairs):
    return [{"role": role, "content": content} for role, content in pairs]


# --- context construction ---

def test_no_context_without_history():
    msgs = _turns(("user", "now draw it in python"))
    assert build_scoring_context(msgs, "now draw it in python") is None


def test_no_context_for_single_assistant_only():
    assert build_scoring_context([], "hello") is None
    assert build_scoring_context(None, "hello") is None


def test_context_includes_prior_turns_and_newest_last():
    msgs = _turns(
        ("user", "design a multi thread system"),
        ("assistant", "here is a queue based design"),
        ("user", "now draw it in python"),
    )
    ctx = build_scoring_context(msgs, "now draw it in python")
    assert ctx is not None
    assert ctx.startswith("user: design a multi thread system")
    assert "assistant: here is a queue based design" in ctx
    # the scored message must be the final thing in the string
    assert ctx.endswith("user: now draw it in python")


def test_context_accepts_pydantic_chat_messages():
    msgs = [
        ChatMessage(role="user", content="explain kmeans"),
        ChatMessage(role="assistant", content="it clusters points"),
        ChatMessage(role="user", content="now show the code"),
    ]
    ctx = build_scoring_context(msgs, "now show the code")
    assert ctx is not None and ctx.endswith("user: now show the code")


def test_context_window_is_bounded():
    msgs = _turns(*[("user", f"turn {i} " + "x" * 400) for i in range(20)],
                  ("user", "now continue"))
    ctx = build_scoring_context(msgs, "now continue")
    assert ctx is not None
    assert len(ctx) <= 1500
    assert ctx.endswith("user: now continue")


def test_blank_turns_are_dropped():
    msgs = _turns(("user", "   "), ("assistant", ""), ("user", "real question"))
    assert build_scoring_context(msgs, "real question") is None


# --- scoring behaviour ---

def test_no_context_matches_original_single_pass():
    msgs = _turns(("user", "design a multi thread system"), ("user", "thanks"))
    assert build_scoring_context(msgs, "thanks") is not None

    # with context suppressed the new helper must equal the old entry point
    for mode in (None, "3tier", "2tier"):
        a = score_with_context("thanks", margin=1.0, support_mode=mode, context=None)
        b = get_tier_with_mode("thanks", 1.0, support_mode=mode)
        assert a == b, mode


def test_context_never_routes_lower_than_message_alone():
    """The core safety property: multi-turn may escalate, never de-escalate."""
    cases = [
        ("now draw it in python", "design a multi thread system in python and explain the architecture"),
        ("and thanks?", "prove that the halting problem is undecidable"),
        ("why?", "implement a red-black tree with rotations in rust"),
    ]
    for follow_up, prior in cases:
        for mode in (None, "3tier", "2tier"):
            msgs = _turns(("user", prior), ("assistant", "here is a long answer"), ("user", follow_up))
            ctx = build_scoring_context(msgs, follow_up)
            alone = get_tier_with_mode(follow_up, 1.0, support_mode=mode)
            with_ctx = score_with_context(follow_up, margin=1.0, support_mode=mode, context=ctx)
            assert TIER_ORDER[with_ctx[1]] >= TIER_ORDER[alone[1]], (follow_up, mode, alone, with_ctx)
            assert with_ctx[0] >= alone[0], (follow_up, mode, alone, with_ctx)


def test_shape_matches_get_tier_with_mode():
    msgs = _turns(("user", "design a distributed queue"), ("user", "now add retries"))
    ctx = build_scoring_context(msgs, "now add retries")
    out = score_with_context("now add retries", margin=1.0, support_mode=None, context=ctx)
    assert len(out) == 5
    score, tier, cheap_ceil, frontier_floor, mode = out
    assert 0.0 <= score <= 10.0
    assert tier in TIER_ORDER
    assert cheap_ceil < frontier_floor
    assert mode == "generic"


def test_follow_up_can_escalate():
    """Sanity check that context actually moves the needle on a real follow-up."""
    prior = "design a fault tolerant distributed task scheduler with leader election and retries"
    follow_up = "now draw it in python"
    msgs = _turns(("user", prior), ("assistant", "x" * 500), ("user", follow_up))
    ctx = build_scoring_context(msgs, follow_up)
    alone = get_tier_with_mode(follow_up, 1.0, support_mode=None)
    with_ctx = score_with_context(follow_up, margin=1.0, support_mode=None, context=ctx)
    assert with_ctx[0] >= alone[0]
    assert with_ctx[0] > alone[0], f"context should read as harder: {alone} -> {with_ctx}"