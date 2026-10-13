"""Prometheus metrics for RouteWise.

Exposed at ``GET /metrics/prometheus`` in the text exposition format. The older
``GET /metrics`` still returns the JSON rollup the dashboard reads and is left
untouched, so nothing that depends on it changes.

The registry is deliberately private rather than prometheus_client's global
default: the exposition is then limited to the metrics this service defines,
identical on every OS, and unaffected by imports that happen to register
metrics elsewhere.
"""
from __future__ import annotations

import time

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest
from starlette.responses import Response

CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"

REGISTRY = CollectorRegistry()

# One request here fans out to an upstream LLM, so latency buckets reach much
# further than the usual web defaults.
_LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)
_ROUTING_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)

REQUESTS = Counter(
    "routewise_requests",
    "HTTP requests handled, by method, matched route and status.",
    ["method", "path", "status"],
    registry=REGISTRY,
)
REQUEST_DURATION = Histogram(
    "routewise_request_duration_seconds",
    "HTTP request duration in seconds.",
    ["method", "path"],
    buckets=_LATENCY_BUCKETS,
    registry=REGISTRY,
)
INFLIGHT = Gauge(
    "routewise_inflight_requests",
    "HTTP requests currently being served.",
    registry=REGISTRY,
)
ROUTING_DURATION = Histogram(
    "routewise_routing_decision_seconds",
    "Time to decide a route: cache lookup plus difficulty scoring.",
    buckets=_ROUTING_BUCKETS,
    registry=REGISTRY,
)
TIER_DECISIONS = Counter(
    "routewise_tier_decisions",
    "Routing decisions, by chosen tier and policy.",
    ["tier", "policy"],
    registry=REGISTRY,
)
CACHE_EVENTS = Counter(
    "routewise_cache_events",
    "Semantic-cache outcomes (hit, miss, skipped, stored).",
    ["result"],
    registry=REGISTRY,
)
BUILD_INFO = Gauge(
    "routewise_build_info",
    "Static build information (always 1); labels carry the deployed model.",
    ["service", "model"],
    registry=REGISTRY,
)
BUILD_INFO.labels(service="routewise", model="unknown").set(1)


def observe_request(method: str, path: str, status: int, duration_s: float) -> None:
    REQUESTS.labels(method=method, path=path, status=str(status)).inc()
    REQUEST_DURATION.labels(method=method, path=path).observe(duration_s)


def observe_routing(duration_s: float) -> None:
    ROUTING_DURATION.observe(duration_s)


def observe_tier(tier: str, policy: str = "generic") -> None:
    TIER_DECISIONS.labels(tier=tier, policy=policy or "generic").inc()


def observe_cache(result: str) -> None:
    CACHE_EVENTS.labels(result=result).inc()


def set_model_info(model_name: str) -> None:
    """Record the deployed model name on ``routewise_build_info``."""
    if not model_name or model_name == "unknown":
        return
    try:
        BUILD_INFO.remove("routewise", "unknown")
    except KeyError:
        pass
    BUILD_INFO.labels(service="routewise", model=model_name).set(1)


def metrics_response() -> Response:
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)


# Paths whose own traffic should not skew the request metrics (dashboard polls
# and Prometheus scrapes).
_SKIP_PATHS = frozenset({"/metrics", "/metrics/prometheus"})


class PrometheusMiddleware:
    """Pure ASGI middleware that counts and times HTTP requests.

    It is deliberately not a ``BaseHTTPMiddleware``: that would wrap the
    streaming ``/route/stream`` response, and pure ASGI passes messages straight
    through so server-sent events are left untouched.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or scope.get("path") in _SKIP_PATHS:
            return await self.app(scope, receive, send)

        INFLIGHT.inc()
        started = time.perf_counter()
        status = {"code": 500}

        async def _send(message):
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, _send)
        finally:
            INFLIGHT.dec()
            route = scope.get("route")
            # The matched route template keeps label cardinality bounded; an
            # unmatched path (404) collapses to a single series.
            path = getattr(route, "path", None) or "unmatched"
            observe_request(
                scope.get("method", "GET"),
                path,
                status["code"],
                time.perf_counter() - started,
            )
