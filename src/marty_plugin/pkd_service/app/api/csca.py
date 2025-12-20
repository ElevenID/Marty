"""
API endpoints for CSCA & Master List Management
"""

from __future__ import annotations

import logging
from typing import Any

from app.controllers.csca_manager import CscaManager
from app.models.pkd_models import MasterListResponse, MasterListUploadResponse, VerificationResult
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/csca", tags=["CSCA"])

# Global CscaManager instance
csca_manager = CscaManager()


@router.on_event("startup")
async def startup_event() -> None:
    """Start CSCA Manager services on API startup"""
    await csca_manager.start_services()


@router.on_event("shutdown")
async def shutdown_event() -> None:
    """Stop CSCA Manager services on API shutdown"""
    await csca_manager.stop_services()


@router.get("/masterlist", response_model=MasterListResponse)
async def get_master_list(country: str | None = None):
    """
    Retrieve the CSCA Master List, optionally filtered by country.

    Args:
        country: Optional country filter (ISO 3166-1 alpha-3 code)

    Returns:
        MasterListResponse containing certificates
    """
    try:
        return await csca_manager.get_master_list(country)
    except Exception as e:
        logger.exception(f"Error retrieving master list: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving master list: {e!s}")


@router.get("/masterlist/binary", response_class=Response)
async def get_master_list_binary(country: str | None = None):
    """
    Download the ASN.1 encoded CSCA Master List, optionally filtered by country.

    Args:
        country: Optional country filter (ISO 3166-1 alpha-3 code)

    Returns:
        ASN.1 encoded master list as binary data
    """
    try:
        master_list_data = await csca_manager.get_master_list_binary(country)
        return Response(
            content=master_list_data,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f"attachment; filename=masterlist{'-' + country if country else ''}.ml"
            },
        )
    except Exception as e:
        logger.exception(f"Error retrieving binary master list: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving binary master list: {e!s}")


@router.post("/masterlist", response_model=MasterListUploadResponse)
async def upload_master_list(file: UploadFile = File(...)):
    """
    Upload an ASN.1 encoded CSCA Master List.

    Args:
        file: The master list file to upload

    Returns:
        Upload response with status
    """
    try:
        contents = await file.read()
        return await csca_manager.upload_master_list(contents)
    except Exception as e:
        logger.exception(f"Error uploading master list: {e}")
        raise HTTPException(status_code=500, detail=f"Error uploading master list: {e!s}")


@router.post("/sync", response_model=dict[str, Any])
async def trigger_synchronization(source_id: str | None = None):
    """
    Trigger synchronization with trusted sources.

    Args:
        source_id: Optional specific source to sync with

    Returns:
        Synchronization results
    """
    try:
        return await csca_manager.trigger_sync(source_id)
    except Exception as e:
        logger.exception(f"Error triggering synchronization: {e}")
        raise HTTPException(status_code=500, detail=f"Error triggering synchronization: {e!s}")


@router.post("/verify", response_model=VerificationResult)
async def verify_certificate(file: UploadFile = File(...)):
    """
    Verify a certificate against the local trust store.

    Args:
        file: The certificate file to verify

    Returns:
        Verification result with status and details
    """
    try:
        certificate_data = await file.read()
        return await csca_manager.verify_certificate(certificate_data)
    except Exception as e:
        logger.exception(f"Error verifying certificate: {e}")
        raise HTTPException(status_code=500, detail=f"Error verifying certificate: {e!s}")


@router.get("/check-expiry", response_model=dict[str, Any])
async def check_expiring_certificates():
    """
    Check for certificates that are expiring soon.

    Returns:
        Check results with status
    """
    try:
        return await csca_manager.check_for_expiring_certificates()
    except Exception as e:
        logger.exception(f"Error checking for expiring certificates: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error checking for expiring certificates: {e!s}"
        )


@router.get("/status", response_model=dict[str, Any])
async def get_csca_status():
    """
    Get the status of CSCA & Master List Management services.

    Returns:
        Status information
    """
    try:
        # Get basic status information
        master_list = await csca_manager.get_master_list()

        return {
            "status": "active",
            "certificate_count": len(master_list.certificates),
            "countries": master_list.countries,
            "last_updated": str(master_list.created),
            "services": {
                "sync_service": csca_manager.sync_service.running,
                "certificate_monitor": csca_manager.certificate_monitor.running,
            },
        }
    except Exception as e:
        logger.exception(f"Error getting CSCA status: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting CSCA status: {e!s}")


@router.get("/health", response_model=dict[str, str])
async def health_check():
    """
    Health check endpoint for CSCA & Master List Management.

    Returns:
        Health status
    """
    return {"status": "healthy"}
