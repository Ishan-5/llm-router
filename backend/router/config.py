import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Default provider used when no user config is set for a tier
DEFAULT_PROVIDER = "groq"

# Pulled from providers_registry -- used for validation in POST /config
from router.providers_registry import PROVIDERS_REGISTRY
SUPPORTED_PROVIDERS = list(PROVIDERS_REGISTRY.keys())


MODEL_CONFIG = {
    "cheap": {
        "model_id": "llama-3.1-8b-instant",
        "price_per_m_input": 0.05,
        "price_per_m_output": 0.08,
    },
    "mid": {
        "model_id": "qwen/qwen3-32b",
        "price_per_m_input": 0.29,
        "price_per_m_output": 0.59,
    },
    "frontier": {
        "model_id": "llama-3.3-70b-versatile",
        "price_per_m_input": 0.59,
        "price_per_m_output": 0.79,
    },
}


TIER_MARGIN = 1.0


# Not a routable tier -- just the backend the "cheap" tier falls back to
# if the local Ollama call fails (not running, model missing, etc.)
OLLAMA_FALLBACK_CONFIG = {
    "model_id": "llama-3.1-8b-instant",
    "price_per_m_input": 0.05,
    "price_per_m_output": 0.08,
}


FALLBACK_CHAIN = {
    "frontier": ["mid", "cheap"],
    "mid": ["cheap"],
    "cheap": [],  # handled internally in providers.py instead -- see OLLAMA_FALLBACK_CONFIG
}


# HONEST NOTE ON PRICING: verify current numbers at ai.google.dev/pricing
# before trusting this for real cost tracking -- I can't confirm live pricing.
# This is a genuinely independent provider (different company, different
# infrastructure than Groq), used as a last resort ONLY if every tier in the
# normal Groq/Ollama chain fails -- e.g. a full Groq outage.
GEMINI_FALLBACK_CONFIG = {
    "model_id": "gemini-1.5-flash",
    "price_per_m_input": 0.075,
    "price_per_m_output": 0.30,
}