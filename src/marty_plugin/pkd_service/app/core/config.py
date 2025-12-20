"""
Configuration settings for the PKD service
"""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseSettings, validator


class Settings(BaseSettings):
    """Settings for the PKD service"""

    # API configuration
    API_V1_STR: str = "/v1/pkd"
    API_ROOT_PATH: str = ""  # Root path for the API (empty for localhost)
    PROJECT_NAME: str = "ICAO Public Key Directory (PKD) API"
    PROJECT_DESCRIPTION: str = """
    ICAO Public Key Directory (PKD) API that provides access to CSCA certificates,
    Document Signer Certificates, Certificate Revocation Lists, and other PKD components
    for passport verification.
    """
    VERSION: str = "1.0.0"

    # Environment configuration
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = ENVIRONMENT == "development"

    # Security configuration
    USE_API_KEY: bool = True
    API_KEY: str = os.getenv("PKD_API_KEY", "")
    SECRET_KEY: str = os.getenv("PKD_SECRET_KEY", "")

    # CORS configuration
    CORS_ORIGINS: list[str] = ["*"]

    # Database configuration
    DATABASE_URL: str | None = os.getenv("PKD_DATABASE_URL")

    # PKD synchronization configuration
    EXTERNAL_PKD_URL: str | None = os.getenv("EXTERNAL_PKD_URL")
    EXTERNAL_PKD_USERNAME: str | None = os.getenv("EXTERNAL_PKD_USERNAME")
    EXTERNAL_PKD_PASSWORD: str | None = os.getenv("EXTERNAL_PKD_PASSWORD")
    SYNC_INTERVAL_HOURS: int = int(os.getenv("PKD_SYNC_INTERVAL_HOURS", "24"))

    # Certificate monitoring configuration
    CERT_CHECK_INTERVAL_HOURS: int = int(os.getenv("PKD_CERT_CHECK_INTERVAL_HOURS", "12"))
    CERT_EXPIRY_WARNING_DAYS: int = int(os.getenv("PKD_CERT_EXPIRY_WARNING_DAYS", "30"))

    # Trusted sources configuration for synchronization
    TRUSTED_SOURCES: dict[str, dict[str, Any]] = {}

    # Storage paths for PKD components
    DATA_PATH: str = os.getenv("PKD_DATA_PATH", "/data/pkd")
    MASTERLIST_PATH: str = os.getenv("PKD_MASTERLIST_PATH", "/data/pkd/masterlist")
    DSCLIST_PATH: str = os.getenv("PKD_DSCLIST_PATH", "/data/pkd/dsclist")
    CRL_PATH: str = os.getenv("PKD_CRL_PATH", "/data/pkd/crl")
    LOCAL_TRUST_STORE_PATH: str = os.getenv("PKD_LOCAL_TRUST_STORE_PATH", "/data/pkd/trust")
    LOCAL_CRL_PATH: str = os.getenv("PKD_LOCAL_CRL_PATH", "/data/pkd/crl/local")

    # API Servers for OpenAPI documentation
    API_SERVERS: list[dict[str, str]] = [
        {"url": "http://localhost:8000", "description": "Local development server"},
        {"url": "https://api.marty.example.com/pkd", "description": "Production server"},
    ]

    @validator("API_KEY", "SECRET_KEY")
    @classmethod
    def validate_secrets(cls, v: str) -> str:
        """Validate that secrets have appropriate values in production."""
        # For now, just validate they exist - environment check removed
        if not v or len(v) < 8:
            msg = "Secrets must be at least 8 characters"
            raise ValueError(msg)
        return v

    class Config:
        env_file = ".env"
        case_sensitive = True


# Create global settings instance
settings = Settings()
