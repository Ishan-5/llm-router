import sys
import os
import logging
import re

from openai import OpenAI

from router.config import GROQ_LABEL_API_KEY, GROQ_LABEL_MODEL
from router.db import SessionLocal, RequestLog
from router.providers_registry import PROVIDERS_REGISTRY

# Make the ML scoring module importable (same pattern as classifier.py).
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from predict_difficulty import score_to_tier  # noqa: E402

log = logging.getLogger("routewise.difficulty_labeler")

_label_client = None


def _get_client():
    global _label_client
    if _label_client is None:
        _label_client = OpenAI(
            api_key=GROQ_LABEL_API_KEY or "",
            base_url=PROVIDERS_REGISTRY["groq"]["base_url"],
            timeout=30.0,
        )
    return _label_client


# Same rubric used to build the gold training dataset (label_gold_dataset.py),
# so live labels are directly comparable to training labels.
LABEL_PROMPT = """You are scoring queries for an LLM cost-routing system. Score how difficult this query is for an AI model to answer well, on a 0-10 scale.

0-2 = trivial: greetings, single fact lookup, basic conversion, simple extraction, casual short creative/subjective requests with no real effort needed (opinions, one-liners, simple preferences)
3-5 = moderate: requires some explanation, a short reasoning chain, small-to-moderate code, summarizing/analyzing a longer passage, or a creative task with a few explicit constraints
6-8 = hard: multi-step reasoning where steps depend on each other, non-trivial code or system design, comparing/synthesizing multiple sources or ideas, long-form writing with many constraints
9-10 = expert: deep domain expertise required, complex multi-part synthesis, research-level problems

CRITICAL RULE: A query having NO single objectively correct answer (an opinion question, a casual creative request, a personal preference question) does NOT make it hard. Score based on how much actual effort/reasoning/generation work is required, not on whether the answer is subjective. "What makes a good parent?" and "design a logo for a band" are casual, low-effort requests -- score them LOW, not high, even though they're open-ended.

Ignore the LENGTH of the query. A long passage to summarize is not automatically hard; a short but genuinely multi-step or technical question can be hard.

Examples:
"What is the capital of France?" -> 0
"Convert 5 miles to km" -> 1
"What makes a good parent?" -> 2
"How do I decorate my new home?" -> 1
"Generate a unique motto for yourself." -> 2
"Design a logo for a rock-and-roll band." -> 3
"Describe what your ideal pet cat would look like." -> 2
"Summarize this paragraph in 2 sentences: [short paragraph]" -> 2
"Explain how binary search works with an example" -> 3
"Write a Python function to check if a string is a palindrome" -> 4
"Extract all person names and organizations from this news article: [article]" -> 4
"Compare functional vs object-oriented programming and recommend one for a given use case" -> 6
"Design a caching layer for a distributed rate limiter" -> 8
"Debug this race condition in my async code: [code]" -> 8
"Write a 1000-word short story with a twist ending" -> 7

Respond with ONLY a single integer from 0 to 10. No words, no explanation.

Query: {query}

Score:"""


def _parse_score(text: str | None) -> float | None:
    if not text:
        return None
    match = re.search(r"\b([0-9]|10)\b", text.strip())
    if not match:
        return None
    return float(match.group(1))


def label_difficulty(query: str) -> float | None:
    """Ask the LLM for a 0-10 difficulty label of the query. Never raises."""
    if not GROQ_LABEL_API_KEY:
        return None
    if not query or not query.strip():
        return None
    try:
        resp = _get_client().chat.completions.create(
            model=GROQ_LABEL_MODEL,
            max_tokens=5,
            temperature=0,
            messages=[{"role": "user", "content": LABEL_PROMPT.format(query=str(query)[:1000])}],
        )
        return _parse_score(resp.choices[0].message.content)
    except Exception as e:
        log.warning("difficulty labeler failed: %s", e)
        return None


def label_to_tier(score: float) -> str:
    """Map a 0-10 difficulty label to the tier the router would pick at balanced thresholds."""
    tier, _, _ = score_to_tier(score, margin=1.0)
    return tier


def update_difficulty_label(log_id: int, query: str) -> None:
    """Label a logged request with the LLM's difficulty score and persist it.
    Runs in a background thread -- never blocks the request path."""
    if log_id is None:
        return
    label = label_difficulty(query)
    if label is None:
        return
    session = SessionLocal()
    try:
        entry = session.query(RequestLog).filter(RequestLog.id == log_id).first()
        if entry is not None:
            entry.llm_difficulty_score = label
            entry.llm_predicted_tier = label_to_tier(label)
            entry.label_judged = True
            session.commit()
    except Exception as e:
        session.rollback()
        log.warning("could not persist difficulty label for log %s: %s", log_id, e)
    finally:
        session.close()