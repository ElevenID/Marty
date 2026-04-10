"""
API endpoints for CSCA & Master List Management
"""

from __future__ import annotations

import logging
from typing import Any

from app.controllers.csca_manager import CscaManager
from app.models.pkd_models import MasterListResponse, MasterListUploadResponse, VerificationResult
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response

from app.api.deps import verify_api_key

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
        logger.exception("Error retrieving master list")
        raise HTTPException(status_code=500, detail="Error retrieving master list")


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
        logger.exception("Error retrieving binary master list")
        raise HTTPException(status_code=500, detail="Error retrieving binary master list")


@router.post("/masterlist", response_model=MasterListUploadResponse)
async def upload_master_list(
    file: UploadFile = File(...),
    _: bool = Depends(verify_api_key),
):
    """
    Upload an ASN.1 encoded CSCA Master List.

    Args:
        file: The master list file to upload

    Returns:
        Upload response with status
    """
    try:
        contents = await file.read(20 * 1024 * 1024 + 1)
        if len(contents) > 20 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Upload exceeds 20 MB limit")
        return await csca_manager.upload_master_list(contents)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error uploading master list")
        raise HTTPException(status_code=500, detail="Error uploading master list")


@router.post("/sync", response_model=dict[str, Any])
async def trigger_synchronization(
    source_id: str | None = None,
    _: bool = Depends(verify_api_key),
):
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
        logger.exception("Error triggering synchronization")
        raise HTTPException(status_code=500, detail="Error triggering synchronization")


@router.post("/verify", response_model=VerificationResult)
async def verify_certificate(
    file: UploadFile = File(...),
    _: bool = Depends(verify_api_key),
):
    """
    Verify a certificate against the local trust store.

    Args:
        file: The certificate file to verify

    Returns:
        Verification result with status and details
    """
    try:
        certificate_data = await file.read(10 * 1024 * 1024 + 1)
        if len(certificate_data) > 10 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Upload exceeds 10 MB limit")
        return await csca_manager.verify_certificate(certificate_data)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error verifying certificate")
        raise HTTPException(status_code=500, detail="Error verifying certificate")


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
        logger.exception("Error checking for expiring certificates")
        raise HTTPException(
            status_code=500, detail="Error checking for expiring certificates"
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
        logger.exception("Error getting CSCA status")
        raise HTTPException(status_code=500, detail="Error getting CSCA status")


@router.get("/health", response_model=dict[str, str])
async def health_check():
    """
    Health check endpoint for CSCA & Master List Management.

    Returns:
        Health status
    """
    return {"status": "healthy"}
