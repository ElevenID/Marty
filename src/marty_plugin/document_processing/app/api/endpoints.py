"""
API endpoints for Document Processing service
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from app.api.deps import get_coordinator_service, verify_api_key
from app.core.config import settings
from app.models.doc_models_clean import HealthResponse, ProcessRequest, ProcessResponse
from app.services.coordinator_service import DocumentProcessingCoordinator
from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import PlainTextResponse

logger = logging.getLogger(__name__)

router = APIRouter()

# Store server start time for uptime calculation
START_TIME = time.time()


@router.get("/api/ping", response_class=PlainTextResponse, tags=["Health"])
async def ping() -> str:
    """
    Liveness ping endpoint
    Returns 'OK' if the service is running.
    """
    return "OK"


@router.get("/api/health", response_model=HealthResponse, tags=["Health"])
async def health() -> HealthResponse:
    """
    Readiness/health details endpoint
    """
    uptime_sec = int(time.time() - START_TIME)

    license_info = {"valid": True, "expiresAt": settings.LICENSE_VALID_UNTIL}

    return HealthResponse(
        status="ready", version=settings.VERSION, uptimeSec=uptime_sec, license=license_info
    )


@router.get("/api/healthz", tags=["Health"])
async def healthz() -> dict[str, object]:
    """
    Kubernetes-style health check with detailed license info
    """
    return {
        "app": settings.PROJECT_NAME,
        "licenseId": settings.LICENSE_ID,
        "licenseType": settings.LICENSE_TYPE,
        "licenseSerial": settings.LICENSE_SERIAL,
        "licenseValidUntil": settings.LICENSE_VALID_UNTIL,
        "scenarios": settings.SUPPORTED_SCENARIOS,
        "version": settings.CORE_VERSION,
        "documentsDatabase": {
            "id": "MockDB",
            "version": "1.0.0",
            "exportDate": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "description": "Mock document database for testing",
        },
    }


@router.get("/api/readyz", tags=["Health"])
async def readyz() -> dict[str, str]:
    """
    License health check endpoint
    Returns 200 if license is valid, 400 if not
    """
    # Always return success for mock implementation
    return {"status": "valid"}


@router.post("/api/process", response_model=ProcessResponse, tags=["Process"])
async def process_documents(
    request: ProcessRequest,
    coordinator: DocumentProcessingCoordinator = Depends(get_coordinator_service),
    _: bool = Depends(verify_api_key),
    x_request_id: str | None = Header(None, alias="X-RequestID"),
) -> ProcessResponse:
    """
    Process one or more document images

    Submit one or more images for processing. For MRZ-only operation set
    processParam.scenario to 'Mrz'. The response contains timing, transaction
    metadata, and structured containers such as mrzResult.
    """
    try:
        logger.info(
            "Processing request scenario=%s images=%d",
            request.processParam.scenario,
            len(request.images),
        )

        if x_request_id:
            logger.info("Request ID=%s", x_request_id)

        # Process the request using the orchestrator
        result = await coordinator.process_request(request)
    except HTTPException:
        # Let FastAPI handle already constructed HTTP errors
        raise
    except ValueError as e:  # Validation issues from models/services
        logger.exception("Validation error processing request")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:  # pragma: no cover - unexpected
        logger.exception("Unexpected error processing request")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during document processing",
        ) from e
    else:
        logger.info("Processing completed in %dms", result.elapsedTime)
        return result


# Legacy Regula API compatibility endpoints
@router.get("/api/ping-legacy", response_class=PlainTextResponse, tags=["Health"], deprecated=True)
async def ping_legacy() -> str:
    """Legacy ping endpoint for backward compatibility"""
    return "OK"
