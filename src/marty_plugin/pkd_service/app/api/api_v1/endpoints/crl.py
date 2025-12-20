"""
Certificate Revocation List (CRL) API endpoints
"""

from __future__ import annotations

import io

from app.api.deps import get_crl_service, verify_api_key
from app.models.pkd_models import CrlResponse, CrlUploadResponse
from app.services.crl_service import CRLService
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import StreamingResponse

router = APIRouter()


@router.get("/", response_model=CrlResponse)
async def get_crl_list(
    country: str | None = Query(None, description="Filter CRL by country code"),
    service: CRLService = Depends(get_crl_service),
    _: bool = Depends(verify_api_key),
):
    """
    Retrieve the Certificate Revocation List.

    Optionally filter by country code.
    """
    try:
        return await service.get_crl(country)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve CRL: {e!s}")


@router.get("/download", response_class=StreamingResponse)
async def download_crl(
    country: str | None = Query(None, description="Filter CRL by country code"),
    service: CRLService = Depends(get_crl_service),
    _: bool = Depends(verify_api_key),
):
    """
    Download the Certificate Revocation List as ASN.1 encoded binary data.

    Optionally filter by country code.
    """
    try:
        crl_data = await service.get_crl_binary(country)
        return StreamingResponse(
            io.BytesIO(crl_data),
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f"attachment; filename=crl{'-'+country if country else ''}.crl"
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to download CRL: {e!s}")


@router.get("/{country}", response_model=CrlResponse)
async def get_country_crl(
    country: str = Path(..., description="Country code (ISO 3166-1 alpha-3)"),
    service: CRLService = Depends(get_crl_service),
    _: bool = Depends(verify_api_key),
):
    """
    Retrieve the Certificate Revocation List for a specific country.
    """
    try:
        return await service.get_crl(country)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve CRL: {e!s}")


@router.post("/", response_model=CrlUploadResponse, status_code=201)
async def upload_crl(
    crl_data: bytes,
    service: CRLService = Depends(get_crl_service),
    _: bool = Depends(verify_api_key),
):
    """
    Upload or update a Certificate Revocation List.

    The CRL should be provided as ASN.1 encoded binary data.
    """
    try:
        return await service.upload_crl(crl_data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to process CRL: {e!s}")
