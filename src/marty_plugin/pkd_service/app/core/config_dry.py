"""
Configuration settings for the PKD service using DRY base classes
"""

from __future__ import annotations

import os
from typing import Any

from pydantic import Field, field_validator

from marty_common.base_config import FastAPIServiceConfig


class PKDServiceConfig(FastAPIServiceConfig):
    """PKD Service configuration using DRY base configuration."""

    # Service identification (inherited from base)
    service_name: str = Field(default="pkd-service")
    title: str = Field(default="ICAO Public Key Directory (PKD) API")
    description: str = Field(
        default="""
    ICAO Public Key Directory (PKD) API that provides access to CSCA certificates,
    Document Signer Certificates, Certificate Revocation Lists, and other PKD components
    for passport verification.
    """
    )

    # API configuration (using base class patterns)
    api_v1_str: str = Field(default="/v1/pkd", description="API v1 base path")

    # Security configuration
    use_api_key: bool = Field(default=True, description="Enable API key authentication")
    api_key: str = Field(default="", description="PKD API key")
    secret_key: str = Field(default="", description="PKD secret key")

    # PKD synchronization configuration
    external_pkd_url: str | None = Field(default=None, description="External PKD URL")
    external_pkd_username: str | None = Field(default=None, description="External PKD username")
    external_pkd_password: str | None = Field(default=None, description="External PKD password")
    sync_interval_hours: int = Field(default=24, description="Sync interval in hours")

    # Certificate monitoring configuration
    cert_check_interval_hours: int = Field(default=12, description="Certificate check interval")
    cert_expiry_warning_days: int = Field(default=30, description="Certificate expiry warning")

    # Trusted sources configuration for synchronization
    trusted_sources: dict[str, dict[str, Any]] = Field(
        default_factory=dict, description="Trusted synchronization sources"
    )

    # Storage paths for PKD components
    data_path: str = Field(default="/data/pkd", description="PKD data storage path")
    masterlist_path: str = Field(default="/data/pkd/masterlist", description="Masterlist path")
    dsclist_path: str = Field(default="/data/pkd/dsclist", description="DSC list path")
    crl_path: str = Field(default="/data/pkd/crl", description="CRL storage path")
    local_trust_store_path: str = Field(
        default="/data/pkd/trust", description="Local trust store path"
    )
    local_crl_path: str = Field(default="/data/pkd/crl/local", description="Local CRL path")

    # API Servers for OpenAPI documentation
    api_servers: list[dict[str, str]] = Field(
        default=[
            {"url": "http://localhost:8000", "description": "Local development server"},
            {"url": "https://api.marty.example.com/pkd", "description": "Production server"},
        ],
        description="API servers for documentation",
    )

    @field_validator("api_key", "secret_key")
    @classmethod
    def validate_secrets(cls, v: str) -> str:
        """Validate that secrets have appropriate values in production."""
        if not v or len(v) < 8:
            msg = "Secrets must be at least 8 characters"
            raise ValueError(msg)
        return v

    @classmethod
    def from_env(cls) -> PKDServiceConfig:
        """Create configuration from environment variables."""
        return cls(
            # Security
            api_key=os.getenv("PKD_API_KEY", ""),
            secret_key=os.getenv("PKD_SECRET_KEY", ""),
            # Database (inherited from base)
            database_url=os.getenv("PKD_DATABASE_URL"),
            # PKD sync
            external_pkd_url=os.getenv("EXTERNAL_PKD_URL"),
            external_pkd_username=os.getenv("EXTERNAL_PKD_USERNAME"),
            external_pkd_password=os.getenv("EXTERNAL_PKD_PASSWORD"),
            sync_interval_hours=int(os.getenv("PKD_SYNC_INTERVAL_HOURS", "24")),
            # Certificate monitoring
            cert_check_interval_hours=int(os.getenv("PKD_CERT_CHECK_INTERVAL_HOURS", "12")),
            cert_expiry_warning_days=int(os.getenv("PKD_CERT_EXPIRY_WARNING_DAYS", "30")),
            # Storage paths
            data_path=os.getenv("PKD_DATA_PATH", "/data/pkd"),
            masterlist_path=os.getenv("PKD_MASTERLIST_PATH", "/data/pkd/masterlist"),
            dsclist_path=os.getenv("PKD_DSCLIST_PATH", "/data/pkd/dsclist"),
            crl_path=os.getenv("PKD_CRL_PATH", "/data/pkd/crl"),
            local_trust_store_path=os.getenv("PKD_LOCAL_TRUST_STORE_PATH", "/data/pkd/trust"),
            local_crl_path=os.getenv("PKD_LOCAL_CRL_PATH", "/data/pkd/crl/local"),
        )


# Create global settings instance
settings = PKDServiceConfig.from_env()
