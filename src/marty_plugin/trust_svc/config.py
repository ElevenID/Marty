"""
Trust Services Configuration

Configuration management for trust services including database connections,
KMS settings, and service parameters.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass
class DatabaseConfig:
    """PostgreSQL database configuration for trust services."""

    host: str = os.getenv("TRUST_DB_HOST", "localhost")
    port: int = int(os.getenv("TRUST_DB_PORT", "5432"))
    database: str = os.getenv("TRUST_DB_NAME", "marty_trust")
    username: str = os.getenv("TRUST_DB_USER", "trust_service")
    password: str = os.getenv("TRUST_DB_PASSWORD", "change_me")
    schema: str = "trust_svc"
    pool_size: int = int(os.getenv("TRUST_DB_POOL_SIZE", "10"))
    max_overflow: int = int(os.getenv("TRUST_DB_MAX_OVERFLOW", "20"))

    @property
    def connection_url(self) -> str:
        """Generate SQLAlchemy connection URL."""
        return f"postgresql+asyncpg://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"


@dataclass
class KMSConfig:
    """KMS configuration for signing trust snapshots."""

    provider: str = os.getenv("KMS_PROVIDER", "aws")  # aws, gcp, azure, mock
    key_id: str = os.getenv("KMS_KEY_ID", "alias/marty-trust-signing")
    region: str = os.getenv("KMS_REGION", "us-east-1")
    signature_algorithm: str = "RSA_PKCS1_SHA_256"


@dataclass
class PKDConfig:
    """PKD ingestion configuration."""

    data_directory: str = os.getenv("PKD_DATA_DIR", "/app/data/pkd")
    synthetic_data_dir: str = os.getenv("SYNTHETIC_DATA_DIR", "/app/data/synthetic")
    master_list_max_age_hours: int = int(os.getenv("MASTER_LIST_MAX_AGE_HOURS", "24"))
    crl_max_age_hours: int = int(os.getenv("CRL_MAX_AGE_HOURS", "6"))
    ocsp_timeout_seconds: int = int(os.getenv("OCSP_TIMEOUT_SECONDS", "10"))
    concurrent_downloads: int = int(os.getenv("PKD_CONCURRENT_DOWNLOADS", "5"))


@dataclass
class ServiceConfig:
    """General service configuration."""

    host: str = os.getenv("TRUST_SVC_HOST", "0.0.0.0")
    port: int = int(os.getenv("TRUST_SVC_PORT", "8080"))
    workers: int = int(os.getenv("TRUST_SVC_WORKERS", "4"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    metrics_enabled: bool = os.getenv("METRICS_ENABLED", "true").lower() == "true"
    metrics_port: int = int(os.getenv("METRICS_PORT", "9090"))

    # Job scheduling
    scheduler_enabled: bool = os.getenv("SCHEDULER_ENABLED", "true").lower() == "true"
    master_list_sync_cron: str = os.getenv("MASTER_LIST_SYNC_CRON", "0 */6 * * *")  # Every 6 hours
    crl_refresh_cron: str = os.getenv("CRL_REFRESH_CRON", "0 */2 * * *")  # Every 2 hours
    snapshot_create_cron: str = os.getenv("SNAPSHOT_CREATE_CRON", "0 0 * * *")  # Daily

    # Trust validation settings
    require_immutable_snapshots: bool = (
        os.getenv("REQUIRE_IMMUTABLE_SNAPSHOTS", "false").lower() == "true"
    )
    snapshot_signature_required: bool = (
        os.getenv("SNAPSHOT_SIGNATURE_REQUIRED", "true").lower() == "true"
    )
    default_trust_level: str = os.getenv("DEFAULT_TRUST_LEVEL", "standard")


@dataclass
class TrustServiceConfig:
    """Complete trust service configuration."""

    database: DatabaseConfig
    kms: KMSConfig
    pkd: PKDConfig
    service: ServiceConfig

    @classmethod
    def from_env(cls) -> TrustServiceConfig:
        """Create configuration from environment variables."""
        return cls(
            database=DatabaseConfig(), kms=KMSConfig(), pkd=PKDConfig(), service=ServiceConfig()
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "database": {
                "host": self.database.host,
                "port": self.database.port,
                "database": self.database.database,
                "schema": self.database.schema,
                "pool_size": self.database.pool_size,
            },
            "kms": {
                "provider": self.kms.provider,
                "key_id": self.kms.key_id,
                "region": self.kms.region,
            },
            "pkd": {
                "data_directory": self.pkd.data_directory,
                "master_list_max_age_hours": self.pkd.master_list_max_age_hours,
                "crl_max_age_hours": self.pkd.crl_max_age_hours,
            },
            "service": {
                "host": self.service.host,
                "port": self.service.port,
                "log_level": self.service.log_level,
                "metrics_enabled": self.service.metrics_enabled,
            },
        }


# Global configuration instance
config = TrustServiceConfig.from_env()
