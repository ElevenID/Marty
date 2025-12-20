"""
CSCA Master List API endpoints
"""

from __future__ import annotations

import io

from app.api.deps import get_masterlist_service, verify_api_key
from app.models.pkd_models import MasterListResponse, MasterListUploadResponse
from app.services.masterlist_service import MasterListService
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import StreamingResponse

router = APIRouter()


@router.get("/", response_model=MasterListResponse)
async def get_master_list(
    country: str | None = Query(None, description="Filter master list by country code"),
    service: MasterListService = Depends(get_masterlist_service),
    _: bool = Depends(verify_api_key),
):
    """
    Retrieve the CSCA Master List.

    Optionally filter by country code.
    """
    try:
        return await service.get_master_list(country)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve master list: {e!s}")


@router.get("/download", response_class=StreamingResponse)
async def download_master_list(
    country: str | None = Query(None, description="Filter master list by country code"),
    service: MasterListService = Depends(get_masterlist_service),
    _: bool = Depends(verify_api_key),
):
    """
    Download the CSCA Master List as ASN.1 encoded binary data.

    Optionally filter by country code.
    """
    try:
        master_list_data = await service.get_master_list_binary(country)
        return StreamingResponse(
            io.BytesIO(master_list_data),
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f"attachment; filename=masterlist{'-'+country if country else ''}.ml"
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to download master list: {e!s}")


@router.get("/{country}", response_model=MasterListResponse)
async def get_country_master_list(
    country: str = Path(..., description="Country code (ISO 3166-1 alpha-3)"),
    service: MasterListService = Depends(get_masterlist_service),
    _: bool = Depends(verify_api_key),
):
    """
    Retrieve the CSCA Master List for a specific country.
    """
    try:
        master_list = await service.get_master_list(country)
        if not master_list.certificates:
            raise HTTPException(
                status_code=404, detail=f"No certificates found for country: {country}"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve master list: {e!s}")
    else:
        return master_list


@router.post("/", response_model=MasterListUploadResponse, status_code=201)
async def upload_master_list(
    master_list_data: bytes,
    service: MasterListService = Depends(get_masterlist_service),
    _: bool = Depends(verify_api_key),
):
    """
    Upload or update a CSCA Master List.

    The master list should be provided as ASN.1 encoded binary data.
    """
    try:
        return await service.upload_master_list(master_list_data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to process master list: {e!s}")
