"""
Credential REST API Router

Provides endpoints for credential issuance, verification, and revocation management.
Integrates with marty-credentials library for credential operations while maintaining
organizational context and compliance requirements.
"""
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from digital_identity.application.services.credential_issuance_service import (
    CredentialIssuanceService,
)
from digital_identity.domain.entities import IssuedCredential
from digital_identity.infrastructure.persistence.repositories import (
    CredentialRepository,
)


router = APIRouter(prefix="/v1/identity/credentials", tags=["credentials"])


# ============================================================================
# Request/Response Models
# ============================================================================


class IssueCredentialRequest(BaseModel):
    """Request to issue a credential."""

    credential_template_id: str = Field(..., description="Credential template ID")
    flow_execution_id: str | None = Field(None, description="Associated flow execution")
    subject_claims: dict[str, Any] = Field(..., description="Claims for the subject")
    holder_identifier: str = Field(..., description="Holder identifier (DID, email, etc.)")
    application_data: dict[str, Any] | None = Field(
        None, description="Application evidence and verification data"
    )


class IssueCredentialResponse(BaseModel):
    """Response from credential issuance."""

    credential_id: str = Field(..., description="Issued credential ID")
    credential: dict[str, Any] = Field(..., description="The actual credential (returned once)")
    credential_hash: str = Field(..., description="SHA-256 hash for audit")
    status_list_entries: list[dict[str, Any]] = Field(
        default_factory=list, description="Status list entry references"
    )
    issued_at: datetime = Field(..., description="Issuance timestamp")


class VerifyCredentialRequest(BaseModel):
    """Request to verify a credential."""

    credential: dict[str, Any] | str = Field(..., description="Credential to verify")
    presentation_policy_id: str | None = Field(None, description="Presentation policy to apply")
    trust_profile_id: str | None = Field(None, description="Trust profile for validation")


class VerifyCredentialResponse(BaseModel):
    """Response from credential verification."""

    valid: bool = Field(..., description="Whether credential is valid")
    verified_claims: dict[str, Any] | None = Field(None, description="Verified claims")
    errors: list[str] = Field(default_factory=list, description="Validation errors")
    verification_timestamp: datetime = Field(..., description="Verification timestamp")


class RevokeCredentialRequest(BaseModel):
    """Request to revoke a credential."""

    revocation_reason: str | None = Field(None, description="Reason for revocation")
    revocation_strategy: str = Field(
        "scheduled",
        description="'scheduled' (batch) or 'immediate' (privacy warning)",
    )


class BatchRevokeRequest(BaseModel):
    """Request to batch revoke credentials."""

    credential_ids: list[str] = Field(..., description="List of credential IDs to revoke")
    revocation_reason: str | None = Field(None, description="Reason for revocation")
    revocation_strategy: str = Field(
        "scheduled", description="'scheduled' (batch) or 'immediate'"
    )


class RevocationBatchStatus(BaseModel):
    """Status of a revocation batch."""

    batch_id: str
    credential_template_id: str
    credential_count: int
    status: str  # pending, processing, completed, failed
    scheduled_for: datetime | None
    completed_at: datetime | None
    revocation_interval: str  # 1h, 6h, 24h


class CredentialMetadata(BaseModel):
    """Metadata about an issued credential (no actual credential data)."""

    id: str
    credential_template_id: str
    organization_id: str
    flow_execution_id: str | None
    credential_hash: str
    status: str  # active, revoked, expired, suspended
    issued_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None


# ============================================================================
# Dependency Injection
# ============================================================================

# Global service instances (initialized in plugin)
_credential_issuance_service: CredentialIssuanceService | None = None
_credential_repository: CredentialRepository | None = None


def set_credential_services(
    issuance_service: CredentialIssuanceService,
    credential_repository: CredentialRepository,
) -> None:
    """Set credential service instances (called from plugin initialization)."""
    global _credential_issuance_service, _credential_repository
    _credential_issuance_service = issuance_service
    _credential_repository = credential_repository


async def get_credential_issuance_service() -> CredentialIssuanceService:
    """Get credential issuance service instance."""
    if _credential_issuance_service is None:
        raise RuntimeError("Credential issuance service not initialized. Call set_credential_services() in plugin.")
    return _credential_issuance_service


async def get_credential_repository() -> CredentialRepository:
    """Get credential repository instance."""
    if _credential_repository is None:
        raise RuntimeError("Credential repository not initialized. Call set_credential_services() in plugin.")
    return _credential_repository


