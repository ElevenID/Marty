"""
Usage Metering API Routes

Endpoints for viewing API usage metrics.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from .middleware import require_license
from .usage import UsageMeter, _current_month
from .validator import LicenseInfo

logger = logging.getLogger(__name__)

# Module-level meter (set at startup)
_usage_meter: UsageMeter | None = None


def configure_usage_dependencies(usage_meter: UsageMeter) -> None:
    """Wire the usage meter instance. Called at app startup."""
    global _usage_meter
    _usage_meter = usage_meter


def _get_meter() -> UsageMeter:
    if _usage_meter is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Usage metering not configured",
        )
    return _usage_meter


# --- Schemas ---

class UsageResponse(BaseModel):
    org_id: str
    month: str
    api_calls_used: int
    api_calls_limit: int
    percent_used: float


# --- Routers ---

usage_router = APIRouter(prefix="/v1/usage", tags=["usage"])
admin_usage_router = APIRouter(prefix="/v1/admin/usage", tags=["usage-admin"])


@usage_router.get("", response_model=UsageResponse)
async def get_my_usage(
    license: LicenseInfo = Depends(require_license),
):
    """Get current org's usage for the current billing period."""
    meter = _get_meter()
    month = _current_month()
    used = await meter.get_usage(license.org_id, month)
    limit = license.api_calls_limit
    pct = (used / limit * 100) if limit > 0 else 0.0
    return UsageResponse(
        org_id=license.org_id,
        month=month,
        api_calls_used=used,
        api_calls_limit=limit,
        percent_used=round(pct, 2),
    )


@admin_usage_router.get("/{org_id}", response_model=UsageResponse)
async def get_org_usage(
    org_id: str,
    month: str | None = None,
):
    """Admin: view any org's usage for a given month."""
    meter = _get_meter()
    m = month or _current_month()
    used = await meter.get_usage(org_id, m)
    return UsageResponse(
        org_id=org_id,
        month=m,
        api_calls_used=used,
        api_calls_limit=0,  # admin view doesn't know the org's limit
        percent_used=0.0,
    )


@admin_usage_router.post("/{org_id}/reset", status_code=status.HTTP_204_NO_CONTENT)
async def reset_org_usage(
    org_id: str,
    month: str | None = None,
):
    """Admin: reset an org's usage counter for a given month."""
    meter = _get_meter()
    m = month or _current_month()
    await meter.reset(org_id, m)
