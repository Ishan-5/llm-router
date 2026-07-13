"""
routewise -- a thin Python client for the routewise cost-aware LLM router.

This does NOT contain any routing logic. It just wraps HTTP calls to the
real API so callers don't have to write requests.post()/headers/error
handling by hand every time.
"""
import requests

DEFAULT_BASE_URL = "https://llm-router-d2b2.onrender.com"


class RouteWiseError(Exception):
    """Raised when the API returns an error response."""
    pass


class RouteWiseClient:
    def __init__(self, api_key: str, base_url: str = DEFAULT_BASE_URL, timeout: int = 30):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"}

    def ask(self, query: str, override_tier: str | None = None) -> dict:
        """
        Send a query through the router. Returns the full response dict
        (response text, tier used, cost, latency, cache_hit, etc.)

        override_tier: optionally force "cheap", "mid", or "frontier"
        instead of letting the difficulty model decide.
        """
        payload = {"query": query}
        if override_tier:
            payload["override_tier"] = override_tier

        response = requests.post(
            f"{self.base_url}/route",
            headers=self._headers(),
            json=payload,
            timeout=self.timeout,
        )

        if not response.ok:
            detail = response.json().get("detail", response.text) if response.content else response.text
            raise RouteWiseError(f"[{response.status_code}] {detail}")

        return response.json()

    def stats(self) -> dict:
        """Fetch aggregate usage stats (total requests, cost saved, tier distribution, etc.)"""
        response = requests.get(f"{self.base_url}/stats", timeout=self.timeout)
        if not response.ok:
            raise RouteWiseError(f"[{response.status_code}] {response.text}")
        return response.json()