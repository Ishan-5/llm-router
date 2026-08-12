import logging
import re

from openai import OpenAI

from router.config import GROQ_JUDGE_API_KEY, GROQ_JUDGE_MODEL
from router.db import SessionLocal, RequestLog
from router.providers_registry import PROVIDERS_REGISTRY

log = logging.getLogger("routewise.quality_judge")

_judge_client = None


def _get_client():
    global _judge_client
    if _judge_client is None:
        _judge_client = OpenAI(
            api_key=GROQ_JUDGE_API_KEY or "",
            base_url=PROVIDERS_REGISTRY["groq"]["base_url"],
            timeout=30.0,
        )
    return _judge_client


JUDGE_SYSTEM_PROMPT = (
    "You are an impartial quality evaluator for an LLM routing service. "
    "Given a user query, the model tier that answered it, and the assistant's response, "
    "score how well the response answers the query on a scale of 1 to 10.\n"
    "Guidelines:\n"
    "  - 10: complete, correct, well-structured answer directly addressing the query.\n"
    "  - 7-9: correct and helpful with minor omissions or verbosity.\n"
    "  - 4-6: partially addresses the query, some errors or important gaps.\n"
    "  - 1-3: mostly wrong, off-topic, refuses unnecessarily, or fails to answer.\n"
    "Penalize refusals and hallucinated facts. Reward conciseness and correctness.\n"
    "Respond with ONLY a single integer between 1 and 10. No explanations, no formatting."
)


def _parse_score(text: str | None) -> float | None:
    if not text:
        return None
    match = re.search(r"\b(10|[1-9])\b", text.strip())
    if not match:
        return None
    return float(match.group(1))


def judge_quality(query: str, response: str, tier: str, model_id: str | None) -> float | None:
    """Score a single response 0-1 via the Groq judge model. Never raises."""
    if not GROQ_JUDGE_API_KEY:
        return None
    if not response or not response.strip():
        return 0.0
    try:
        user_prompt = (
            f"User query:\n{query[:1000]}\n\n"
            f"Answered by: {tier} tier ({model_id or 'unknown model'})\n\n"
            f"Assistant response:\n{response[:6000]}"
        )
        resp = _get_client().chat.completions.create(
            model=GROQ_JUDGE_MODEL,
            max_tokens=16,
            temperature=0,
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        score = _parse_score(resp.choices[0].message.content)
        if score is None:
            return None
        return round(score / 10.0, 4)
    except Exception as e:
        log.warning("quality judge failed: %s", e)
        return None


def update_quality_score(log_id: int, query: str, response: str, tier: str, model_id: str | None) -> None:
    """Judge a logged request and persist the score. Runs in a background thread."""
    if log_id is None:
        return
    score = judge_quality(query, response, tier, model_id)
    if score is None:
        return
    session = SessionLocal()
    try:
        entry = session.query(RequestLog).filter(RequestLog.id == log_id).first()
        if entry is not None:
            entry.quality_score = score
            entry.quality_judged = True
            session.commit()
    except Exception as e:
        session.rollback()
        log.warning("could not persist judge score for log %s: %s", log_id, e)
    finally:
        session.close()
