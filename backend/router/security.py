"""Baseline security response headers.

Applied as a pure ASGI middleware rather than Starlette's BaseHTTPMiddleware:
the latter buffers the response body, which would break /route/stream's SSE.
This only appends headers to the ``http.response.start`` message, so streaming
passes through untouched while every response still leaves hardened.

Deliberately no Content-Security-Policy here: the API serves JSON and hosts
Swagger UI / ReDoc at /docs and /redoc, which rely on inline scripts. A CSP that
kept those working would be theatre, and a strict one would break them.
"""
from __future__ import annotations

# These do not change what the API can serve; they only stop a browser from
# being talked into reinterpreting a response.
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}

# Only meaningful (and only honoured by browsers) over TLS, so it is added only
# when the request arrived over HTTPS -- locally it is correctly absent.
HSTS_HEADER = ("strict-transport-security", "max-age=31536000; includeSubDomains")


class SecurityHeadersMiddleware:
    """Append baseline security headers to every HTTP response."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        https = scope.get("scheme") == "https"

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                present = {name.lower() for name, _ in headers}
                for name, value in SECURITY_HEADERS.items():
                    lowered = name.lower().encode()
                    if lowered not in present:
                        headers.append((lowered, value.encode()))
                if https and HSTS_HEADER[0].encode() not in present:
                    headers.append((HSTS_HEADER[0].encode(), HSTS_HEADER[1].encode()))
            await send(message)

        await self.app(scope, receive, send_with_headers)
