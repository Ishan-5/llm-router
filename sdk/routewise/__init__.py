"""
routewise -- Python client for the routewise LLM router.
Wraps HTTP calls to /route, /route/stream, /v1/chat/completions, and management endpoints.
"""
import json
import requests
from typing import Optional

DEFAULT_BASE_URL = "https://llm-router-d2b2.onrender.com"

# Friendly product names → backend support_mode. "emma" is the generic router
# (the default), "lisa" is the 3-tier customer-support policy, "kate" is the
# 2-tier customer-support policy.
MODELS = {
    "emma": None,      # generic — regular difficulty routing
    "lisa": "3tier",   # support · cheap / mid / frontier
    "kate": "2tier",   # support · cheap / frontier only
}


class _ModelMapping:
    """Validates the product names accepted by ask()/ask_stream()."""

    @staticmethod
    def resolve(model: str | None, support_mode: str | None) -> str | None:
        if support_mode:
            if support_mode not in ("generic", "2tier", "3tier"):
                raise ValidationError(f"[400] support_mode must be one of generic, 2tier, 3tier")
            return None if support_mode == "generic" else support_mode
        if model:
            key = model.strip().lower()
            if key not in MODELS:
                raise ValidationError(f"[400] model must be one of {', '.join(MODELS)}")
            return MODELS[key]
        return None


class RouteWiseError(Exception):
    """Raised when the API returns a non-2xx response."""
    pass


class ValidationError(RouteWiseError):
    """Raised when the API rejects the request due to invalid input (400)."""
    pass


class AuthError(RouteWiseError):
    """Raised when the API key is missing, invalid, or rate-limited (401/429)."""
    pass


class AllTiersFailedError(RouteWiseError):
    """Raised when every provider tier failed and no response could be returned (503)."""
    pass


def _raise_for_status(response: requests.Response):
    if response.ok:
        return
    try:
        detail = response.json().get("detail", response.text)
    except Exception:
        detail = response.text

    if response.status_code == 400:
        raise ValidationError(f"[400] {detail}")
    elif response.status_code in (401, 403):
        raise AuthError(f"[{response.status_code}] {detail}")
    elif response.status_code == 429:
        raise AuthError(f"[429] {detail}")
    elif response.status_code == 503:
        raise AllTiersFailedError(f"[503] {detail}")
    else:
        raise RouteWiseError(f"[{response.status_code}] {detail}")


