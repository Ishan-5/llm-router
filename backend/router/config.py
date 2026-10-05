import os
from dotenv import load_dotenv
from router.providers_registry import PROVIDERS_REGISTRY
SUPPORTED_PROVIDERS = list(PROVIDERS_REGISTRY.keys())


load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_JUDGE_API_KEY = os.getenv("GROQ_JUDGE_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
ADMIN_USER_ID = os.getenv("ADMIN_USER_ID", "")
DISABLE_OLLAMA = os.getenv("DISABLE_OLLAMA", "false").lower() == "true"
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:5173,http://localhost:4173"
).split(",")

# Multi-key support: comma-separated keys per tier for load balancing
GROQ_KEYS_CHEAP = os.getenv("GROQ_KEYS_CHEAP", "")
GROQ_KEYS_MID = os.getenv("GROQ_KEYS_MID", "")
GROQ_KEYS_FRONTIER = os.getenv("GROQ_KEYS_FRONTIER", "")

# Initialize load balancer with multi-key config
from router.load_balancer import init_load_balancer
init_load_balancer(GROQ_KEYS_CHEAP, GROQ_KEYS_MID, GROQ_KEYS_FRONTIER)

# Default provider used when no user config is set for a tier
DEFAULT_PROVIDER = "groq"

# Tier prices MUST ascend cheap < mid < frontier. They previously did not:
# deepseek-chat sat in "cheap" at $0.28/$1.10 while gpt-oss-120b sat in
# "frontier" at $0.15/$0.60, so every downroute to cheap cost 1.84x MORE than
# calling frontier and the savings claims inverted. deepseek-chat is the most
# expensive of these three, so it belongs on the top rung.
# Per-request cost @ 1,000 in / 300 out (the assumption every public cost
# figure on the site is quoted at -- see frontend/src/productMetrics.js):
#   cheap    gpt-oss-20b       $0.000165   (1.0x)
#   mid      gpt-oss-120b      $0.000330   (2.0x)
#   frontier deepseek-chat     $0.000600   (3.6x)
MODEL_CONFIG = {
    "cheap": {
        "provider": "groq",
        "model_id": "openai/gpt-oss-20b",
        "price_per_m_input": 0.075,
        "price_per_m_output": 0.30,
    },
    "mid": {
        "provider": "groq",
        "model_id": "openai/gpt-oss-120b",
        "price_per_m_input": 0.15,
        "price_per_m_output": 0.60,
    },
    "frontier": {
        "provider": "openrouter",
        "model_id": "deepseek/deepseek-chat",
        "price_per_m_input": 0.27,
        "price_per_m_output": 1.10,
    },
}


TIER_MARGIN = 1.0

# Fallback configuration for the 'cheap' tier in case the local Ollama instance fails.
OLLAMA_FALLBACK_CONFIG = {
    "model_id": "openai/gpt-oss-20b",
    "price_per_m_input": 0.075,
    "price_per_m_output": 0.30,
}


FALLBACK_CHAIN = {
    "frontier": ["mid", "cheap"],
    "mid": ["cheap"],
    "cheap": [],  # handled internally in providers.py instead -- see OLLAMA_FALLBACK_CONFIG
}


# Last-resort fallback if the entire Groq/Ollama chain fails.
GEMINI_FALLBACK_CONFIG = {
    "model_id": "gemini-3.6-flash",
    "price_per_m_input": 0.10,
    "price_per_m_output": 0.40,
}

# LLM-as-judge: scores answer quality in the background. Uses its own Groq key.
GROQ_JUDGE_MODEL = "openai/gpt-oss-120b"

# LLM-as-labeler: scores query difficulty (0-10) in the background as ground-truth
# labels for the ML difficulty classifier. Falls back to the quality-judge key/model.
GROQ_LABEL_API_KEY = os.getenv("GROQ_LABEL_API_KEY") or GROQ_JUDGE_API_KEY
GROQ_LABEL_MODEL = os.getenv("GROQ_LABEL_MODEL", "openai/gpt-oss-120b")