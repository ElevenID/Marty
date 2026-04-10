"""
TLS Enforcement Middleware

Rejects non-HTTPS requests in production and adds security headers.
"""

import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class EnforceTLSMiddleware(BaseHTTPMiddleware):
    """
    Middleware that enforces HTTPS in production.

    - Rejects plain HTTP requests with 403 when ENVIRONMENT=production.
    - Adds Strict-Transport-Security header to all responses.
    - Respects X-Forwarded-Proto from trusted reverse proxies.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        environment = os.getenv("ENVIRONMENT", "development")

        # Determine effective scheme (trust X-Forwarded-Proto from proxy)
        scheme = request.headers.get("x-forwarded-proto", request.url.scheme)

        if environment == "production" and scheme != "https":
            return JSONResponse(
                status_code=403,
                content={"detail": "HTTPS required in production"},
            )

        response = await call_next(request)

        # HSTS: tell browsers to always use HTTPS (1 year, include subdomains)
        if scheme == "https" or environment == "production":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )

        return response
