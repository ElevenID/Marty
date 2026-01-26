"""
Issuer Registry and Cascade Operations API Router

Endpoints for issuer lifecycle management and cascade revocation operations.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from digital_identity.infrastructure.adapters.rest.schemas import (
    IssuerCreate,
    IssuerUpdate,
    IssuerResponse,
    CascadeOperationConfirm,
    CascadeOperationRollback,
    CascadeOperationResponse,
    ErrorResponse,
)
from digital_identity.infrastructure.adapters.rest.dependencies import (
    get_issuer_registry_service,
)

logger = logging.getLogger(__name__)


# =========================================================
# Issuer Registry Router
# =========================================================

issuer_router = APIRouter(
    prefix="/v1/identity/issuers",
    tags=["Issuer Registry"],
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)


@issuer_router.post(
    "",
    response_model=IssuerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register Issuer",
    description="Register a new issuer in the registry.",
)
async def register_issuer(
    data: IssuerCreate,
    service=Depends(get_issuer_registry_service),
) -> IssuerResponse:
    """Register a new issuer."""
    try:
        issuer = await service.register_issuer(**data.model_dump())
        return _issuer_to_response(issuer)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception("Failed to register issuer")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@issuer_router.get(
    "",
    response_model=list[IssuerResponse],
    summary="List Issuers",
    description="List issuers with optional filtering by organization.",
)
async def list_issuers(
    organization_id: str | None = Query(default=None, description="Filter by organization ID"),
    include_system: bool = Query(default=True, description="Include system issuers"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    service=Depends(get_issuer_registry_service),
) -> list[IssuerResponse]:
    """List issuers."""
    try:
        issuers = await service.list_issuers(
            organization_id=organization_id,
            include_system=include_system,
            skip=skip,
            limit=limit,
        )
        return [_issuer_to_response(i) for i in issuers]
    except Exception as e:
        logger.exception("Failed to list issuers")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@issuer_router.get(
    "/{issuer_id}",
    response_model=IssuerResponse,
    summary="Get Issuer",
    description="Get a specific issuer by ID.",
)
async def get_issuer(
    issuer_id: str,
    service=Depends(get_issuer_registry_service),
) -> IssuerResponse:
    """Get issuer by ID."""
    try:
        issuer = await service.get_issuer(issuer_id)
        if not issuer:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issuer not found")
        return _issuer_to_response(issuer)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get issuer")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@issuer_router.patch(
    "/{issuer_id}",
    response_model=IssuerResponse,
    summary="Update Issuer",
    description="Update issuer information.",
)
async def update_issuer(
    issuer_id: str,
    data: IssuerUpdate,
    service=Depends(get_issuer_registry_service),
) -> IssuerResponse:
    """Update an issuer."""
    try:
        issuer = await service.update_issuer(issuer_id, **data.model_dump(exclude_none=True))
        if not issuer:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issuer not found")
        return _issuer_to_response(issuer)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception("Failed to update issuer")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@issuer_router.post(
    "/{issuer_id}/revoke",
    response_model=CascadeOperationResponse,
    summary="Revoke Issuer",
    description="Revoke an issuer and create cascade operation for dependent credentials.",
)
async def revoke_issuer(
    issuer_id: str,
    reason: str = Query(..., description="Revocation reason"),
    revoked_by: str = Query(..., description="Who initiated revocation"),
    cascade_policy: str | None = Query(default=None, description="Override cascade policy"),
    service=Depends(get_issuer_registry_service),
) -> CascadeOperationResponse:
    """Revoke an issuer."""
    try:
        operation = await service.revoke_issuer(
            issuer_id=issuer_id,
            reason=reason,
            revoked_by=revoked_by,
            cascade_policy=cascade_policy,
        )
        return _cascade_operation_to_response(operation)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception("Failed to revoke issuer")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@issuer_router.post(
    "/{issuer_id}/suspend",
    response_model=IssuerResponse,
    summary="Suspend Issuer",
    description="Suspend an issuer (reversible).",
)
async def suspend_issuer(
    issuer_id: str,
    reason: str = Query(..., description="Suspension reason"),
    service=Depends(get_issuer_registry_service),
) -> IssuerResponse:
    """Suspend an issuer."""
    try:
        issuer = await service.suspend_issuer(issuer_id, reason)
        if not issuer:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issuer not found")
        return _issuer_to_response(issuer)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception("Failed to suspend issuer")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@issuer_router.post(
    "/{issuer_id}/reinstate",
    response_model=IssuerResponse,
    summary="Reinstate Issuer",
    description="Reinstate a suspended issuer.",
)
async def reinstate_issuer(
    issuer_id: str,
    service=Depends(get_issuer_registry_service),
) -> IssuerResponse:
    """Reinstate a suspended issuer."""
    try:
        issuer = await service.reinstate_issuer(issuer_id)
        if not issuer:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issuer not found")
        return _issuer_to_response(issuer)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception("Failed to reinstate issuer")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


def _issuer_to_response(issuer) -> IssuerResponse:
    """Convert issuer entity to response schema."""
    return IssuerResponse(
        id=issuer.id,
        issuer_id=issuer.issuer_id,
        display_name=issuer.display_name,
        issuer_type=issuer.issuer_type,
        description=issuer.description,
        organization_id=issuer.organization_id,
        trust_anchor_id=issuer.trust_anchor_id,
        is_system_issuer=issuer.is_system_issuer,
        compliance_status=issuer.compliance_status,
        accreditation_body=issuer.accreditation_body,
        accreditation_date=issuer.accreditation_date,
        valid_from=issuer.valid_from,
        valid_until=issuer.valid_until,
        revoked_at=issuer.revoked_at,
        revocation_reason=issuer.revocation_reason,
        revoked_by=issuer.revoked_by,
        metadata=issuer.metadata,
        created_at=issuer.created_at,
        updated_at=issuer.updated_at,
        version=issuer.version,
    )


# =========================================================
# Cascade Operations Router
# =========================================================

cascade_router = APIRouter(
    prefix="/v1/identity/cascade-operations",
    tags=["Cascade Operations"],
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)


@cascade_router.get(
    "/{operation_id}",
    response_model=CascadeOperationResponse,
    summary="Get Cascade Operation",
    description="Get cascade operation status and details.",
)
async def get_cascade_operation(
    operation_id: str,
    service=Depends(get_issuer_registry_service),
) -> CascadeOperationResponse:
    """Get cascade operation."""
    try:
        operation = await service.get_cascade_operation(operation_id)
        if not operation:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cascade operation not found")
        return _cascade_operation_to_response(operation)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get cascade operation")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@cascade_router.post(
    "/{operation_id}/confirm",
    response_model=CascadeOperationResponse,
    summary="Confirm Cascade Operation",
    description="Confirm and execute a high-impact cascade operation.",
)
async def confirm_cascade_operation(
    operation_id: str,
    data: CascadeOperationConfirm,
    service=Depends(get_issuer_registry_service),
) -> CascadeOperationResponse:
    """Confirm cascade operation."""
    try:
        operation = await service.confirm_cascade(operation_id, data.confirmed_by)
        return _cascade_operation_to_response(operation)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception("Failed to confirm cascade operation")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@cascade_router.post(
    "/{operation_id}/rollback",
    response_model=CascadeOperationResponse,
    summary="Rollback Cascade Operation",
    description="Roll back a completed cascade operation.",
)
async def rollback_cascade_operation(
    operation_id: str,
    data: CascadeOperationRollback,
    service=Depends(get_issuer_registry_service),
) -> CascadeOperationResponse:
    """Rollback cascade operation."""
    try:
        operation = await service.rollback_cascade(operation_id, data.rolled_back_by)
        return _cascade_operation_to_response(operation)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception("Failed to rollback cascade operation")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@cascade_router.get(
    "/{operation_id}/status",
    response_model=dict[str, Any],
    summary="Get Cascade Operation Status",
    description="Get simple status summary of a cascade operation.",
)
async def get_cascade_operation_status(
    operation_id: str,
    service=Depends(get_issuer_registry_service),
) -> dict[str, Any]:
    """Get cascade operation status summary."""
    try:
        operation = await service.get_cascade_operation(operation_id)
        if not operation:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cascade operation not found")
        
        return {
            "operation_id": operation.id,
            "status": operation.status,
            "affected_count": operation.affected_credential_count,
            "requires_confirmation": operation.requires_confirmation,
            "can_rollback": operation.can_be_rolled_back(),
            "circuit_breaker_triggered": operation.circuit_breaker_triggered,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get cascade operation status")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


def _cascade_operation_to_response(operation) -> CascadeOperationResponse:
    """Convert cascade operation entity to response schema."""
    return CascadeOperationResponse(
        id=operation.id,
        operation_type=operation.operation_type,
        trigger_entity_type=operation.trigger_entity_type,
        trigger_entity_id=operation.trigger_entity_id,
        status=operation.status,
        affected_credential_count=operation.affected_credential_count,
        affected_credential_ids=operation.affected_credential_ids,
        requires_confirmation=operation.requires_confirmation,
        confirmed_at=operation.confirmed_at,
        confirmed_by=operation.confirmed_by,
        max_cascade_depth=operation.max_cascade_depth,
        current_depth=operation.current_depth,
        circuit_breaker_threshold=operation.circuit_breaker_threshold,
        circuit_breaker_triggered=operation.circuit_breaker_triggered,
        can_rollback=operation.can_rollback,
        rolled_back_at=operation.rolled_back_at,
        rolled_back_by=operation.rolled_back_by,
        error_message=operation.error_message,
        metadata=operation.metadata,
        created_at=operation.created_at,
        updated_at=operation.updated_at,
        version=operation.version,
    )
