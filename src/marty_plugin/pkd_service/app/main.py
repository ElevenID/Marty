"""
Main FastAPI application for PKD service
"""

from app.api.api_v1.api import api_router
from app.api.csca import router as csca_router
from app.core.config import settings
from app.db.database import init_db
from fastapi import FastAPI

from marty_common.logging_config import get_logger, setup_logging

# Configure logging using shared utility
setup_logging(service_name="pkd-service")
logger = get_logger(__name__)

app = FastAPI(
    title="ICAO PKD API",
    description="API for ICAO Public Key Directory management",
    version="1.0.0",
    openapi_url="/openapi.json",
    docs_url="/docs",
)

# Add API routers
app.include_router(api_router, prefix=settings.API_V1_STR)
app.include_router(csca_router)  # CSCA router already includes /v1/csca prefix


@app.on_event("startup")
async def startup_db_client() -> None:
    """Initialize database connection on startup"""
    await init_db()
    logger.info("Database initialized")


@app.on_event("shutdown")
async def shutdown_db_client() -> None:
    """Close database connection on shutdown"""
    logger.info("Shutting down database connection")


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "ICAO PKD API Server",
        "docs": f"{settings.API_ROOT_PATH}/docs",
    }
