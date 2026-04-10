"""
License API Routes

Admin endpoints for license management and a public validation endpoint
for container/verifier phone-home checks.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from .service import (
    IssuedLicense,
    LicenseIssuerError,
    LicenseIssuerService,
    LicenseNotFoundError,
    LicenseRequest,
    VALID_PLAN_TIERS,
)
from .registry import RegistryGatingService, RegistryGatingError

logger = logging.getLogger(__name__)


# --- Pydantic schemas ---

class IssueLicenseRequest(BaseModel):
    """Request body for issuing a new license."""
    org_id: UUID
    org_name: str
    plan_tier: str = Field(..., description="One of: sandbox, program, institution, system")
    entitled_products: list[str] | None = None
    features: list[str] | None = None
    max_instances: dict[str, int] | None = None
    registry_access: bool | None = None
    api_calls_limit: int | None = None
    hardware_binding: str | None = None
    deployment_mode: str | None = None
    duration_days: int = Field(default=365, ge=1, le=1095)
    grace_period_days: int | None = Field(default=None, ge=1, le=90)


class IssuedLicenseResponse(BaseModel):
    """Response after issuing a license."""
    license_id: str
    license_jti: str
    license_jwt: str
    org_id: str
    plan_tier: str
    issued_at: str
    expires_at: str
    entitled_products: list[str]
    features: list[str]


class RevokeLicenseRequest(BaseModel):
    """Request body for revoking a license."""
    reason: str = "Subscription canceled"


class RevokeOrgLicensesRequest(BaseModel):
    """Request body for revoking all org licenses."""
    org_id: UUID
    reason: str = "Subscription canceled"


class LicenseResponse(BaseModel):
    """License record response."""
    license_id: str
    license_jti: str
    org_id: str
    status: str
    plan_tier: str
    entitled_products: list[str] | None
    features: list[str] | None
    registry_access: bool
    api_calls_limit: int
    issued_at: str
    expires_at: str
    revoked_at: str | None = None
    revocation_reason: str | None = None


class ValidationResponse(BaseModel):
    """Online license validation response."""
    valid: bool
    reason: str | None = None
    plan_tier: str | None = None
    expires_at: str | None = None
    entitled_products: list[str] | None = None


class PublicKeyResponse(BaseModel):
    """Public key response for container bootstrapping."""
    public_key_pem: str
    algorithm: str = "EdDSA"
    key_type: str = "Ed25519"


class RegistryCredentialResponse(BaseModel):
    """Registry credential response (returned only once at issuance)."""
    credential_id: str
    org_id: str
    registry_url: str
    username: str
    token: str
    allowed_images: list[str]
    expires_at: str | None = None


class RegistryCredentialInfoResponse(BaseModel):
    """Registry credential info (no token — for status checks)."""
    credential_id: str
    org_id: str
    registry_url: str
    username: str
    allowed_images: list[str]
    status: str
    issued_at: str
    expires_at: str | None = None


class RegistryTokenValidationRequest(BaseModel):
    """Request body for registry proxy token validation."""
    username: str
    token: str


class RegistryTokenValidationResponse(BaseModel):
    """Response for registry proxy token validation."""
    valid: bool
    org_id: str | None = None
    allowed_images: list[str] | None = None
    expires_at: str | None = None


class ErrorResponse(BaseModel):
    """Error response."""
    detail: str


# --- Dependency injection placeholder ---
# The actual wiring happens when the router is mounted in the application.
# This follows the same pattern as other routers in the codebase.

_license_service_factory = None
_key_manager_factory = None
_registry_service_factory = None


def configure_license_dependencies(
    license_service_factory,
    key_manager_factory,
    registry_service_factory=None,
):
    """Configure dependency factories. Called at application startup."""
    global _license_service_factory, _key_manager_factory, _registry_service_factory
    _license_service_factory = license_service_factory
    _key_manager_factory = key_manager_factory
    _registry_service_factory = registry_service_factory


async def get_license_service() -> LicenseIssuerService:
    if _license_service_factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="License service not configured",
        )
    return await _license_service_factory()


def get_key_manager():
    if _key_manager_factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Key manager not configured",
        )
    return _key_manager_factory()


async def get_registry_service() -> RegistryGatingService:
    if _registry_service_factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Registry service not configured",
        )
    return await _registry_service_factory()


# --- Admin routes (protected — require admin auth) ---

admin_license_router = APIRouter(
    prefix="/v1/admin/licenses",
    tags=["License Administration"],
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)


@admin_license_router.post(
    "",
    response_model=IssuedLicenseResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Issue a new license",
    description="Mint a signed Ed25519 JWT license for an organization. "
    "Supersedes any existing active license for the org.",
)
async def issue_license(
    body: IssueLicenseRequest,
    service: LicenseIssuerService = Depends(get_license_service),
) -> IssuedLicenseResponse:
    try:
        result = await service.issue_license(LicenseRequest(
            org_id=body.org_id,
            org_name=body.org_name,
            plan_tier=body.plan_tier,
            entitled_products=body.entitled_products,
            features=body.features,
            max_instances=body.max_instances,
            registry_access=body.registry_access,
            api_calls_limit=body.api_calls_limit,
            hardware_binding=body.hardware_binding,
            deployment_mode=body.deployment_mode,
            duration_days=body.duration_days,
            grace_period_days=body.grace_period_days,
        ))
        return IssuedLicenseResponse(
            license_id=str(result.license_id),
            license_jti=result.license_jti,
            license_jwt=result.license_jwt,
            org_id=str(result.org_id),
            plan_tier=result.plan_tier,
            issued_at=result.issued_at.isoformat(),
            expires_at=result.expires_at.isoformat(),
            entitled_products=result.entitled_products,
            features=result.features,
        )
    except LicenseIssuerError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception:
        logger.exception("Failed to issue license")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@admin_license_router.post(
    "/{license_jti}/revoke",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a license",
    description="Revoke a specific license by JTI. Adds to revocation list for online validation.",
)
async def revoke_license(
    license_jti: str,
    body: RevokeLicenseRequest,
    service: LicenseIssuerService = Depends(get_license_service),
) -> None:
    try:
        await service.revoke_license(license_jti, reason=body.reason)
    except LicenseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="License not found")
    except Exception:
        logger.exception("Failed to revoke license %s", license_jti)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@admin_license_router.post(
    "/revoke-org",
    status_code=status.HTTP_200_OK,
    summary="Revoke all org licenses",
    description="Revoke all active licenses for an organization.",
)
async def revoke_org_licenses(
    body: RevokeOrgLicensesRequest,
    service: LicenseIssuerService = Depends(get_license_service),
) -> dict[str, Any]:
    try:
        count = await service.revoke_org_licenses(body.org_id, reason=body.reason)
        return {"revoked_count": count}
    except Exception:
        logger.exception("Failed to revoke org licenses for %s", body.org_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@admin_license_router.get(
    "/org/{org_id}",
    response_model=list[LicenseResponse],
    summary="List org licenses",
    description="List all licenses for an organization.",
)
async def list_org_licenses(
    org_id: UUID,
    include_inactive: bool = False,
    service: LicenseIssuerService = Depends(get_license_service),
) -> list[LicenseResponse]:
    try:
        licenses = await service.list_org_licenses(org_id, include_inactive=include_inactive)
        return [_license_to_response(lic) for lic in licenses]
    except Exception:
        logger.exception("Failed to list licenses for org %s", org_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@admin_license_router.get(
    "/{license_jti}",
    response_model=LicenseResponse,
    summary="Get license details",
    description="Get a specific license record by JTI.",
)
async def get_license(
    license_jti: str,
    service: LicenseIssuerService = Depends(get_license_service),
) -> LicenseResponse:
    lic = await service.get_license_by_jti(license_jti)
    if lic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="License not found")
    return _license_to_response(lic)


# --- Public routes (for phone-home validation) ---

public_license_router = APIRouter(
    prefix="/v1/licenses",
    tags=["License Validation"],
    responses={
        500: {"model": ErrorResponse},
    },
)


@public_license_router.get(
    "/validate/{license_jti}",
    response_model=ValidationResponse,
    summary="Validate a license (phone-home)",
    description="Online validation check for containers and verifier apps. "
    "Returns whether the license is still valid and not revoked.",
)
async def validate_license(
    license_jti: str,
    service: LicenseIssuerService = Depends(get_license_service),
) -> ValidationResponse:
    try:
        result = await service.validate_license_online(license_jti)
        return ValidationResponse(**result)
    except Exception:
        logger.exception("Failed to validate license %s", license_jti)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@public_license_router.get(
    "/public-key",
    response_model=PublicKeyResponse,
    summary="Get license signing public key",
    description="Returns the Ed25519 public key used to verify license signatures. "
    "Containers use this to verify licenses offline.",
)
async def get_public_key(
    key_manager=Depends(get_key_manager),
) -> PublicKeyResponse:
    try:
        return PublicKeyResponse(public_key_pem=key_manager.public_key_pem())
    except Exception:
        logger.exception("Failed to get public key")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


# --- Helpers ---

def _license_to_response(lic) -> LicenseResponse:
    return LicenseResponse(
        license_id=str(lic.id),
        license_jti=lic.license_jti,
        org_id=str(lic.org_id),
        status=lic.status,
        plan_tier=lic.plan_tier,
        entitled_products=lic.entitled_products,
        features=lic.features,
        registry_access=lic.registry_access,
        api_calls_limit=lic.api_calls_limit,
        issued_at=lic.issued_at.isoformat(),
        expires_at=lic.expires_at.isoformat(),
        revoked_at=lic.revoked_at.isoformat() if lic.revoked_at else None,
        revocation_reason=lic.revocation_reason,
    )


# --- Registry routes (admin — manage org pull credentials) ---

admin_registry_router = APIRouter(
    prefix="/v1/admin/registry",
    tags=["Registry Administration"],
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)


@admin_registry_router.post(
    "/credentials/{org_id}",
    response_model=RegistryCredentialResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Issue registry credentials",
    description="Generate pull credentials for an org's entitled container images. "
    "Supersedes any existing credentials for the org.",
)
async def issue_registry_credentials(
    org_id: UUID,
    license_jti: str = Query(...),
    entitled_products: list[str] = Query(...),
    registry_prefix: str = Query(default=""),
    service: RegistryGatingService = Depends(get_registry_service),
) -> RegistryCredentialResponse:
    try:
        result = await service.issue_credentials(
            org_id=org_id,
            license_jti=license_jti,
            entitled_products=entitled_products,
            registry_prefix=registry_prefix,
        )
        return RegistryCredentialResponse(
            credential_id=str(result.credential_id),
            org_id=str(result.org_id),
            registry_url=result.registry_url,
            username=result.username,
            token=result.token,
            allowed_images=result.allowed_images,
            expires_at=result.expires_at.isoformat() if result.expires_at else None,
        )
    except Exception:
        logger.exception("Failed to issue registry credentials for org %s", org_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@admin_registry_router.delete(
    "/credentials/{org_id}",
    status_code=status.HTTP_200_OK,
    summary="Revoke registry credentials",
    description="Revoke all active registry pull credentials for an org.",
)
async def revoke_registry_credentials(
    org_id: UUID,
    reason: str = "Subscription canceled",
    service: RegistryGatingService = Depends(get_registry_service),
) -> dict[str, Any]:
    try:
        count = await service.revoke_org_credentials(org_id, reason)
        return {"revoked_count": count}
    except Exception:
        logger.exception("Failed to revoke registry credentials for org %s", org_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@admin_registry_router.get(
    "/credentials/{org_id}",
    response_model=RegistryCredentialInfoResponse | None,
    summary="Get registry credential status",
    description="Check the current registry credential status for an org. "
    "Does not return the token — only metadata.",
)
async def get_registry_credential_status(
    org_id: UUID,
    service: RegistryGatingService = Depends(get_registry_service),
) -> RegistryCredentialInfoResponse | None:
    cred = await service.get_org_credential(org_id)
    if cred is None:
        return None
    return RegistryCredentialInfoResponse(
        credential_id=str(cred.id),
        org_id=str(cred.org_id),
        registry_url=cred.registry_url,
        username=cred.username,
        allowed_images=cred.allowed_images or [],
        status=cred.status,
        issued_at=cred.issued_at.isoformat(),
        expires_at=cred.expires_at.isoformat() if cred.expires_at else None,
    )


# --- Registry proxy validation (called by container registry pull proxy) ---

registry_proxy_router = APIRouter(
    prefix="/v1/registry",
    tags=["Registry Proxy"],
    responses={
        500: {"model": ErrorResponse},
    },
)


@registry_proxy_router.post(
    "/validate-token",
    response_model=RegistryTokenValidationResponse,
    summary="Validate a registry pull token",
    description="Called by the registry proxy on each pull to validate the presented token "
    "against the stored credentials. Returns allowed images if valid.",
)
async def validate_registry_token(
    body: RegistryTokenValidationRequest,
    service: RegistryGatingService = Depends(get_registry_service),
) -> RegistryTokenValidationResponse:
    try:
        result = await service.validate_token(body.username, body.token)
        if result is None:
            return RegistryTokenValidationResponse(valid=False)
        return RegistryTokenValidationResponse(
            valid=True,
            org_id=result["org_id"],
            allowed_images=result["allowed_images"],
            expires_at=result["expires_at"],
        )
    except Exception:
        logger.exception("Failed to validate registry token")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )
