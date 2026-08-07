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



_WEB_PATTERNS = [
    # temporal signals
    r"\btoday\b", r"\bright now\b", r"\bcurrently\b", r"\bcurrent\b",
    r"\blatest\b", r"\blive\b", r"\bbreaking\b", r"\bjust (happened|announced|released)\b",
    r"\bthis (morning|evening|week|month|year)\b",
    r"\byesterday\b", r"\blast (week|month|night)\b",
    r"\bas of (today|now|\d{4})\b",
    # factual lookup signals
    r"\bprice of\b", r"\bstock price\b", r"\bshare price\b",
    r"\bweather\b", r"\bforecast\b",
    r"\bscore\b", r"\bwho won\b", r"\bmatch result\b",
    r"\bnews\b", r"\bheadlines\b",
    r"\bwho is (the )?ceo\b", r"\bwho (leads|runs|heads)\b",
    r"\blatest version\b", r"\bmost recent\b",
    r"\bwhat happened\b", r"\bwhat('s| is) happening\b",
    r"\bis .+ (still|open|closed|available|down|up)\b",
]


def needs_web_search(query: str) -> bool:
    q = query.lower()
    # "current" in an electrical/engineering context is NOT a temporal signal —
    # neutralize it so "design a current-limiting circuit" doesn't trigger web search.
    q = re.sub(
        r"current\s*(?:[-–—]\s*)?(?:limiting|carrying|flow|flowing|flowed|source|density|rating|draw|drain|through|sensor|sensing|voltage|resistor|circuit)",
        "electrical",
        q,
    )
    q = re.sub(r"(?:alternating|direct|electric|electrical|a[.]?c|d[.]?c)\s+current\b", "electrical", q)
    return any(re.search(p, q) for p in _WEB_PATTERNS)


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
