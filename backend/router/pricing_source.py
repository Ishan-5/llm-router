"""Live model pricing, sourced from the public AI Pricing Guru dataset.

The dataset is a daily scrape of provider pricing pages: 236 models across 18
providers, no auth, CORS-open, ~25 KB, refreshed at 04:00 UTC.

Two reasons this is not a straight pass-through:

1. It is a third party. If it is unreachable we still have to answer, so the
   router's own MODEL_CONFIG rates are the fallback and every response says
   which source it used.
2. A handful of records are internally inconsistent -- `claude-haiku-3.5`
   lists cached input at 2x the input rate and output at a tenth of it, which
   is a field-rotation error in the source, not a real price. Those are dropped
   rather than shown, because a calculator that quotes a rotated price is worse
   than one that admits it does not know.

Terms: attribution required. Internal/portfolio use is fine; using it as the
primary source of a commercial pricing-comparison product needs written
permission from info@aipricing.guru.
"""
from __future__ import annotations

import threading
import time
from typing import Any

import requests

PRICING_URL = "https://www.aipricing.guru/api/pricing.json"
ATTRIBUTION = "Pricing data by AI Pricing Guru (aipricing.guru)"

# The dataset refreshes daily; poll well inside that so we never serve stale
# rates for long, and never hammer the endpoint.
CACHE_TTL_SECONDS = 3600
FETCH_TIMEOUT_SECONDS = 8

# Only these providers are chat/completion models we can route to. The dataset
# also carries embedding, rerank, image, audio and video models, which have no
# meaningful output-token rate for a text request.
TEXT_PROVIDERS = {
    "openai", "anthropic", "google", "deepseek", "xai", "mistral",
    "groq", "cohere", "together", "perplexity", "moonshot", "alibaba",
    "minimax", "fireworks", "telnyx", "meta",
}

# The upstream feed lags reality on model availability: it still lists Groq's
# llama-3.1-8b-instant and llama-3.3-70b-versatile as active, but Groq shut
# them down on 2026-08-16 (see backend/scripts/load_test_pricing.sql, and the
# is_active=false rows in model_pricing). Offering them as calculator
# baselines would let a visitor price a projection against a dead model.
# Treat this feed as a PRICE source only, never an availability source.
RETIRED_MODEL_IDS = {
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
    "llama-3.3-70b-specdec",
}

_lock = threading.Lock()
_cache: dict[str, Any] = {"fetched_at": 0.0, "models": None, "source": None}


def _plausible(pricing: dict) -> bool:
    """Reject records whose rates are internally inconsistent.

    Guards the failure mode we actually hit: a source-side field rotation, so
    `outputPerM` holds the cached rate and `cachedInputPerM` holds the output
    rate. A cached read is always cheaper than a fresh one, and generating is
    never cheaper than reading, so both orderings are safe rejection rules.
    """
    pin = pricing.get("inputPerM")
    pout = pricing.get("outputPerM")
    if not isinstance(pin, (int, float)) or not isinstance(pout, (int, float)):
        return False
    if pin < 0 or pout < 0:
        return False
    cached = pricing.get("cachedInputPerM")
    if isinstance(cached, (int, float)) and cached > pin:
        return False
    return True


def _normalize(raw: dict) -> list[dict]:
    """Flatten the dataset into the shape the calculator consumes."""
    out = []
    for m in raw.get("models", []):
        if m.get("status") != "active":
            continue
        if m.get("availability") == "suspended":
            continue
        if m.get("provider") not in TEXT_PROVIDERS:
            continue
        if m["id"] in RETIRED_MODEL_IDS:
            continue
        pricing = m.get("pricing") or {}
        if not _plausible(pricing):
            continue
        # Embedding and rerank models price per token with no generation step.
        # They are not routable targets, so drop the zero-output rows.
        if not pricing.get("outputPerM"):
            continue
        out.append({
            "id": m["id"],
            "name": m.get("name") or m["id"],
            "provider": m["provider"],
            "input_per_m": float(pricing["inputPerM"]),
            "output_per_m": float(pricing["outputPerM"]),
            "cached_input_per_m": (
                float(pricing["cachedInputPerM"])
                if isinstance(pricing.get("cachedInputPerM"), (int, float)) else None
            ),
            "context": m.get("context"),
            "source_url": m.get("sourceUrl"),
        })
    out.sort(key=lambda r: (r["input_per_m"], r["output_per_m"]))
    return out


def _fallback_models() -> list[dict]:
    """The router's own three tiers, so the page still works if the feed is down.

    These are what the live deployment actually bills against, so they are the
    right numbers to fall back to -- not a broader set we cannot route to.
    """
    from router.config import MODEL_CONFIG
    out = []
    for tier, cfg in MODEL_CONFIG.items():
        out.append({
            "id": f"{cfg['provider']}/{cfg['model_id']}",
            "name": cfg["model_id"],
            "provider": cfg["provider"],
            "input_per_m": float(cfg["price_per_m_input"]),
            "output_per_m": float(cfg["price_per_m_output"]),
            "cached_input_per_m": None,
            "context": None,
            "source_url": None,
            "tier": tier,
        })
    return out


def get_models(force: bool = False) -> dict:
    """Return {models, source, last_updated, attribution}.

    Never raises. A fetch failure falls back to the router's own configured
    rates and says so, so the caller can label the numbers honestly.
    """
    now = time.time()
    with _lock:
        fresh = now - _cache["fetched_at"] < CACHE_TTL_SECONDS
        if fresh and _cache["models"] and not force:
            return {
                "models": _cache["models"],
                "source": _cache["source"],
                "last_updated": _cache["fetched_at"],
                "attribution": ATTRIBUTION if _cache["source"] == "aipricing.guru" else None,
            }

        try:
            resp = requests.get(PRICING_URL, timeout=FETCH_TIMEOUT_SECONDS)
            resp.raise_for_status()
            models = _normalize(resp.json())
            if models:
                _cache.update({"fetched_at": now, "models": models, "source": "aipricing.guru"})
                return {
                    "models": models,
                    "source": "aipricing.guru",
                    "last_updated": now,
                    "attribution": ATTRIBUTION,
                }
        except Exception:
            pass

        models = _fallback_models()
        _cache.update({"fetched_at": now, "models": models, "source": "fallback"})
        return {
            "models": models,
            "source": "fallback",
            "last_updated": now,
            "attribution": None,
        }


def find_model(model_id: str) -> dict | None:
    """Look up one model by id, case-insensitively."""
    if not model_id:
        return None
    target = model_id.strip().lower()
    for m in get_models()["models"]:
        if m["id"].lower() == target:
            return m
    return None