async def get_organization_id(
    # TODO: Add authentication/authorization dependency
) -> str:
    """Extract organization ID from authenticated request."""
    # TODO: Implement from auth context
    # For now, return a default org ID for testing
    return "default-org-id"


# ============================================================================
# Endpoints
# ============================================================================


@router.post(
    "/issue",
    response_model=IssueCredentialResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Issue a credential",
    description="""
    Issues a credential based on a template and subject claims.
    
    The credential is returned in the response and not stored by the platform
    (spec privacy requirement). Only metadata (hash, status list entries) is
    retained for revocation management.
    
    Returns the credential once - holder wallet must store it.
    """,
)
async def issue_credential(
    request: IssueCredentialRequest,
    organization_id: Annotated[str, Depends(get_organization_id)],
    issuance_service: Annotated[
        CredentialIssuanceService, Depends(get_credential_issuance_service)
    ],
) -> IssueCredentialResponse:
    """Issue a credential and return it to the caller."""
    try:
        result = await issuance_service.issue_credential_from_request(
            organization_id=organization_id,
            credential_template_id=request.credential_template_id,
            flow_execution_id=request.flow_execution_id,
            subject_claims=request.subject_claims,
            holder_identifier=request.holder_identifier,
            application_data=request.application_data,
        )

        return IssueCredentialResponse(
            credential_id=result["credential_id"],
            credential=result["credential"],
            credential_hash=result["credential_hash"],
            status_list_entries=result.get("status_list_entries", []),
            issued_at=result["issued_at"],
        )

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Credential issuance failed: {str(e)}",
        )


@router.post(
    "/verify",
    response_model=VerifyCredentialResponse,
    summary="Verify a credential",
    description="""
    Verifies a credential's authenticity, validity, and revocation status.
    
    Optionally applies a presentation policy to validate required claims.
    Uses trust profile for issuer validation and status list checking.
    """,
)
async def verify_credential(
    request: VerifyCredentialRequest,
    organization_id: Annotated[str, Depends(get_organization_id)],
    issuance_service: Annotated[
        CredentialIssuanceService, Depends(get_credential_issuance_service)
    ],
) -> VerifyCredentialResponse:
    """Verify a credential."""
    try:
        result = await issuance_service.verify_credential(
            organization_id=organization_id,
            credential=request.credential,
            presentation_policy_id=request.presentation_policy_id,
            trust_profile_id=request.trust_profile_id,
        )

        return VerifyCredentialResponse(
            valid=result["valid"],
            verified_claims=result.get("verified_claims"),
            errors=result.get("errors", []),
            verification_timestamp=datetime.utcnow(),
        )

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Credential verification failed: {str(e)}",
        )


@router.get(
    "/{credential_id}",
    response_model=CredentialMetadata,
    summary="Get credential metadata",
    description="""
    Returns metadata about an issued credential.
    
    Does NOT return the actual credential (privacy requirement).
    Only returns audit information: hash, status, timestamps.
    """,
)
async def get_credential_metadata(
    credential_id: str,
    organization_id: Annotated[str, Depends(get_organization_id)],
    credential_repo: Annotated[CredentialRepository, Depends(get_credential_repository)],
) -> CredentialMetadata:
    """Get credential metadata by ID."""
    try:
        issued_credential = await credential_repo.get_by_id(
            credential_id, organization_id=organization_id
        )

        if not issued_credential:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Credential not found"
            )

        return CredentialMetadata(
            id=str(issued_credential.id),
            credential_template_id=str(issued_credential.credential_template_id),
            organization_id=str(issued_credential.organization_id),
            flow_execution_id=str(issued_credential.flow_execution_id)
            if issued_credential.flow_execution_id
            else None,
            credential_hash=issued_credential.credential_hash,
            status=issued_credential.status,
            issued_at=issued_credential.issued_at,
            expires_at=issued_credential.expires_at,
            revoked_at=issued_credential.revoked_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve credential: {str(e)}",
        )


@router.patch(
    "/{credential_id}/revoke",
    status_code=status.HTTP_200_OK,
    summary="Revoke a credential (immediate)",
    description="""
    Immediately revokes a credential.
    
    ⚠️ WARNING: Immediate revocation reveals which specific credential was revoked,
    potentially compromising holder privacy. Prefer batch revocation for privacy.
    
    Updates status list and publishes new status list credential.
    """,
)
async def revoke_credential(
    credential_id: str,
    request: RevokeCredentialRequest,
    organization_id: Annotated[str, Depends(get_organization_id)],
    issuance_service: Annotated[
        CredentialIssuanceService, Depends(get_credential_issuance_service)
    ],
) -> dict[str, Any]:
    """Revoke a single credential."""
    try:
        if request.revocation_strategy == "immediate":
            # Log privacy warning
            # TODO: Emit event for monitoring/compliance
            pass

        result = await issuance_service.revoke_credential(
            organization_id=organization_id,
            credential_id=credential_id,
            revocation_reason=request.revocation_reason,
            immediate=request.revocation_strategy == "immediate",
        )

        return {
            "credential_id": credential_id,
            "status": "revoked" if request.revocation_strategy == "immediate" else "queued",
            "revoked_at": result.get("revoked_at"),
            "batch_id": result.get("batch_id"),
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Credential revocation failed: {str(e)}",
        )


