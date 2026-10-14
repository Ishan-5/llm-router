"""Shared prompt fragments for routed answers.

The router used to forward the raw user query with no instructions, so models
returned whatever shape they liked: raw LaTeX that the dashboard and CLI render
as literal backslashes, walls of text with no ending, and answers that stopped
mid-equation when the streaming budget ran out.

A single short style directive fixes the presentation at the source. It is added
as a system message only when the caller did not supply one, so an explicit
system prompt (for example through the OpenAI-compatible endpoint) always wins.
"""

from __future__ import annotations

# Keep this free of backslashes and LaTeX so it reads the same in every log.
ANSWER_STYLE_PROMPT = (
    "Answer clearly and completely, and write for a screen. "
    "Use Markdown for structure: short paragraphs, bullet points, and tables "
    "where they help. Do not use LaTeX or math markup -- no backslash commands "
    "(frac, boxed, begin, aligned), no bracket or dollar delimiters. Write "
    "formulas as plain text, e.g. V = I x R or I = V / R. "
    "Any answer longer than a few lines must finish with a short "
    "'Key takeaways' summary of two to four bullets. Never stop mid-sentence."
)

# Cheap idempotency marker: recognise our own prompt if it is already present.
_MARKER = "Never stop mid-sentence."


def with_answer_style(messages: list[dict] | None, query: str) -> list[dict]:
    """Return ``messages`` with the answer-style system prompt as the first turn.

    * a caller-supplied system message is respected and left untouched;
    * the function is idempotent, so callers that chain (stream -> call) never
      stack the prompt twice;
    * when ``messages`` is empty it seeds a single user turn from ``query``.

    Signatures and dict contents are never mutated: a new list is returned.
    """
    msgs = list(messages) if messages else [{"role": "user", "content": query}]

    if any(
        m.get("role") == "system" and _MARKER in (m.get("content") or "")
        for m in msgs
    ):
        return msgs

    # A caller that supplied its own system prompt owns the behaviour; only add
    # our style rules when nobody has set a system turn.
    if msgs and msgs[0].get("role") == "system":
        return msgs

    return [{"role": "system", "content": ANSWER_STYLE_PROMPT}] + msgs
