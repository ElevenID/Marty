"""
API endpoints for ICAO PKD Document Signer Certificate (DSC) List operations
"""

from __future__ import annotations

import io

from app.api.dependencies import get_dsclist_service
from app.models.pkd_models import DSCListResponse, DSCListUploadResponse
from app.services.dsclist_service import DSCListService
from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import StreamingResponse

router = APIRouter()


@router.get("/", response_model=DSCListResponse)
async def get_dsc_list(
    country: str | None = None, service: DSCListService = Depends(get_dsclist_service)
):
    """
    Get the Document Signer Certificate List in JSON format, optionally filtered by country.

    - **country**: Optional three-letter country code (ISO 3166-1 alpha-3)
    """
    return await service.get_dsc_list(country)


@router.get("/download", response_class=StreamingResponse)
async def download_dsc_list(
    country: str | None = None, service: DSCListService = Depends(get_dsclist_service)
):
    """
    Download the DSC List in ASN.1 binary format, optionally filtered by country.

    - **country**: Optional three-letter country code (ISO 3166-1 alpha-3)
    """
    dsc_list_data = await service.get_dsc_list_binary(country)

    # Return binary data with appropriate content type
    return StreamingResponse(
        io.BytesIO(dsc_list_data),
        media_type="application/octet-stream",
        headers={"Content-Disposition": "attachment; filename=dsclist.dl"},
    )


@router.post("/upload", response_model=DSCListUploadResponse)
async def upload_dsc_list(
    dsc_list_file: UploadFile = File(...), service: DSCListService = Depends(get_dsclist_service)
):
    """
    Upload a DSC List in ASN.1 binary format for processing and storage.

    - **dsc_list_file**: The ASN.1 encoded Document Signer Certificate List file
    """
    # Read the uploaded file
    content = await dsc_list_file.read()

    # Process the DSC List data
    return await service.upload_dsc_list(content)
