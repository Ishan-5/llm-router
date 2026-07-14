"""
"ignore all previous instructions" — classic injection opener
"you are now DAN" / "you are now unrestricted" — persona hijacking
"forget your training" / "forget all rules" — training override attempts
"act as an unrestricted AI" / "act as jailbreak" — role-play jailbreaks
"do anything now" — DAN (Do Anything Now) shorthand
"pretend you have no restrictions" — constraint removal
"system prompt" — trying to reference or manipulate the system prompt
"reveal your instructions" — trying to extract the system prompt

"""

import re

_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions",
    r"you\s+are\s+now\s+(dan|jailbreak|unrestricted|evil)",
    r"forget\s+(all\s+)?(previous|prior|your)\s+(instructions|rules|training)",
    r"act\s+as\s+(if\s+you\s+are\s+)?(an?\s+)?(unrestricted|evil|jailbreak|dan)",
    r"do\s+anything\s+now",
    r"pretend\s+(you\s+have\s+no|there\s+are\s+no)\s+(restrictions|rules|limits)",
    r"system\s*prompt",
    r"reveal\s+your\s+(instructions|prompt|system)",
]



_PII_PATTERNS = [
    (r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", "[EMAIL]"),
    (r"\b\d{3}[-.\s]?\d{2}[-.\s]?\d{4}\b", "[SSN]"),
    (r"\b\d{4}[-.\s]?\d{4}[-.\s]?\d{4}[-.\s]?\d{4}\b", "[CARD]"),
    (r"\b(\+\d{1,2}\s?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b", "[PHONE]"),
    (r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", "[IP]"),
]


def is_prompt_injection(query: str) -> bool:
    q = query.lower()
    return any(re.search(p, q) for p in _INJECTION_PATTERNS)


def sanitize_pii(query: str) -> str:
    for pattern, replacement in _PII_PATTERNS:
        query = re.sub(pattern, replacement, query)
    return query