@router.post(
    "/revoke/batch",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Batch revoke credentials",
    description="""
    Queues multiple credentials for batch revocation.
    
    Scheduled batching (default) follows W3C Bitstring Status List privacy
    recommendations by grouping revocations. The batch interval is determined
    by the credential template configuration (1h/6h/24h).
    
    Immediate processing available but reduces privacy guarantees.
    """,
)
async def batch_revoke_credentials(
    request: BatchRevokeRequest,
    organization_id: Annotated[str, Depends(get_organization_id)],
    issuance_service: Annotated[
        CredentialIssuanceService, Depends(get_credential_issuance_service)
    ],
) -> dict[str, Any]:
    """Queue credentials for batch revocation."""
    try:
        result = await issuance_service.batch_revoke_credentials(
            organization_id=organization_id,
            credential_ids=request.credential_ids,
            revocation_reason=request.revocation_reason,
            immediate=request.revocation_strategy == "immediate",
        )

        return {
            "batch_id": result["batch_id"],
            "credential_count": len(request.credential_ids),
            "status": "processing" if request.revocation_strategy == "immediate" else "queued",
            "scheduled_for": result.get("scheduled_for"),
            "message": result.get("message"),
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Batch revocation failed: {str(e)}",
        )


@router.get(
    "/",
    response_model=list[CredentialMetadata],
    summary="List credential metadata",
    description="""
    Query credential metadata with filters.
    
    Returns only metadata (hashes, status), not actual credentials.
    Useful for dashboards, reporting, and revocation management.
    """,
)
async def list_credentials(
    organization_id: Annotated[str, Depends(get_organization_id)],
    credential_repo: Annotated[CredentialRepository, Depends(get_credential_repository)],
    flow_id: Annotated[str | None, Query()] = None,
    credential_template_id: Annotated[str | None, Query()] = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[CredentialMetadata]:
    """List credentials with optional filters."""
    try:
        credentials = await credential_repo.list_by_organization(
            organization_id=organization_id,
            flow_id=flow_id,
            credential_template_id=credential_template_id,
            status=status_filter,
            limit=limit,
            offset=offset,
        )

        return [
            CredentialMetadata(
                id=str(cred.id),
                credential_template_id=str(cred.credential_template_id),
                organization_id=str(cred.organization_id),
                flow_execution_id=str(cred.flow_execution_id) if cred.flow_execution_id else None,
                credential_hash=cred.credential_hash,
                status=cred.status,
                issued_at=cred.issued_at,
                expires_at=cred.expires_at,
                revoked_at=cred.revoked_at,
            )
            for cred in credentials
        ]

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list credentials: {str(e)}",
        )


@router.get(
    "/revocation-batches",
    response_model=list[RevocationBatchStatus],
    summary="List revocation batches",
    description="""
    Returns pending and completed revocation batches.
    
    Shows scheduled batch processing status per credential template.
    Useful for monitoring privacy-preserving batch revocation operations.
    """,
)
async def list_revocation_batches(
    organization_id: Annotated[str, Depends(get_organization_id)],
    issuance_service: Annotated[
        CredentialIssuanceService, Depends(get_credential_issuance_service)
    ],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
) -> list[RevocationBatchStatus]:
    """List revocation batches."""
    try:
        batches = await issuance_service.list_revocation_batches(
            organization_id=organization_id, status=status_filter
        )

        return [
            RevocationBatchStatus(
                batch_id=batch["batch_id"],
                credential_template_id=batch["credential_template_id"],
                credential_count=batch["credential_count"],
                status=batch["status"],
                scheduled_for=batch.get("scheduled_for"),
                completed_at=batch.get("completed_at"),
                revocation_interval=batch["revocation_interval"],
            )
            for batch in batches
        ]

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list revocation batches: {str(e)}",
        )


# TODO: Add presentation endpoints
# POST /v1/identity/presentations/create
# POST /v1/identity/presentations/verify
