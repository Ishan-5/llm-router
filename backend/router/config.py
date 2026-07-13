import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


MODEL_CONFIG = {
    "cheap": {
        "model_id": "llama-3.1-8b-instant",
        "price_per_m_input": 0.05,
        "price_per_m_output": 0.08,
    },
    "mid": {
        "model_id": "llama-3.3-70b-versatile",
        "price_per_m_input": 0.59,
        "price_per_m_output": 0.79,
    },
    "frontier": {
        "model_id": "deepseek-r1-distill-llama-70b",
        "price_per_m_input": 0.75,
        "price_per_m_output": 0.99,
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