"""
API endpoints for ICAO PKD Deviation List operations
"""

from __future__ import annotations

import io

from app.api.dependencies import get_deviationlist_service
from app.models.pkd_models import DeviationListResponse, DeviationListUploadResponse
from app.services.deviationlist_service import DeviationListService
from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import StreamingResponse

router = APIRouter()


@router.get("/", response_model=DeviationListResponse)
async def get_deviation_list(
    country: str | None = None,
    service: DeviationListService = Depends(get_deviationlist_service),
):
    """
    Get the Deviation List in JSON format, optionally filtered by country.

    - **country**: Optional three-letter country code (ISO 3166-1 alpha-3)
    """
    return await service.get_deviation_list(country)


@router.get("/download", response_class=StreamingResponse)
async def download_deviation_list(
    country: str | None = None,
    service: DeviationListService = Depends(get_deviationlist_service),
):
    """
    Download the Deviation List in ASN.1 binary format, optionally filtered by country.

    - **country**: Optional three-letter country code (ISO 3166-1 alpha-3)
    """
    deviation_list_data = await service.get_deviation_list_binary(country)

    # Return binary data with appropriate content type
    return StreamingResponse(
        io.BytesIO(deviation_list_data),
        media_type="application/octet-stream",
        headers={"Content-Disposition": "attachment; filename=deviationlist.dl"},
    )


@router.post("/upload", response_model=DeviationListUploadResponse)
async def upload_deviation_list(
    deviation_list_file: UploadFile = File(...),
    service: DeviationListService = Depends(get_deviationlist_service),
):
    """
    Upload a Deviation List in ASN.1 binary format for processing and storage.

    - **deviation_list_file**: The ASN.1 encoded Deviation List file
    """
    # Read the uploaded file
    content = await deviation_list_file.read()

    # Process the Deviation List data
    return await service.upload_deviation_list(content)
