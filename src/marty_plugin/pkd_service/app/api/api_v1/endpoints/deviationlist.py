"""
PKD Deviation List API endpoints
"""

from app.api.deps import get_deviationlist_service, verify_api_key
from app.models.pkd_models import (
    DeviationListRequest,
    DeviationListResponse,
    DeviationListUploadResponse,
)
from app.services.deviationlist_service import DeviationListService
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter()


@router.get("/", response_model=DeviationListResponse)
async def get_deviation_list(
    service: DeviationListService = Depends(get_deviationlist_service),
    _: bool = Depends(verify_api_key),
):
    """
    Retrieve the current PKD Deviation List.
    """
    try:
        return await service.get_deviation_list()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve deviation list: {e!s}")


@router.post("/", response_model=DeviationListUploadResponse, status_code=201)
async def upload_deviation_list(
    request: DeviationListRequest,
    service: DeviationListService = Depends(get_deviationlist_service),
    _: bool = Depends(verify_api_key),
):
    """
    Upload or update the PKD Deviation List.
    """
    try:
        return await service.upload_deviation_list(request.deviations)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to process deviation list: {e!s}")
