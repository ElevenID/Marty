"""
License Enforcement Middleware for FastAPI

Provides a FastAPI dependency and middleware that validates the container's
license on every request. Designed to be added to any Marty container service.

Usage:
    from src.licensing.middleware import require_license, get_license_info

    app = FastAPI()

    # Enforce on all routes:
    app.add_middleware(LicenseMiddleware, validator=validator)

    # Or per-route:
    @app.get("/api/something")
    async def something(license=Depends(require_license)):
        ...

    # Access license info without blocking:
    @app.get("/api/info")
    async def info(license=Depends(get_license_info)):
        ...
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from .usage import UsageMeter, _seconds_until_month_end
from .validator import (
    LicenseExpiredError,
    LicenseInfo,
    LicenseValidationError,
    LicenseValidator,
    ProductNotEntitledError,
)

logger = logging.getLogger(__name__)

# Module-level validator instance (set during app startup)
_validator: LicenseValidator | None = None
_usage_meter: UsageMeter | None = None


def configure_license_middleware(
    validator: LicenseValidator,
    usage_meter: UsageMeter | None = None,
) -> None:
    """Configure the module-level validator. Called at app startup."""
    global _validator, _usage_meter
    _validator = validator
    _usage_meter = usage_meter


def _get_validator() -> LicenseValidator:
    if _validator is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="License system not configured",
        )
    return _validator


# --- FastAPI Dependencies ---

async def require_license() -> LicenseInfo:
    """
    FastAPI dependency that requires a valid license.

    Returns the license info if valid, raises 403 if not.
    """
    validator = _get_validator()
    info = validator.cached_info

    if info is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No valid license loaded",
        )

    if validator.is_revoked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="License has been revoked",
        )

    if info.is_expired and not info.grace_period_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="License has expired",
        )

    return info


async def get_license_info() -> LicenseInfo | None:
    """
    FastAPI dependency that returns license info without blocking.

    Returns None if no license is loaded (for informational endpoints).
    """
    validator = _get_validator()
    return validator.cached_info


def require_feature(feature: str):
    """
    Factory for a FastAPI dependency that requires a specific feature.

    Usage:
        @app.get("/api/mdl/verify")
        async def verify_mdl(license=Depends(require_feature("mdl"))):
            ...
    """
    async def _check(license: LicenseInfo = Depends(require_license)) -> LicenseInfo:
        validator = _get_validator()
        if not validator.has_feature(feature):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Feature '{feature}' is not included in your license",
            )
        return license
    return _check


def require_product(product: str):
    """
    Factory for a FastAPI dependency that requires a specific product entitlement.

    Usage:
        @app.get("/api/sign")
        async def sign(license=Depends(require_product("document-signer"))):
            ...
    """
    async def _check(license: LicenseInfo = Depends(require_license)) -> LicenseInfo:
        validator = _get_validator()
        if not validator.has_product(product):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Product '{product}' is not entitled by your license",
            )
        return license
    return _check


# --- Starlette Middleware (blanket enforcement) ---

# Paths that bypass license checks (health, readiness, metrics)
DEFAULT_EXEMPT_PATHS = {
    "/health",
    "/healthz",
    "/ready",
    "/readyz",
    "/metrics",
    "/v1/licenses/validate",
    "/v1/licenses/public-key",
}


class LicenseMiddleware(BaseHTTPMiddleware):
    """
    Middleware that enforces license validation on all requests.

    Health/readiness endpoints are exempted so orchestrators can
    still probe the container.
    """

    def __init__(
        self,
        app,
        validator: LicenseValidator,
        exempt_paths: set[str] | None = None,
        usage_meter: UsageMeter | None = None,
    ):
        super().__init__(app)
        self._validator = validator
        self._exempt_paths = exempt_paths or DEFAULT_EXEMPT_PATHS
        self._usage_meter = usage_meter

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        path = request.url.path.rstrip("/")

        # Skip license check for exempt paths
        if path in self._exempt_paths:
            return await call_next(request)

        info = self._validator.cached_info

        if info is None:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"detail": "No valid license loaded — service unavailable"},
            )

        if self._validator.is_revoked:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "License has been revoked"},
            )

        if info.is_expired and not info.grace_period_active:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "License has expired"},
            )

        # Add license info to request state for downstream access
        request.state.license = info

        # Log grace period warning (once per request, not spammy)
        if info.grace_period_active:
            logger.warning("Serving request under grace period — license renewal needed")

        # --- Usage metering & enforcement ---
        if self._usage_meter is not None and info.api_calls_limit > 0:
            count = await self._usage_meter.increment(info.org_id)
            limit = info.api_calls_limit

            if count > limit:
                retry_after = _seconds_until_month_end()
                return JSONResponse(
                    status_code=429,
                    content={"detail": "API call limit exceeded for this billing period"},
                    headers={
                        "Retry-After": str(retry_after),
                        "X-RateLimit-Limit": str(limit),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(retry_after),
                    },
                )

        # Trigger async phone-home if due (fire-and-forget)
        try:
            await self._validator.phone_home()
        except Exception:
            pass  # never block requests for phone-home failures

        response = await call_next(request)

        # Attach rate-limit headers to successful responses
        if self._usage_meter is not None and info.api_calls_limit > 0:
            limit = info.api_calls_limit
            usage = await self._usage_meter.get_usage(info.org_id)
            remaining = max(limit - usage, 0)
            response.headers["X-RateLimit-Limit"] = str(limit)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            response.headers["X-RateLimit-Reset"] = str(_seconds_until_month_end())

        return response
