"""
Configuration utilities for the PKD service
"""

from typing import Any

from app.core.config import Settings


def get_config() -> dict[str, Any]:
    """
    Get configuration settings as a dictionary

    Returns:
        Dictionary containing configuration settings
    """
    settings = Settings()

    # Convert Pydantic settings to dictionary format expected by services
    return {
        "api": {
            "v1_str": settings.API_V1_STR,
            "project_name": settings.PROJECT_NAME,
            "version": settings.VERSION,
            "environment": settings.ENVIRONMENT,
            "debug": settings.DEBUG,
        },
        "security": {
            "use_api_key": settings.USE_API_KEY,
            "api_key": settings.API_KEY,
        },
        "database": {
            "url": getattr(settings, "DATABASE_URL", "sqlite:///./data/pkd.db"),
        },
        "data": {
            "path": getattr(settings, "DATA_PATH", "/data"),
        },
        # OpenXPKI configuration with defaults
        "openxpki": {
            "base_url": "https://localhost:8443/api/v2",
            "username": "pkiadmin",
            "password": "secret",
            "realm": "marty",
            "connection_timeout": 30,
            "read_timeout": 60,
            "verify_ssl": False,
            "local_store_path": "data/trust/openxpki_sync",
        },
    }
