"""
Single source of truth for all supported providers and their known models.
Exposed via GET /providers so the frontend can build dropdowns from this.
Every provider includes a "custom" option for models not in the list.
"""

PROVIDERS_REGISTRY = {
    "groq": {
        "label": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "models": [
            "llama-3.1-8b-instant",
            "llama-3.3-70b-versatile",
            "llama-3.3-70b-specdec",
            "qwen/qwen3-32b",
            "qwen/qwen3.6-27b",
            "meta-llama/llama-4-scout-17b-16e-instruct",
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
            "mixtral-8x7b-32768",
            "gemma2-9b-it",
            "custom",
        ],
    },
    "openai": {
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "models": [
            "gpt-5",
            "gpt-5-mini",
            "gpt-4o",
            "gpt-4o-mini",
            "o1",
            "o1-mini",
            "o3-mini",
            "custom",
        ],
    },
    "anthropic": {
        "label": "Anthropic",
        "base_url": "https://api.anthropic.com/v1",
        "models": [
            "claude-sonnet-5",
            "claude-3-7-sonnet",
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            "claude-3-opus-20240229",
            "custom",
        ],
    },
    "gemini": {
        "label": "Google Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "models": [
            "gemini-3.5-flash",
            "gemini-3.1-pro",
            "gemini-3.1-flash-lite",
            "gemini-2.5-pro",
            "gemini-2.0-flash",
            "gemini-1.5-pro",
            "custom",
        ],
    },
    "deepseek": {
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "models": [
            "deepseek-chat",
            "deepseek-reasoner",
            "deepseek-v3",
            "custom",
        ],
    },
    "perplexity": {
        "label": "Perplexity",
        "base_url": "https://api.perplexity.ai",
        "models": [
            "sonar",
            "sonar-pro",
            "sonar-reasoning",
            "custom",
        ],
    },
    "mistral": {
        "label": "Mistral",
        "base_url": "https://api.mistral.ai/v1",
        "models": [
            "mistral-small-latest",
            "mistral-medium-latest",
            "mistral-large-latest",
            "codestral-latest",
            "pixtral-large",
            "custom",
        ],
    },
    "xai": {
        "label": "xAI",
        "base_url": "https://api.x.ai/v1",
        "models": [
            "grok-4",
            "grok-4-heavy",
            "grok-4-fast",
            "custom",
        ],
    },
    "ollama": {
        "label": "Ollama (local)",
        "base_url": "http://localhost:11434",
        "models": [
            "llama3.3",
            "llama3.2",
            "qwen2.5-coder",
            "phi4",
            "mistral",
            "custom",
        ],
    },
}
