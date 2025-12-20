"""
Document Signer Certificate List API endpoints
"""

from __future__ import annotations

import io

from app.api.deps import get_dsclist_service, verify_api_key
from app.models.pkd_models import DscListResponse, DscListUploadResponse
from app.services.dsclist_service import DSCListService
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import StreamingResponse

router = APIRouter()


@router.get("/", response_model=DscListResponse)
async def get_dsc_list(
    country: str | None = Query(None, description="Filter DSC list by country code"),
    service: DSCListService = Depends(get_dsclist_service),
    _: bool = Depends(verify_api_key),
):
    """
    Retrieve the Document Signer Certificate List.

    Optionally filter by country code.
    """
    try:
        return await service.get_dsc_list(country)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve DSC list: {e!s}")


@router.get("/download", response_class=StreamingResponse)
async def download_dsc_list(
    country: str | None = Query(None, description="Filter DSC list by country code"),
    service: DSCListService = Depends(get_dsclist_service),
    _: bool = Depends(verify_api_key),
):
    """
    Download the Document Signer Certificate List as ASN.1 encoded binary data.

    Optionally filter by country code.
    """
    try:
        dsc_list_data = await service.get_dsc_list_binary(country)
        return StreamingResponse(
            io.BytesIO(dsc_list_data),
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f"attachment; filename=dsclist{'-'+country if country else ''}.dsc"
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to download DSC list: {e!s}")


@router.get("/{country}", response_model=DscListResponse)
async def get_country_dsc_list(
    country: str = Path(..., description="Country code (ISO 3166-1 alpha-3)"),
    service: DSCListService = Depends(get_dsclist_service),
    _: bool = Depends(verify_api_key),
):
    """
    Retrieve the Document Signer Certificate List for a specific country.
    """
    try:
        dsc_list = await service.get_dsc_list(country)
        if not dsc_list.certificates:
            raise HTTPException(
                status_code=404, detail=f"No certificates found for country: {country}"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve DSC list: {e!s}")
    else:
        return dsc_list


@router.post("/", response_model=DscListUploadResponse, status_code=201)
async def upload_dsc_list(
    dsc_list_data: bytes,
    service: DSCListService = Depends(get_dsclist_service),
    _: bool = Depends(verify_api_key),
):
    """
    Upload or update a Document Signer Certificate List.

    The DSC list should be provided as ASN.1 encoded binary data.
    """
    try:
        return await service.upload_dsc_list(dsc_list_data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to process DSC list: {e!s}")
