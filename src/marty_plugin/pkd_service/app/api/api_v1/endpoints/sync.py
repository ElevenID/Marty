"""
PKD Synchronization API endpoints
"""

from __future__ import annotations

from app.api.deps import get_sync_service, verify_api_key
from app.models.pkd_models import PkdSyncRequest, PkdSyncResponse, PkdSyncStatusResponse
from app.services.sync_service import SyncService
from fastapi import APIRouter, Depends, HTTPException, Query

router = APIRouter()


@router.post("/", response_model=PkdSyncResponse, status_code=202)
async def sync_pkd(
    request: PkdSyncRequest,
    service: SyncService = Depends(get_sync_service),
    _: bool = Depends(verify_api_key),
):
    """
    Trigger synchronization with an external PKD.
    """
    try:
        return await service.initiate_sync(request)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to initiate PKD synchronization: {e!s}"
        )


@router.get("/status", response_model=PkdSyncStatusResponse)
async def get_sync_status(
    sync_id: str | None = Query(None, description="ID of the synchronization job to check"),
    service: SyncService = Depends(get_sync_service),
    _: bool = Depends(verify_api_key),
):
    """
    Check the status of a PKD synchronization job.

    If no sync_id is provided, returns the status of the most recent job.
    """
    try:
        return await service.get_sync_status(sync_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve synchronization status: {e!s}"
        )
