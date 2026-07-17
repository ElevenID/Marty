"""
Enhanced configuration management utilities to eliminate duplicate configuration patterns.

This module extends the existing config_manager with common patterns used across services
to reduce code duplication in environment variable handling and service configuration.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

from marty_common.config_manager import ServiceConfig

T = TypeVar("T")


@dataclass
class EnhancedServiceConfig(ServiceConfig):
    """Enhanced service configuration with common patterns."""

    # Data directories
    data_dir: str = field(default_factory=lambda: os.environ.get("DATA_DIR", "/app/data"))

    # Certificate and trust management
    trust_store_path: str | None = field(default_factory=lambda: os.environ.get("TRUST_STORE_PATH"))
    cert_notification_days: list[int] = field(default_factory=list)
    cert_check_interval_days: int = field(
        default_factory=lambda: int(os.environ.get("CERT_CHECK_INTERVAL_DAYS", "1"))
    )
    cert_history_file: str | None = field(
        default_factory=lambda: os.environ.get("CERT_HISTORY_FILE")
    )

    # Service-specific ports (commonly used patterns)
    postgres_port: int = field(default_factory=lambda: int(os.environ.get("POSTGRES_PORT", "5432")))

    # Common timeout configurations
    connection_timeout: int = field(
        default_factory=lambda: int(os.environ.get("CONNECTION_TIMEOUT", "30"))
    )
    read_timeout: int = field(default_factory=lambda: int(os.environ.get("READ_TIMEOUT", "60")))

    # SSL/TLS configuration
    verify_ssl: bool = field(
        default_factory=lambda: os.environ.get("VERIFY_SSL", "False").lower() == "true"
    )

    def __post_init__(self) -> None:
        """Initialize computed fields after object creation."""
        if hasattr(super(), "__post_init__"):
            super().__post_init__()

        # Parse notification days from environment
        if not self.cert_notification_days:
            notification_days_str = os.environ.get("NOTIFICATION_DAYS", "30,15,7,5,3,1")
            self.cert_notification_days = [
                int(day.strip()) for day in notification_days_str.split(",") if day.strip()
            ]


class ConfigurationManager:
    """
    Centralized configuration manager to eliminate duplicate patterns.

    Provides standardized methods for common configuration patterns
    used across services.
    """

    @staticmethod
    def get_env_int(key: str, default: int) -> int:
        """Get integer value from environment with default."""
        try:
            return int(os.environ.get(key, str(default)))
        except (ValueError, TypeError):
            return default

    @staticmethod
    def get_env_bool(key: str, default: bool = False) -> bool:
        """Get boolean value from environment with default."""
        value = os.environ.get(key, str(default)).lower()
        return value in ("true", "1", "yes", "on")

    @staticmethod
    def get_env_path(key: str, default: str | None = None) -> Path | None:
        """Get Path object from environment with default."""
        value = os.environ.get(key, default)
        return Path(value) if value else None

    @staticmethod
    def get_env_list(key: str, separator: str = ",", default: list[str] | None = None) -> list[str]:
        """Get list of strings from environment with separator."""
        value = os.environ.get(key)
        if not value:
            return default or []
        return [item.strip() for item in value.split(separator) if item.strip()]

    @staticmethod
    def get_env_int_list(
        key: str, separator: str = ",", default: list[int] | None = None
    ) -> list[int]:
        """Get list of integers from environment with separator."""
        str_list = ConfigurationManager.get_env_list(key, separator)
        if not str_list:
            return default or []
        try:
            return [int(item) for item in str_list]
        except ValueError:
            return default or []

    @staticmethod
    def resolve_secret(
        env_var: str,
        file_var: str | None = None,
        default: str | None = None,
        required: bool = False,
    ) -> str | None:
        """
        Resolve a secret from environment variable or file.

        This consolidates the common pattern of checking both direct env vars
        and file-based secrets (e.g., Docker secrets).

        Args:
            env_var: Direct environment variable name
            file_var: Environment variable containing file path
            default: Default value if neither is found
            required: Raise error if not found and no default

        Returns:
            Resolved secret value or None

        Raises:
            ValueError: If required=True and secret not found
        """
        # Try direct environment variable first
        value = os.environ.get(env_var)
        if value:
            return value

        # Try file-based secret if file_var provided
        if file_var:
            file_path = os.environ.get(file_var)
            if file_path:
                try:
                    with Path(file_path).open(encoding="utf-8") as f:
                        content = f.read().strip()
                        if content:
                            return content
                except (FileNotFoundError, OSError, PermissionError):
                    pass  # Fall through to default/error handling

        # Return default or raise error if required
        if default is not None:
            return default

        if required:
            file_info = f" or {file_var}" if file_var else ""
            error_msg = f"Required secret not found: {env_var}{file_info}"
            raise ValueError(error_msg)

        return None

    @staticmethod
    def get_service_port(service_name: str, default_port: int) -> int:
        """Get port for a service using common naming patterns."""
        # Try service-specific port first
        service_key = f"{service_name.upper().replace('-', '_')}_PORT"
        port = ConfigurationManager.get_env_int(service_key, default_port)

        # Fall back to GRPC_PORT for gRPC services
        if port == default_port:
            port = ConfigurationManager.get_env_int("GRPC_PORT", default_port)

        return port

    @staticmethod
    def get_service_host(service_name: str, default_host: str | None = None) -> str:
        """Get host for a service using common naming patterns."""
        service_key = f"{service_name.upper().replace('-', '_')}_HOST"
        default = default_host or service_name
        return os.environ.get(service_key, default)

    @staticmethod
    def get_service_endpoint(
        service_name: str, default_port: int, default_host: str | None = None
    ) -> str:
        """Get full endpoint (host:port) for a service."""
        host = ConfigurationManager.get_service_host(service_name, default_host)
        port = ConfigurationManager.get_service_port(service_name, default_port)
        return f"{host}:{port}"

    @staticmethod
    def get_database_config() -> dict[str, Any]:
        """Get standard database configuration."""
        return {
            "url": ConfigurationManager.resolve_secret(
                "DATABASE_URL", "DATABASE_URL_FILE", required=True
            ),
            "pool_size": ConfigurationManager.get_env_int("DB_POOL_SIZE", 5),
            "max_overflow": ConfigurationManager.get_env_int("DB_MAX_OVERFLOW", 10),
            "pool_timeout": ConfigurationManager.get_env_int("DB_POOL_TIMEOUT", 30),
            "pool_recycle": ConfigurationManager.get_env_int("DB_POOL_RECYCLE", 3600),
        }

    @staticmethod
    def get_openxpki_config() -> dict[str, Any]:
        """Get standard OpenXPKI configuration."""
        return {
            "base_url": os.environ.get("OPENXPKI_BASE_URL", "https://localhost:8443/api/v2"),
            "username": ConfigurationManager.resolve_secret(
                "OPENXPKI_USERNAME", "OPENXPKI_USERNAME_FILE", required=True
            ),
            "password": ConfigurationManager.resolve_secret(
                "OPENXPKI_PASSWORD", "OPENXPKI_PASSWORD_FILE", required=True
            ),
            "realm": os.environ.get("OPENXPKI_REALM", "11id"),
            "connection_timeout": ConfigurationManager.get_env_int("OPENXPKI_CONN_TIMEOUT", 30),
            "read_timeout": ConfigurationManager.get_env_int("OPENXPKI_READ_TIMEOUT", 60),
            "verify_ssl": ConfigurationManager.get_env_bool("OPENXPKI_VERIFY_SSL", False),
            "local_store_path": os.environ.get("OPENXPKI_LOCAL_STORE", "data/trust/openxpki_sync"),
        }

    @staticmethod
    def get_certificate_config() -> dict[str, Any]:
        """Get standard certificate management configuration."""
        return {
            "check_interval_days": ConfigurationManager.get_env_int("CERT_CHECK_INTERVAL_DAYS", 1),
            "notification_days": ConfigurationManager.get_env_int_list(
                "CERT_NOTIFICATION_DAYS", default=[30, 15, 7, 5, 3, 1]
            ),
            "history_file": os.environ.get("CERT_HISTORY_FILE"),
            "data_dir": os.environ.get("DATA_DIR", "data"),
            "trust_store_path": os.environ.get("TRUST_STORE_PATH"),
        }


def create_enhanced_config(service_name: str, **overrides: object) -> EnhancedServiceConfig:
    """
    Create enhanced service configuration with common patterns.

    Args:
        service_name: Name of the service
        **overrides: Configuration overrides

    Returns:
        Configured EnhancedServiceConfig instance
    """
    config_data = {
        "service_name": service_name,
        "grpc_port": ConfigurationManager.get_service_port(service_name, 50051),
        **overrides,
    }

    return EnhancedServiceConfig(**config_data)


# Common configuration factory functions for specific service types
def create_grpc_service_config(
    service_name: str, default_port: int = 50051
) -> EnhancedServiceConfig:
    """Create configuration for gRPC services."""
    return create_enhanced_config(
        service_name=service_name,
        grpc_port=ConfigurationManager.get_service_port(service_name, default_port),
        grpc_max_workers=ConfigurationManager.get_env_int("GRPC_MAX_WORKERS", 10),
    )


def create_certificate_service_config(service_name: str) -> EnhancedServiceConfig:
    """Create configuration for certificate management services."""
    cert_config = ConfigurationManager.get_certificate_config()
    return create_enhanced_config(
        service_name=service_name,
        cert_check_interval_days=cert_config["check_interval_days"],
        cert_notification_days=cert_config["notification_days"],
        cert_history_file=cert_config["history_file"],
        data_dir=cert_config["data_dir"],
        trust_store_path=cert_config["trust_store_path"],
    )


def create_openxpki_service_config(service_name: str) -> EnhancedServiceConfig:
    """Create configuration for OpenXPKI-enabled services."""
    openxpki_config = ConfigurationManager.get_openxpki_config()
    return create_enhanced_config(
        service_name=service_name,
        connection_timeout=openxpki_config["connection_timeout"],
        read_timeout=openxpki_config["read_timeout"],
        verify_ssl=openxpki_config["verify_ssl"],
    )
