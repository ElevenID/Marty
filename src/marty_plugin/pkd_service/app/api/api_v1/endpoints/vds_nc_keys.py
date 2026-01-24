"""PKD API endpoints for VDS-NC key distribution.

Provides RESTful endpoints for distributing VDS-NC signer public keys
according to ICAO Doc 9303 Part 13 and the unified trust protocol.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from marty_common.crypto.database_vds_nc_manager import (
    DatabaseVDSNCKeyManager,
    VDSNCKeyRepository,
)
from marty_common.crypto.vds_nc_keys import (
    KeyRole,
    KeyStatus,
    VDSNCKeyManager,
    VDSNCKeyDistributor,  # type: ignore
)


def get_key_distributor() -> VDSNCKeyDistributor:  # type: ignore
    """Placeholder dependency provider for key distributor.

    In full implementation this would resolve an instance from the application
    container. For now we raise a 501 to indicate it's not wired.
    """
    raise HTTPException(status_code=501, detail="Key distributor not configured")

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/pkd", tags=["PKD VDS-NC Keys"])


# Pydantic models for API responses
class VDSNCKeyResponse(BaseModel):
    """Single VDS-NC key in JWK format."""

    kid: str = Field(..., description="Key identifier")
    kty: str = Field(..., description="Key type (EC)")
    crv: str = Field(..., description="Curve name (P-256)")
    x: str = Field(..., description="X coordinate (base64url)")
    y: str = Field(..., description="Y coordinate (base64url)")
    use: str = Field(..., description="Key use (sig)")
    alg: str = Field(..., description="Algorithm (ES256)")
    issuer: str = Field(..., description="Issuing country (ISO 3166-1 alpha-3)")
    role: str = Field(..., description="Key role (CMC, VISA, etc.)")
    not_before: str = Field(..., description="Validity start (ISO 8601)")
    not_after: str = Field(..., description="Validity end (ISO 8601)")
    status: str = Field(..., description="Key status")
    rotation_generation: int = Field(..., description="Rotation generation number")


class VDSNCKeysMetadata(BaseModel):
    """Metadata for VDS-NC keys response."""

    last_updated: str = Field(..., description="Last update timestamp")
    next_update: str | None = Field(None, description="Next scheduled update")
    total_count: int = Field(..., description="Total number of keys")
    country: str | None = Field(None, description="Country code filter applied")
    role: str | None = Field(None, description="Role filter applied")


class VDSNCKeysResponse(BaseModel):
    """Response containing VDS-NC public keys (JWKS format)."""

    keys: list[VDSNCKeyResponse] = Field(..., description="List of public keys")
    metadata: VDSNCKeysMetadata = Field(..., description="Response metadata")


class UnifiedTrustStoreResponse(BaseModel):
    """Unified response containing both DSC certificates and VDS-NC keys."""

    country: str
    csca_certificates: list[dict] = Field(default_factory=list)
    dsc_certificates: list[dict] = Field(default_factory=list)
    vds_nc_keys: list[VDSNCKeyResponse] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


# Dependency injection
async def get_db_session() -> AsyncSession:
    """Get database session (placeholder)."""
    # In production, this would get session from dependency injection container
    raise HTTPException(status_code=501, detail="Database session not configured")


async def get_key_manager(
    session: AsyncSession = Depends(get_db_session),
) -> DatabaseVDSNCKeyManager:
    """Get database-backed VDS-NC key manager instance."""
    return DatabaseVDSNCKeyManager(session)


async def get_key_repository(session: AsyncSession = Depends(get_db_session)) -> VDSNCKeyRepository:
    """Get VDS-NC key repository instance."""
    return VDSNCKeyRepository(session)


# Endpoints
@router.get(
    "/vds-nc-keys/{country_code}",
    response_model=VDSNCKeysResponse,
    summary="Get VDS-NC keys for a country",
    description="Retrieve all active VDS-NC signer public keys for a specific country",
)
async def get_vds_nc_keys_by_country(
    country_code: str = Path(
        ...,
        description="ISO 3166-1 alpha-3 country code (e.g., USA, FRA, DEU)",
        min_length=3,
        max_length=3,
        regex="^[A-Z]{3}$",
    ),
    role: str | None = Query(
        None,
        description="Filter by role (CMC, VISA, ETD, etc.)",
    ),
    manager: DatabaseVDSNCKeyManager = Depends(get_key_manager),
) -> VDSNCKeysResponse:
    """Get VDS-NC public keys for specific country.

    Returns JWKS-compatible format with all active keys for verification.
    Includes keys in overlap period during rotation.
    """
    try:
        # Convert role string to enum if provided
        role_enum = KeyRole[role.upper()] if role else None

        # Get JWKS document
        jwks_data = await manager.get_jwks_for_distribution(
            issuer_country=country_code.upper(), role=role_enum
        )

        if not jwks_data.get("keys"):
            raise HTTPException(
                status_code=404,
                detail=f"No VDS-NC keys found for country {country_code}"
                + (f" and role {role}" if role else ""),
            )

        # Convert to response format
        keys = []
        for jwk in jwks_data["keys"]:
            keys.append(
                VDSNCKeyResponse(
                    kid=jwk["kid"],
                    kty=jwk["kty"],
                    crv=jwk["crv"],
                    x=jwk["x"],
                    y=jwk["y"],
                    use=jwk["use"],
                    alg=jwk["alg"],
                    issuer=jwk["country"],
                    role=jwk["role"],
                    not_before=jwk.get("nbf", ""),
                    not_after=jwk.get("exp", ""),
                    status="active",
                    rotation_generation=1,
                )
            )

        metadata = VDSNCKeysMetadata(
            last_updated=jwks_data["metadata"]["last_updated"],
            next_update=jwks_data["metadata"].get("next_update"),
            total_count=jwks_data["metadata"]["total_count"],
            country=country_code,
            role=role,
        )

        return VDSNCKeysResponse(keys=keys, metadata=metadata)

    except KeyError:
        raise HTTPException(status_code=400, detail=f"Invalid role: {role}") from None
    except Exception as e:
        logger.exception("Error retrieving VDS-NC keys")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve VDS-NC keys: {e!s}") from e


@router.get(
    "/vds-nc-keys/all",
    response_model=VDSNCKeysResponse,
    summary="Get all VDS-NC keys",
    description="Retrieve all active VDS-NC signer public keys from all countries",
)
async def get_all_vds_nc_keys(
    role: str | None = Query(None, description="Filter by role"),
    status: str | None = Query(None, description="Filter by status (active, rotating)"),
    distributor: VDSNCKeyDistributor = Depends(get_key_distributor),
) -> VDSNCKeysResponse:
    """Get all VDS-NC public keys across all countries.

    Useful for initial trust list population or bulk refresh.
    """
    try:
        role_enum = KeyRole[role.upper()] if role else None

        jwks_data = await distributor.get_jwks(issuer_country=None, role=role_enum)

        return VDSNCKeysResponse(**jwks_data)

    except KeyError:
        raise HTTPException(status_code=400, detail=f"Invalid role: {role}")
    except Exception as e:
        logger.exception("Error retrieving all VDS-NC keys")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve VDS-NC keys: {e!s}")


@router.get(
    "/vds-nc-keys/key/{kid}",
    response_model=VDSNCKeyResponse,
    summary="Get VDS-NC key by KID",
    description="Retrieve a specific VDS-NC key by its key identifier",
)
async def get_vds_nc_key_by_kid(
    kid: str = Path(..., description="Key identifier"),
    distributor: VDSNCKeyDistributor = Depends(get_key_distributor),
) -> VDSNCKeyResponse:
    """Get single VDS-NC key by key identifier.

    Used when verifier encounters unknown KID and needs to fetch it.
    """
    try:
        key_data = await distributor.get_key_by_kid(kid)

        if not key_data:
            raise HTTPException(status_code=404, detail=f"VDS-NC key not found: {kid}")

        return VDSNCKeyResponse(**key_data)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error retrieving VDS-NC key {kid}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve key: {e!s}")


@router.get(
    "/trust-store/{country_code}",
    response_model=UnifiedTrustStoreResponse,
    summary="Get unified trust store",
    description="Retrieve complete trust store including CSCAs, DSCs, and VDS-NC keys",
)
async def get_unified_trust_store(
    country_code: str = Path(
        ...,
        description="ISO 3166-1 alpha-3 country code",
        min_length=3,
        max_length=3,
        regex="^[A-Z]{3}$",
    ),
    distributor: VDSNCKeyDistributor = Depends(get_key_distributor),
) -> UnifiedTrustStoreResponse:
    """Get unified trust store with all trust materials for a country.

    Combines:
    - CSCA certificates (chip/LDS trust roots)
    - DSC certificates (document signers)
    - VDS-NC signer keys (barcode verification)

    Single endpoint for complete trust establishment.
    """
    try:
        # Get VDS-NC keys
        vds_nc_jwks = await distributor.get_jwks(issuer_country=country_code.upper())

        # TODO: Get DSC certificates from DSC service
        # dsc_certs = await dsc_service.get_certificates(country_code)

        # TODO: Get CSCA certificates from trust anchor
        # csca_certs = await trust_anchor.get_csca_certificates(country_code)

        return UnifiedTrustStoreResponse(
            country=country_code,
            csca_certificates=[],  # TODO: Populate from trust anchor
            dsc_certificates=[],  # TODO: Populate from DSC service
            vds_nc_keys=vds_nc_jwks.get("keys", []),
            metadata={
                "last_updated": vds_nc_jwks.get("metadata", {}).get("last_updated"),
                "format_version": "1.0",
                "components": ["vds_nc_keys"],  # Add more as implemented
            },
        )

    except Exception as e:
        logger.exception(f"Error retrieving unified trust store: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve trust store: {e!s}")


@router.get(
    "/vds-nc-keys/{country_code}/revocation-list",
    summary="Get VDS-NC key revocation list",
    description="Retrieve revoked VDS-NC keys for a country",
)
async def get_vds_nc_revocation_list(
    country_code: str = Path(..., description="ISO 3166-1 alpha-3 country code"),
    manager: VDSNCKeyManager = Depends(get_key_manager),
) -> dict:
    """Get revoked VDS-NC keys.

    Similar to CRL for certificates, provides list of revoked keys.
    """
    try:
        revoked_keys = await manager.list_keys(
            issuer_country=country_code.upper(), status=KeyStatus.REVOKED
        )

        return {
            "country": country_code,
            "revoked_keys": [
                {
                    "kid": key.kid,
                    "revoked_at": key.revoked_at.isoformat() if key.revoked_at else None,
                    "revocation_reason": key.revocation_reason,
                    "role": key.role.value,
                }
                for key in revoked_keys
            ],
            "metadata": {
                "total_revoked": len(revoked_keys),
                "last_updated": "2025-10-01T12:00:00Z",  # TODO: Track actual update time
            },
        }

    except Exception as e:
        logger.exception(f"Error retrieving revocation list: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve revocation list: {e!s}")


# Health check
@router.get("/health", summary="Health check", tags=["Health"])
async def health_check() -> dict:
    """Health check endpoint for PKD service."""
    return {"status": "healthy", "service": "PKD VDS-NC Key Distribution"}


# OpenAPI metadata
def get_router_metadata() -> dict:
    """Get router metadata for OpenAPI documentation."""
    return {
        "title": "PKD VDS-NC Key Distribution API",
        "description": """
## PKD Public Key Distribution for VDS-NC

This API provides distribution of VDS-NC signer public keys according to
ICAO Doc 9303 Part 13 and the unified trust protocol.

### Key Features
- JWKS-compatible key distribution
- Support for key rotation with overlap periods
- Country and role-based filtering
- Individual key lookup by KID
- Revocation list support
- Unified trust store endpoint

### Trust Model
VDS-NC uses direct trust (no CA hierarchy). Verifiers fetch public keys
from this PKD service and validate barcode signatures directly.

### Key Lifecycle
Keys support rotation with overlap periods where multiple keys are valid
simultaneously. Verifiers should fetch:
- Active keys (current signing keys)
- Rotating keys (during overlap period)
- Recently deprecated keys (grace period for verification)

### Integration
1. Initial fetch: Get all keys for countries of interest
2. Periodic refresh: Update trust list every 24 hours
3. On-demand fetch: Get specific key by KID when unknown
4. Revocation check: Verify keys not in revocation list

### Fail-Closed Verification
Verifiers MUST reject signatures from unknown or untrusted keys.
This service provides authoritative trust information.
        """,
        "version": "1.0.0",
        "contact": {
            "name": "Marty Identity Platform",
            "email": "support@marty.example.com",
        },
    }
