"""
Status List REST API Router

Serves BitstringStatusListCredential VCs that verifiers fetch to check
credential revocation/suspension status.

W3C Bitstring Status List v1.0 §5.2: "The statusListCredential value MUST
be a URL to a Verifiable Credential."
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["status-list"])

# ============================================================================
# Dependency Injection (same pattern as credential_router)
# ============================================================================

_status_list_service: Any | None = None


def set_status_list_service(service: Any) -> None:
    """Set status list service instance (called from plugin initialization)."""
    global _status_list_service
    _status_list_service = service


async def _get_service() -> Any:
    if _status_list_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Status list service not available",
        )
    return _status_list_service


# ============================================================================
# Endpoints
# ============================================================================


@router.get(
    "/{issuer_id}/credentials/status/{shard_id}",
    summary="Get status list credential",
    description=(
        "Returns the BitstringStatusListCredential for a given shard. "
        "Verifiers fetch this to check whether a credential has been revoked "
        "or suspended."
    ),
    response_class=JSONResponse,
)
async def get_status_list_credential(
    issuer_id: str,
    shard_id: str,
) -> JSONResponse:
    """
    Serve the BitstringStatusListCredential VC for a shard.

    This is the endpoint that verifiers resolve when they encounter a
    ``credentialStatus.statusListCredential`` URL in a credential.

    Returns the unsigned VC with Content-Type application/vc+ld+json.
    """
    service = await _get_service()

    try:
        vc = await service.get_status_list_credential(
            shard_id=shard_id,
            issuer_did=issuer_id,
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Status list shard not found: {shard_id}",
        )

    return JSONResponse(
        content=vc,
        media_type="application/vc+ld+json",
        headers={
            "Cache-Control": "public, max-age=300",
        },
    )
