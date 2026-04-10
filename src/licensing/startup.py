"""
Container Startup License Check

Validates the license before the application starts serving traffic.
Designed to be called from container entrypoints or FastAPI lifespan hooks.

Usage in FastAPI lifespan:

    from src.licensing.startup import create_licensed_lifespan

    app = FastAPI(lifespan=create_licensed_lifespan(product_id="document-signer"))

Usage as standalone check:

    from src.licensing.startup import startup_license_check

    license_info = startup_license_check(product_id="document-signer")
"""
from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from .middleware import LicenseMiddleware, configure_license_middleware
from .validator import (
    LicenseExpiredError,
    LicenseInfo,
    LicenseValidationError,
    LicenseValidator,
    ProductNotEntitledError,
)

logger = logging.getLogger(__name__)

# Re-validation interval for the background task (seconds)
REVALIDATION_INTERVAL = 3600  # 1 hour


def startup_license_check(
    product_id: str,
    *,
    strict: bool = True,
) -> LicenseInfo | None:
    """
    Synchronous license check for container startup.

    Args:
        product_id: The product ID this container runs (e.g., "document-signer").
        strict: If True (default), exit the process on license failure.
                If False, return None on failure (for dev/test environments).

    Returns:
        LicenseInfo if valid, None if strict=False and validation fails.
    """
    try:
        validator = LicenseValidator.from_env(product_id=product_id)
        info = validator.validate_from_env()

        logger.info(
            "License validated: org=%s plan=%s product=%s expires=%s",
            info.org_id,
            info.plan_tier,
            product_id,
            info.expires_at.isoformat(),
        )

        if info.grace_period_active:
            logger.warning(
                "License is in grace period — %d days remaining. "
                "Renew the license to avoid service interruption.",
                info.grace_period_days,
            )

        return info

    except LicenseExpiredError as e:
        logger.error("License expired: %s", e)
        if strict:
            sys.exit(78)  # EX_CONFIG
        return None

    except ProductNotEntitledError as e:
        logger.error("Product not entitled: %s", e)
        if strict:
            sys.exit(77)  # EX_NOPERM
        return None

    except LicenseValidationError as e:
        logger.error("License validation failed: %s", e)
        if strict:
            sys.exit(78)  # EX_CONFIG
        return None


def create_licensed_lifespan(
    product_id: str,
    *,
    strict: bool = True,
    enable_middleware: bool = True,
    revalidation_interval: int = REVALIDATION_INTERVAL,
):
    """
    Create a FastAPI lifespan context manager that validates the license
    at startup and periodically re-validates in the background.

    Args:
        product_id: The product ID this container runs.
        strict: Exit the process if the license is invalid.
        enable_middleware: Automatically configure the license middleware.
        revalidation_interval: Seconds between background re-validation checks.

    Returns:
        An async context manager suitable for FastAPI's `lifespan` parameter.

    Usage:
        app = FastAPI(lifespan=create_licensed_lifespan("document-signer"))
    """
    @asynccontextmanager
    async def lifespan(app) -> AsyncGenerator[dict[str, Any], None]:
        # Validate license at startup
        try:
            validator = LicenseValidator.from_env(product_id=product_id)
            info = validator.validate_from_env()
        except LicenseValidationError as e:
            logger.error("Startup license check failed: %s", e)
            if strict:
                sys.exit(78)
            yield {}
            return

        logger.info(
            "License validated at startup: org=%s plan=%s product=%s expires=%s",
            info.org_id,
            info.plan_tier,
            product_id,
            info.expires_at.isoformat(),
        )

        # Configure middleware
        if enable_middleware:
            configure_license_middleware(validator)
            app.add_middleware(LicenseMiddleware, validator=validator)

        # Start background re-validation task
        revalidation_task = asyncio.create_task(
            _periodic_revalidation(validator, revalidation_interval)
        )

        yield {"license": info, "license_validator": validator}

        # Shutdown: cancel background task
        revalidation_task.cancel()
        try:
            await revalidation_task
        except asyncio.CancelledError:
            pass

    return lifespan


async def _periodic_revalidation(
    validator: LicenseValidator,
    interval: int,
) -> None:
    """Background task: re-validate license and phone home periodically."""
    while True:
        await asyncio.sleep(interval)
        try:
            # Re-validate the cached JWT
            validator.validate_from_env()
            logger.debug("Periodic license re-validation succeeded")

            # Phone home for revocation check
            result = await validator.phone_home()
            if result and not result.get("valid", True):
                logger.warning(
                    "Phone-home reports license invalid: %s",
                    result.get("reason", "unknown"),
                )

        except LicenseExpiredError:
            logger.error(
                "License expired during periodic check — "
                "service will stop accepting requests after grace period"
            )
        except LicenseValidationError as e:
            logger.warning("Periodic license re-validation failed: %s", e)
        except Exception:
            logger.debug("Periodic license check error", exc_info=True)
