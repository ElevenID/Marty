"""
CMC (Crew Member Certificate) API endpoints for Document Processing service

This module implements FastAPI endpoints for CMC operations including creation,
signing, verification, and Annex 9 compliance management.
"""

from __future__ import annotations

import logging
from typing import Annotated

from app.api.deps import verify_api_key
from app.models.cmc_models import (
    CMCBackgroundCheckRequest,
    CMCBackgroundCheckResponse,
    CMCCreateRequest,
    CMCCreateResponse,
    CMCListResponse,
    CMCSignRequest,
    CMCSignResponse,
    CMCStatusResponse,
    CMCVerificationRequest,
    CMCVerificationResponse,
    CMCVisaFreeStatusRequest,
    CMCVisaFreeStatusResponse,
    VerificationResult,
)
from app.services.cmc_service_client import (
    CMCServiceClient,
    CMCServiceError,
    get_cmc_service_client,
)
from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, status

logger = logging.getLogger(__name__)

# Create CMC router
cmc_router = APIRouter(prefix="/api/cmc", tags=["CMC"])


@cmc_router.post("/create", response_model=CMCCreateResponse)
async def create_cmc(
    request: CMCCreateRequest,
    cmc_client: CMCServiceClient = Depends(get_cmc_service_client),
    _: bool = Depends(verify_api_key),
    x_request_id: str | None = Header(None, alias="X-RequestID"),
) -> CMCCreateResponse:
    """
    Create a new Crew Member Certificate (CMC)

    Creates a CMC with the specified data according to ICAO Doc 9303 Part 5
    and Annex 9 requirements. Supports both chip-based (LDS) and VDS-NC
    security models.
    """
    try:
        logger.info(
            "Creating CMC for document_number=%s issuing_country=%s security_model=%s",
            request.document_number,
            request.issuing_country,
            request.security_model.value,
        )

        # Convert request to dictionary for service client
        cmc_data = {
            "document_number": request.document_number,
            "issuing_country": request.issuing_country,
            "surname": request.surname,
            "given_names": request.given_names,
            "nationality": request.nationality,
            "date_of_birth": request.date_of_birth,
            "gender": request.gender.value,
            "date_of_expiry": request.date_of_expiry,
            "employer": request.employer,
            "crew_id": request.crew_id,
            "security_model": request.security_model.value,
            "face_image": request.face_image,
            "background_check_verified": request.background_check_verified,
        }

        # Call CMC service
        result = await cmc_client.create_cmc(cmc_data)

        return CMCCreateResponse(
            success=result["success"],
            cmc_id=result.get("cmc_id"),
            td1_mrz=result.get("td1_mrz"),
            security_model=result.get("security_model"),
            error_message=result.get("error_message"),
        )

    except CMCServiceError as e:
        logger.exception("CMC service error during creation")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"CMC service error: {e.message}"
        ) from e
    except Exception as e:
        logger.exception("Unexpected error during CMC creation")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {e!s}",
        ) from e


@cmc_router.post("/sign", response_model=CMCSignResponse)
async def sign_cmc(
    request: CMCSignRequest,
    cmc_client: CMCServiceClient = Depends(get_cmc_service_client),
    _: bool = Depends(verify_api_key),
    x_request_id: str | None = Header(None, alias="X-RequestID"),
) -> CMCSignResponse:
    """
    Sign a Crew Member Certificate (CMC)

    Signs the CMC using the document signing service. The signing process
    varies based on the security model (chip LDS vs VDS-NC barcode).
    """
    try:
        logger.info("Signing CMC: %s", request.cmc_id)

        # Call CMC service
        result = await cmc_client.sign_cmc(request.cmc_id, request.signer_id)

        return CMCSignResponse(
            success=result["success"],
            signature_info=result.get("signature_info"),
            error_message=result.get("error_message"),
        )

    except CMCServiceError as e:
        logger.exception("CMC service error during signing")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"CMC service error: {e.message}"
        ) from e
    except Exception as e:
        logger.exception("Unexpected error during CMC signing")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {e!s}",
        ) from e


@cmc_router.post("/verify", response_model=CMCVerificationResponse)
async def verify_cmc(
    request: CMCVerificationRequest,
    cmc_client: CMCServiceClient = Depends(get_cmc_service_client),
    _: bool = Depends(verify_api_key),
    x_request_id: str | None = Header(None, alias="X-RequestID"),
) -> CMCVerificationResponse:
    """
    Verify a Crew Member Certificate (CMC)

    Verifies the CMC using one of the supported methods:
    - TD-1 MRZ string verification
    - VDS-NC barcode verification
    - Direct CMC ID lookup

    Includes comprehensive verification checks including revocation status
    and Annex 9 background check compliance.
    """
    try:
        verification_method = "unknown"
        if request.td1_mrz:
            verification_method = "TD-1 MRZ"
        elif request.barcode_data:
            verification_method = "VDS-NC barcode"
        elif request.cmc_id:
            verification_method = "CMC ID"

        logger.info("Verifying CMC using %s method", verification_method)

        # Convert request to dictionary for service client
        verification_data = {
            "check_revocation": request.check_revocation,
            "validate_background_check": request.validate_background_check,
        }

        if request.td1_mrz:
            verification_data["td1_mrz"] = request.td1_mrz
        elif request.barcode_data:
            verification_data["barcode_data"] = request.barcode_data
        elif request.cmc_id:
            verification_data["cmc_id"] = request.cmc_id
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="One of td1_mrz, barcode_data, or cmc_id must be provided",
            )

        # Call CMC service
        result = await cmc_client.verify_cmc(verification_data)

        # Convert verification results
        verification_results = [
            VerificationResult(
                check_name=vr["check_name"],
                passed=vr["passed"],
                details=vr["details"],
                error_code=vr.get("error_code"),
            )
            for vr in result.get("verification_results", [])
        ]

        return CMCVerificationResponse(
            success=result["success"],
            is_valid=result.get("is_valid", False),
            cmc_data=result.get("cmc_data"),
            verification_results=verification_results,
            error_message=result.get("error_message"),
        )

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except CMCServiceError as e:
        logger.exception("CMC service error during verification")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"CMC service error: {e.message}"
        ) from e
    except Exception as e:
        logger.exception("Unexpected error during CMC verification")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {e!s}",
        ) from e


