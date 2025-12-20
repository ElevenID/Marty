"""
API endpoints for Certificate Revocation List (CRL) operations
"""

from __future__ import annotations

import io

from app.api.dependencies import get_crl_service
from app.models.pkd_models import CRLResponse, CRLUploadResponse
from app.services.crl_service import CRLService
from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import StreamingResponse

router = APIRouter()


@router.get("/", response_model=CRLResponse)
async def get_crl_list(country: str | None = None, service: CRLService = Depends(get_crl_service)):
    """
    Get the Certificate Revocation List (CRL) in JSON format, optionally filtered by country.

    - **country**: Optional three-letter country code (ISO 3166-1 alpha-3)
    """
    return await service.get_crl_list(country)


@router.get("/download", response_class=StreamingResponse)
async def download_crl(country: str | None = None, service: CRLService = Depends(get_crl_service)):
    """
    Download the CRL in binary format, optionally filtered by country.

    - **country**: Optional three-letter country code (ISO 3166-1 alpha-3)
    """
    crl_data = await service.get_crl_binary(country)

    # Return binary data with appropriate content type
    return StreamingResponse(
        io.BytesIO(crl_data),
        media_type="application/pkix-crl",
        headers={"Content-Disposition": "attachment; filename=revocation_list.crl"},
    )


@router.post("/upload", response_model=CRLUploadResponse)
async def upload_crl(
    crl_file: UploadFile = File(...), service: CRLService = Depends(get_crl_service)
):
    """
    Upload a CRL in binary format for processing and storage.

    - **crl_file**: The Certificate Revocation List file
    """
    # Read the uploaded file
    content = await crl_file.read()

    # Process the CRL data
    return await service.upload_crl(content)