class RouteWiseClient:
    def __init__(self, api_key: str, base_url: str = DEFAULT_BASE_URL, timeout: int = 30):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._byom_config: dict = {}

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"}

    def _apply_byom(self, payload: dict, user_api_keys: dict | None = None):
        """Merge in-memory BYOM config (set via configure()) into a request payload.
        byom_config carries provider + model per tier; user_api_keys carries the keys."""
        if self._byom_config:
            payload["byom_config"] = {
                tier: {"provider": cfg["provider"], "model_id": cfg["model_id"]}
                for tier, cfg in self._byom_config.items()
                if cfg.get("provider") and cfg.get("model_id")
            }
        keys = {
            tier: cfg["api_key"]
            for tier, cfg in self._byom_config.items()
            if cfg.get("api_key")
        }
        keys = {**keys, **(user_api_keys or {})}
        if keys:
            payload["user_api_keys"] = keys

    def ask(
        self,
        query: str,
        override_tier: Optional[str] = None,
        bypass_cache: bool = False,
        user_api_keys: Optional[dict] = None,
        model: Optional[str] = None,
        support_mode: Optional[str] = None,
    ) -> dict:
        """
        Send a query through the router. Returns the full response dict
        (response text, tier used, cost, latency, cache_hit, etc.)

        override_tier: optionally force "cheap", "mid", or "frontier"
        bypass_cache: skip semantic cache for this request
        user_api_keys: { "cheap": "key", "mid": "key", "frontier": "key" }
                       overrides keys for this single request only.
                       If not passed, uses keys set via configure().
        model: product name to pick a difficulty policy —
               "emma" (generic, default), "lisa" (3-tier support), "kate" (2-tier support)
        support_mode: raw policy id ("generic", "2tier", "3tier"). If given it
                      wins over model.
        """
        payload = {"query": query}
        if override_tier:
            payload["override_tier"] = override_tier
        if bypass_cache:
            payload["bypass_cache"] = True

        resolved = _ModelMapping.resolve(model, support_mode)
        if resolved:
            payload["support_mode"] = resolved

        self._apply_byom(payload, user_api_keys)

        response = requests.post(
            f"{self.base_url}/route",
            headers=self._headers(),
            json=payload,
            timeout=self.timeout,
        )
        _raise_for_status(response)
        return response.json()

    def ask_stream(
        self,
        query: str,
        override_tier: Optional[str] = None,
        bypass_cache: bool = False,
        user_api_keys: Optional[dict] = None,
        model: Optional[str] = None,
        support_mode: Optional[str] = None,
    ):
        """
        Streaming version of ask(). Yields text chunks, then a final dict
        with metadata (tier, cost, model_id, tokens).

        model: "emma" (generic), "lisa" (3-tier support), "kate" (2-tier support), or None.
        support_mode: raw policy id ("generic", "2tier", "3tier"); wins over model.

        Usage:
            for item in client.ask_stream("Explain quantum computing"):
                if isinstance(item, str):
                    print(item, end="", flush=True)
                else:
                    print(f"\n--- {item['tier']} | ${item['cost_usd']:.4f} ---")
        """
        payload = {"query": query}
        if override_tier:
            payload["override_tier"] = override_tier
        if bypass_cache:
            payload["bypass_cache"] = True

        resolved = _ModelMapping.resolve(model, support_mode)
        if resolved:
            payload["support_mode"] = resolved

        self._apply_byom(payload, user_api_keys)

        response = requests.post(
            f"{self.base_url}/route/stream",
            headers=self._headers(),
            json=payload,
            timeout=self.timeout,
            stream=True,
        )
        _raise_for_status(response)

        for line in response.iter_lines():
            if not line:
                continue
            decoded = line.decode()
            if not decoded.startswith("data: "):
                continue
            try:
                event = json.loads(decoded[6:])
            except json.JSONDecodeError:
                continue

            if event.get("type") == "chunk":
                yield event.get("text", "")
            elif event.get("type") == "done":
                yield {
                    "tier": event.get("routed_to"),
                    "model_id": event.get("model_id", event.get("routed_to")),
                    "cost_usd": event.get("cost_usd", 0),
                    "latency_ms": event.get("latency_ms", 0),
                    "cache_hit": event.get("cache_hit", False),
                    "difficulty_score": event.get("difficulty_score"),
                    "support_mode": event.get("support_mode"),
                }
                return
            elif event.get("type") == "error":
                raise RouteWiseError(event.get("detail", "Stream error"))
            elif event.get("type") == "meta":
                pass  # intermediate metadata, skip

    def chat(
        self,
        messages: list,
        model: str = "auto",
        stream: bool = False,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> dict:
        """
        OpenAI-compatible /v1/chat/completions endpoint.
        Drop-in replacement for openai.ChatCompletion.create().

        model: "auto" for ML routing, "cheap"/"mid"/"frontier" to force a tier,
               or a product name ("emma"/"lisa"/"kate") to use that difficulty
               policy (generic / 3-tier support / 2-tier support).
        messages: [{"role": "user", "content": "..."}] (same as OpenAI format)
        stream: if True, returns an iterator of chunk dicts
        max_tokens: optional token limit
        temperature: optional temperature

        Returns a dict matching the OpenAI chat completion response format.
        """
        payload = {"model": model, "messages": messages}
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if temperature is not None:
            payload["temperature"] = temperature
        if stream:
            payload["stream"] = True

        response = requests.post(
            f"{self.base_url}/v1/chat/completions",
            headers={**self._headers(), "Content-Type": "application/json"},
            json=payload,
            timeout=self.timeout,
            stream=stream,
        )
        _raise_for_status(response)

        if not stream:
            return response.json()

        return self._chat_stream(response)

    def _chat_stream(self, response: requests.Response):
        """Internal generator for streaming chat responses."""
        for line in response.iter_lines():
            if not line:
                continue
            decoded = line.decode()
            if decoded == "data: [DONE]":
                return
            if not decoded.startswith("data: "):
                continue
            try:
                chunk = json.loads(decoded[6:])
                yield chunk
            except json.JSONDecodeError:
                continue

    def configure(
        self,
        cheap: Optional[dict] = None,
        mid: Optional[dict] = None,
        frontier: Optional[dict] = None,
    ) -> dict:
        """
        Set custom provider/model/api_key for any tier (Bring Your Own Model).
        Configure one, two, or all three tiers — tiers you omit keep the server
        defaults (e.g. only frontier for a one-model setup, or cheap+frontier
        for a two-tier stack).

        Each tier dict: { "provider": "openai", "model_id": "gpt-4o", "api_key": "sk-..." }

        Config is stored in memory on the client and applied to every
        subsequent ask()/ask_stream() call via the per-request BYOM fields.
        API keys never touch the server's database.

        Example:
            client.configure(
                frontier={"provider": "openai", "model_id": "gpt-4o", "api_key": "sk-..."}
            )
        """
        saved = {}
        for tier, cfg in {"cheap": cheap, "mid": mid, "frontier": frontier}.items():
            if cfg is None:
                continue
            if not isinstance(cfg, dict) or not cfg.get("api_key"):
                raise ValidationError(f"[400] {tier} config requires an 'api_key'")
            self._byom_config[tier] = {
                "provider": cfg.get("provider"),
                "model_id": cfg.get("model_id"),
                "api_key": cfg["api_key"],
            }
            saved[tier] = {"provider": cfg.get("provider"), "model_id": cfg.get("model_id")}
        return {"saved": saved}

    def get_config(self) -> dict:
        """
        Returns the currently active model config for all tiers
        (user overrides merged with defaults, plus any config set via
        configure()). API keys are never returned.
        """
        response = requests.get(f"{self.base_url}/config", headers=self._headers(), timeout=self.timeout)
        _raise_for_status(response)
        config = response.json()
        for tier, cfg in self._byom_config.items():
            if tier in config:
                config[tier]["provider"] = cfg.get("provider") or config[tier].get("provider")
                config[tier]["model_id"] = cfg.get("model_id") or config[tier].get("model_id")
        return config

    def reset(self) -> dict:
        """
        Clears any in-memory BYOM config and api keys set by configure(),
        reverting all tiers back to the default models.
        """
        self._byom_config.clear()
        return {"reset": True}

    def get_providers(self) -> dict:
        """
        Returns all supported providers and their available models.
        Useful for discovering what you can pass to configure().
        """
        response = requests.get(f"{self.base_url}/providers", headers=self._headers(), timeout=self.timeout)
        _raise_for_status(response)
        return response.json()

    def get_models(self) -> dict:
        """
        Lists the available routing models (emma / lisa / kate) with their
        policies, tier cuts and evaluation metrics.
        """
        response = requests.get(f"{self.base_url}/route/policies", headers=self._headers(), timeout=self.timeout)
        _raise_for_status(response)
        return response.json()

    def stats(self) -> dict:
        """Fetch aggregate usage stats (total requests, cost saved, tier distribution, etc.)"""
        response = requests.get(f"{self.base_url}/stats", headers=self._headers(), timeout=self.timeout)
        _raise_for_status(response)
        return response.json()

    def get_logs(self, limit: int = 50) -> list[dict]:
        """
        Fetch recent request logs for this API key.
        Returns a list of dicts with query, tier, cost, latency, etc.
        """
        response = requests.get(
            f"{self.base_url}/logs",
            headers=self._headers(),
            params={"limit": min(limit, 100)},
            timeout=self.timeout,
        )
        _raise_for_status(response)
        return response.json()

    def get_log_detail(self, log_id: int) -> dict:
        """
        Fetch full detail of a single log entry (including full response text).
        """
        response = requests.get(
            f"{self.base_url}/logs/{log_id}",
            headers=self._headers(),
            timeout=self.timeout,
        )
        _raise_for_status(response)
        return response.json()

    def get_analytics(self) -> dict:
        """
        Fetch detailed cost analytics for this API key:
        tier costs, model costs, daily breakdown, latency, top expensive queries.
        """
        response = requests.get(
            f"{self.base_url}/analytics",
            headers=self._headers(),
            timeout=self.timeout,
        )
        _raise_for_status(response)
        return response.json()

    def get_pricing(self) -> list[dict]:
        """
        Fetch all active model pricing rows.
        """
        response = requests.get(f"{self.base_url}/pricing", headers=self._headers(), timeout=self.timeout)
        _raise_for_status(response)
        return response.json()
