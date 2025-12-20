"""
API dependencies for PKD service
"""

import aiosqlite
from app.core.config import settings
from app.db.database import get_db
from app.services.crl_service import CRLService
from app.services.deviationlist_service import DeviationListService
from app.services.dsclist_service import DSCListService
from app.services.masterlist_service import MasterListService
from app.services.sync_service import SyncService
from fastapi import Depends, HTTPException, Security, status
from fastapi.security.api_key import APIKeyHeader

# API Key security
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str = Security(api_key_header)) -> bool:
    """
    Verify the API key provided in the request header.

    Returns True if API key is valid, raises HTTPException otherwise.
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="API Key header is missing"
        )

    # In development mode, allow test API key
    if settings.ENVIRONMENT == "development" and api_key == "test_api_key":
        return True

    if api_key != settings.API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API Key")

    return True


# Service dependencies
async def get_masterlist_service(db: aiosqlite.Connection = Depends(get_db)) -> MasterListService:
    """
    Get MasterListService instance with database dependency
    """
    return MasterListService(db)


async def get_dsclist_service(db: aiosqlite.Connection = Depends(get_db)) -> DSCListService:
    """
    Get DSCListService instance with database dependency
    """
    return DSCListService(db)


async def get_crl_service(db: aiosqlite.Connection = Depends(get_db)) -> CRLService:
    """
    Get CRLService instance with database dependency
    """
    return CRLService(db)


async def get_deviationlist_service(
    db: aiosqlite.Connection = Depends(get_db),
) -> DeviationListService:
    """
    Get DeviationListService instance with database dependency
    """
    return DeviationListService(db)


async def get_sync_service() -> SyncService:
    """Get SyncService instance."""
    return SyncService()
