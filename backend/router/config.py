import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

GROQ_API_KEY = os.getenv("GROQ_API_KEY")


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


OLLAMA_FALLBACK_CONFIG = {
    "model_id": "llama-3.1-8b-instant",
    "price_per_m_input": 0.05,
    "price_per_m_output": 0.08,
}


FALLBACK_CHAIN = {
    "frontier": ["mid", "cheap"],
    "mid": ["cheap"],
    "cheap": [],  
}