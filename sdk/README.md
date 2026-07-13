# routewise (Python SDK)

Thin client for the routewise cost-aware LLM router. No routing logic lives
here -- it's a convenience wrapper around HTTP calls to the real API.

## Install

```bash
pip install routewise
```

## Usage

```python
from routewise import RouteWiseClient

client = RouteWiseClient(api_key="rw_your_key_here")

result = client.ask("What is the capital of France?")
print(result["response"])
print(result["routed_to"], result["cost_usd"])

# Force a specific tier instead of letting the difficulty model decide
result = client.ask("Explain quantum computing", override_tier="frontier")

# Get aggregate usage stats
stats = client.stats()
print(stats["total_requests"], stats["cache_hit_rate"])
```

## Errors

All non-2xx responses raise `RouteWiseError` with the API's error detail
message, e.g. invalid key, rate limit exceeded, empty query.