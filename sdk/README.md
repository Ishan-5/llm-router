# routewise (Python SDK)

Thin client for the routewise cost-aware LLM router. No routing logic lives
here -- it's a convenience wrapper around HTTP calls to the real API.

## Install

```bash
pip install routewise
```

## Quick start

```python
from routewise import RouteWiseClient

client = RouteWiseClient(api_key="rw_your_key_here")

result = client.ask("What is the capital of France?")
print(result["response"])
print(result["routed_to"], result["cost_usd"])
```

## Bring your own model

Override any tier with your own provider and model. Unset tiers fall back to defaults automatically.

```python
# set custom models for any combination of tiers
client.configure(
    cheap={"provider": "groq", "model_id": "llama-3.1-8b-instant", "api_key": "your-groq-key"},
    frontier={"provider": "openai", "model_id": "gpt-4o", "api_key": "your-openai-key"},
    # mid not set -- uses default
)

# api keys are stored in memory and sent automatically with every ask()
result = client.ask("Design a distributed rate limiter")
print(result["response"])
```

## All methods

```python
# routing
client.ask("query")                          # auto-route by difficulty
client.ask("query", override_tier="frontier") # force a specific tier
client.ask("query", user_api_keys={"frontier": "sk-..."})  # per-request key override

# byom config
client.configure(cheap={...}, mid={...}, frontier={...})  # set custom models
client.get_config()     # see currently active config (no keys returned)
client.get_providers()  # list all supported providers + models
client.reset()          # revert all tiers to defaults, clears in-memory keys

# stats
client.stats()          # total requests, cost saved, tier distribution, etc.
```

## Supported providers

```python
providers = client.get_providers()
# returns: groq, openai, anthropic, gemini, deepseek, perplexity, mistral, xai, ollama
# each with a list of known models + "custom" option
```

## Errors

| Exception | When |
|---|---|
| `RouteWiseError` | Base class for all errors |
| `ValidationError` | Bad input — empty query, unsupported provider, invalid model (400) |
| `AuthError` | Invalid/missing API key or rate limit hit (401/429) |
| `AllTiersFailedError` | Every provider tier failed, no response returned (503) |

```python
from routewise import RouteWiseClient, ValidationError, AuthError, AllTiersFailedError

try:
    result = client.ask("hello")
except AllTiersFailedError:
    print("all providers down")
except AuthError:
    print("check your api key")
except ValidationError as e:
    print(f"bad request: {e}")
```