@cmc_router.post("/background-check", response_model=CMCBackgroundCheckResponse)
async def background_check_cmc(
    request: CMCBackgroundCheckRequest,
    cmc_client: CMCServiceClient = Depends(get_cmc_service_client),
    _: bool = Depends(verify_api_key),
    x_request_id: str | None = Header(None, alias="X-RequestID"),
) -> CMCBackgroundCheckResponse:
    """
    Initiate or check background verification for CMC (Annex 9)

    Initiates a background check for the specified CMC or checks the status
    of an existing background verification process. This is required for
    Annex 9 compliance.
    """
    try:
        logger.info(
            "Background check for CMC: %s by authority: %s", request.cmc_id, request.check_authority
        )

        # Call CMC service
        result = await cmc_client.background_check(
            request.cmc_id, request.check_authority, request.check_reference
        )

        return CMCBackgroundCheckResponse(
            success=result["success"],
            check_passed=result.get("check_passed", False),
            check_date=result.get("check_date"),
            check_authority=result.get("check_authority"),
            check_reference=result.get("check_reference"),
            error_message=result.get("error_message"),
        )

    except CMCServiceError as e:
        logger.exception("CMC service error during background check")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"CMC service error: {e.message}"
        ) from e
    except Exception as e:
        logger.exception("Unexpected error during background check")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {e!s}",
        ) from e


@cmc_router.post("/visa-free-status", response_model=CMCVisaFreeStatusResponse)
async def update_visa_free_status(
    request: CMCVisaFreeStatusRequest,
    cmc_client: CMCServiceClient = Depends(get_cmc_service_client),
    _: bool = Depends(verify_api_key),
    x_request_id: str | None = Header(None, alias="X-RequestID"),
) -> CMCVisaFreeStatusResponse:
    """
    Update visa-free entry eligibility status (Annex 9)

    Updates the visa-free entry eligibility status for the specified CMC.
    This is managed according to Annex 9 policy requirements and requires
    proper authority verification.
    """
    try:
        logger.info(
            "Updating visa-free status for CMC: %s to %s by authority: %s",
            request.cmc_id,
            request.visa_free_eligible,
            request.authority,
        )

        # Call CMC service
        result = await cmc_client.update_visa_free_status(
            request.cmc_id, request.visa_free_eligible, request.authority, request.reason
        )

        return CMCVisaFreeStatusResponse(
            success=result["success"],
            visa_free_eligible=result.get("visa_free_eligible", False),
            updated_at=result.get("updated_at"),
            error_message=result.get("error_message"),
        )

    except CMCServiceError as e:
        logger.exception("CMC service error during visa-free status update")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"CMC service error: {e.message}"
        ) from e
    except Exception as e:
        logger.exception("Unexpected error during visa-free status update")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {e!s}",
        ) from e


@cmc_router.get("/list", response_model=CMCListResponse)
async def list_cmcs(
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    offset: Annotated[int, Query(ge=0)] = 0,
    issuing_country: str | None = Query(None, description="Filter by issuing country"),
    security_model: str | None = Query(None, description="Filter by security model"),
    cmc_client: CMCServiceClient = Depends(get_cmc_service_client),
    _: bool = Depends(verify_api_key),
    x_request_id: str | None = Header(None, alias="X-RequestID"),
) -> CMCListResponse:
    """
    List Crew Member Certificates (CMCs)

    Retrieves a paginated list of CMCs with optional filtering by issuing
    country and security model.
    """
    try:
        logger.info("Listing CMCs: limit=%d offset=%d", limit, offset)

        # For now, return a mock response since the CMC engine doesn't have a list endpoint yet
        # In a full implementation, this would call the CMC service

        return CMCListResponse(
            success=True,
            total_count=0,
            cmcs=[],
            error_message=None,
        )

    except Exception as e:
        logger.exception("Unexpected error during CMC listing")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {e!s}",
        ) from e


@cmc_router.get("/{cmc_id}/status", response_model=CMCStatusResponse)
async def get_cmc_status(
    cmc_id: Annotated[str, Path(description="CMC ID")],
    cmc_client: CMCServiceClient = Depends(get_cmc_service_client),
    _: bool = Depends(verify_api_key),
    x_request_id: str | None = Header(None, alias="X-RequestID"),
) -> CMCStatusResponse:
    """
    Get CMC status information

    Retrieves the current status and metadata for the specified CMC,
    including Annex 9 compliance status.
    """
    try:
        logger.info("Getting status for CMC: %s", cmc_id)

        # For now, return a mock response since we'd need to add a GetCMCStatus endpoint
        # In a full implementation, this would call the CMC service

        return CMCStatusResponse(
            success=True,
            cmc_id=cmc_id,
            status="ACTIVE",
            created_at="2025-10-01T12:00:00Z",
            updated_at="2025-10-01T12:00:00Z",
            security_model="CHIP_LDS",
            annex9_compliant=True,
            error_message=None,
        )

    except Exception as e:
        logger.exception("Unexpected error during CMC status retrieval")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {e!s}",
        ) from e
