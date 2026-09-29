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

## Pick a model (difficulty policy)

`ask()` accepts a product name that chooses which routing policy to use:

| `model` | Policy | Who it's for |
|---|---|---|
| `emma` | generic | General-purpose routing (default) |
| `lisa` | 3-tier support | Customer support — cheap / mid / frontier |
| `kate` | 2-tier support | Customer support — cheap / frontier only |

```python
# customer support, scored by the support-specific difficulty model
result = client.ask("I want a refund", model="lisa")

# 2-tier support policy — no mid tier
result = client.ask("I was charged twice", model="kate")

# raw policy id wins over the name
result = client.ask("My order is late", support_mode="3tier")

# ask_stream works the same way; the final meta dict includes support_mode
for item in client.ask_stream("Where is my order?", model="lisa"):
    if isinstance(item, str):
        print(item, end="", flush=True)
    else:
        print(f"\n--- {item['tier']} {item['support_mode']} ---")

# the OpenAI-compatible chat path accepts the same names
client.chat([{"role": "user", "content": "Refund please"}], model="kate")

# discover all models + their cuts/evals
client.get_models()
```

## Bring your own model

Override any tier with your own provider and model. Unset tiers fall back to defaults automatically.

```python
# set custom models for any combination of tiers
client.configure(
    cheap={"provider": "openrouter", "model_id": "deepseek/deepseek-v4-flash", "api_key": "sk-or-v1-..."},
    frontier={"provider": "openai", "model_id": "gpt-4o", "api_key": "your-openai-key"},
    # mid not set -- uses default
)

# config is stored in memory and sent with every ask() as a per-request
# BYOM override -- your API keys never touch the router's database.
result = client.ask("Design a distributed rate limiter")
print(result["response"])
```

`configure()` applies the config client-side on every request (works with a plain `rw_` API key — no sign-in needed). `reset()` clears it.

## All methods

```python
# routing
client.ask("query")                          # auto-route by difficulty
client.ask("query", override_tier="frontier") # force a specific tier
client.ask("query", model="lisa")             # use the 3-tier support policy
client.ask("query", user_api_keys={"frontier": "sk-..."})  # per-request key override

# byom config — set one, two, or all three tiers; unset tiers keep defaults
client.configure(cheap={...}, mid={...}, frontier={...})  # set custom models
client.get_config()     # see currently active config (no keys returned)
client.get_models()     # list available models + policies (cuts, tiers, evals)
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
