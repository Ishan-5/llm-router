"""The answer-style prompt that keeps routed replies readable.

Before this, the router forwarded the raw query with no instructions at all, so
answers came back full of LaTeX the dashboard renders as literal backslashes and
sometimes stopped mid-sentence with no ending. `with_answer_style` adds one
short system turn -- and it must never stomp a caller's own system prompt.
"""
from router.prompts import ANSWER_STYLE_PROMPT, with_answer_style


def test_seeds_a_user_turn_when_messages_are_empty():
    msgs = with_answer_style(None, "what is voltage?")
    assert msgs[0]["role"] == "system"
    assert msgs[1] == {"role": "user", "content": "what is voltage?"}


def test_prepends_style_before_existing_turns():
    history = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    msgs = with_answer_style(history, "hi")
    assert msgs[0]["role"] == "system"
    assert msgs[1:] == history


def test_callers_own_system_prompt_is_respected():
    history = [
        {"role": "system", "content": "You are terse."},
        {"role": "user", "content": "hi"},
    ]
    assert with_answer_style(history, "hi") == history


def test_is_idempotent():
    once = with_answer_style(None, "hi")
    twice = with_answer_style(once, "hi")
    assert twice == once
    assert sum(1 for m in twice if m["role"] == "system") == 1


def test_does_not_mutate_the_input_list():
    history = [{"role": "user", "content": "hi"}]
    with_answer_style(history, "hi")
    assert history == [{"role": "user", "content": "hi"}]


def test_prompt_bans_latex_and_asks_for_a_summary():
    assert "LaTeX" in ANSWER_STYLE_PROMPT
    assert "Markdown" in ANSWER_STYLE_PROMPT
    assert "Key takeaways" in ANSWER_STYLE_PROMPT


def test_prompt_has_no_stray_escape_sequences():
    # A backslash-f, backslash-b or backslash-n in the source would be silently
    # turned into a control character by Python and corrupt what the model reads.
    assert "\\" not in ANSWER_STYLE_PROMPT
