"""
API dependencies for Document Processing service
"""

from __future__ import annotations

from app.core.config import settings
from app.services.coordinator_service import DocumentProcessingCoordinator
from app.services.mrz_service import MRZProcessingService
from fastapi import HTTPException, Security, status
from fastapi.security.api_key import APIKeyHeader

# API Key security (optional)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str | None = Security(api_key_header)) -> bool:
    """
    Verify the API key provided in the request header.
    Returns True if API key is valid or if API key verification is disabled.
    """
    if not settings.USE_API_KEY:
        return True

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="API Key header is missing"
        )

    # In development mode, allow test API key
    if settings.ENVIRONMENT == "development" and api_key == "test_api_key":
        return True

    if settings.API_KEY and api_key != settings.API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API Key")

    return True


def get_mrz_service() -> MRZProcessingService:
    """
    Get MRZProcessingService instance (legacy)
    """
    return MRZProcessingService()


def get_coordinator_service() -> DocumentProcessingCoordinator:
    """
    Get DocumentProcessingCoordinator instance
    """
    return DocumentProcessingCoordinator()
