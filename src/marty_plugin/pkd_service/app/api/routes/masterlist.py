"""
API endpoints for ICAO PKD Master List operations
"""

from __future__ import annotations

import io

from app.api.dependencies import get_masterlist_service
from app.models.pkd_models import MasterListResponse, MasterListUploadResponse
from app.services.masterlist_service import MasterListService
from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import StreamingResponse

router = APIRouter()


@router.get("/", response_model=MasterListResponse)
async def get_master_list(
    country: str | None = None, service: MasterListService = Depends(get_masterlist_service)
):
    """
    Get the Master List in JSON format, optionally filtered by country.

    - **country**: Optional three-letter country code (ISO 3166-1 alpha-3)
    """
    return await service.get_master_list(country)


@router.get("/download", response_class=StreamingResponse)
async def download_master_list(
    country: str | None = None, service: MasterListService = Depends(get_masterlist_service)
):
    """
    Download the Master List in ASN.1 binary format, optionally filtered by country.

    - **country**: Optional three-letter country code (ISO 3166-1 alpha-3)
    """
    master_list_data = await service.get_master_list_binary(country)

    # Return binary data with appropriate content type
    return StreamingResponse(
        io.BytesIO(master_list_data),
        media_type="application/octet-stream",
        headers={"Content-Disposition": "attachment; filename=masterlist.ml"},
    )


@router.post("/upload", response_model=MasterListUploadResponse)
async def upload_master_list(
    master_list_file: UploadFile = File(...),
    service: MasterListService = Depends(get_masterlist_service),
):
    """
    Upload a Master List in ASN.1 binary format for processing and storage.

    - **master_list_file**: The ASN.1 encoded Master List file
    """
    # Read the uploaded file
    content = await master_list_file.read()

    # Process the Master List data
    return await service.upload_master_list(content)
