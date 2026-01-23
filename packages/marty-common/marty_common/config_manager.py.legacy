"""
Shared configuration utilities for Marty services.

This module provides standardized configuration loading and management,
reducing redundancy across services.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class ServiceConfig:
    """Base configuration for Marty services."""

    service_name: str
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"

    # gRPC Configuration
    grpc_port: int = 50051
    grpc_max_workers: int = 10
    grpc_enable_health_check: bool = True
    grpc_enable_logging_streamer: bool = True

    # Service Discovery
    hosts: dict[str, str] = field(default_factory=dict)
    ports: dict[str, int] = field(default_factory=dict)

    # Security
    enable_tls: bool = False
    cert_file: str | None = None
    key_file: str | None = None
    ca_file: str | None = None

    # Database (if applicable)
    database_url: str | None = None
    database_pool_size: int = 5

    # External Services
    trust_store_path: str | None = None
    pkd_service_url: str | None = None

    # Feature Flags
    enable_online_verification: bool = False
    enable_caching: bool = True
    cache_ttl_seconds: int = 3600

    # Monitoring
    enable_metrics: bool = True
    metrics_port: int = 8080

    def __post_init__(self) -> None:
        """Post-initialization processing."""
        # Override from environment variables
        self.grpc_port = int(os.environ.get("GRPC_PORT", self.grpc_port))
        self.log_level = os.environ.get("LOG_LEVEL", self.log_level)
        self.environment = os.environ.get("ENV", self.environment)
        self.debug = os.environ.get("DEBUG", "false").lower() == "true"

        # Set service-specific defaults
        if self.service_name in self.ports:
            self.grpc_port = self.ports[self.service_name]


class ConfigurationManager:
    """Centralized configuration management for Marty services."""

    def __init__(self, config_dir: str | Path = "config") -> None:
        self.config_dir = Path(config_dir)
        self._cache: dict[str, dict[str, Any]] = {}

    def load_service_config(
        self,
        service_name: str,
        environment: str | None = None,
        config_overrides: dict[str, Any] | None = None,
    ) -> ServiceConfig:
        """
        Load configuration for a specific service.

        Args:
            service_name: Name of the service
            environment: Environment name (development, production, etc.)
            config_overrides: Additional configuration overrides

        Returns:
            ServiceConfig instance with merged configuration
        """
        env = environment or os.environ.get("ENV", "development")

        # Load base configuration
        base_config = self._load_config_file(f"{env}.yaml")

        # Load service-specific configuration if it exists
        service_config_file = self.config_dir / f"{service_name}.yaml"
        service_config = {}
        if service_config_file.exists():
            service_config = self._load_config_file(f"{service_name}.yaml")

        # Merge configurations (service-specific overrides base)
        merged_config = self._merge_configs(base_config, service_config)

        # Apply any additional overrides
        if config_overrides:
            merged_config = self._merge_configs(merged_config, config_overrides)

        # Create ServiceConfig instance
        return ServiceConfig(service_name=service_name, environment=env, **merged_config)

    def _load_config_file(self, filename: str) -> dict[str, Any]:
        """Load configuration from a YAML file."""
        if filename in self._cache:
            return self._cache[filename]

        config_path = self.config_dir / filename
        if not config_path.exists():
            logger.warning(f"Configuration file not found: {config_path}")
            return {}

        try:
            with config_path.open("r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
                self._cache[filename] = config
                logger.info(f"Loaded configuration from {config_path}")
                return config
        except Exception:
            logger.exception(f"Failed to load configuration from {config_path}")
            return {}

    def _merge_configs(self, base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        """Recursively merge configuration dictionaries."""
        result = base.copy()

        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_configs(result[key], value)
            else:
                result[key] = value

        return result

    def get_service_target(
        self, service_name: str, config: ServiceConfig, use_tls: bool = False
    ) -> str:
        """Get the target address for a service."""
        host = config.hosts.get(service_name, "localhost")
        port = config.ports.get(service_name, 50051)

        if use_tls:
            return f"{host}:{port}"
        return f"{host}:{port}"

    def validate_config(self, config: ServiceConfig) -> list[str]:
        """Validate configuration and return list of validation errors."""
        errors = []

        # Basic validation
        if not config.service_name:
            errors.append("service_name is required")

        if config.grpc_port < 1 or config.grpc_port > 65535:
            errors.append(f"Invalid gRPC port: {config.grpc_port}")

        # TLS validation
        if config.enable_tls:
            if not config.cert_file:
                errors.append("cert_file is required when TLS is enabled")
            if not config.key_file:
                errors.append("key_file is required when TLS is enabled")

        # Database validation
        if config.database_url and config.database_pool_size < 1:
            errors.append("database_pool_size must be at least 1")

        return errors


# Global configuration manager instance
config_manager = ConfigurationManager()


def get_service_config(
    service_name: str,
    environment: str | None = None,
    config_overrides: dict[str, Any] | None = None,
) -> ServiceConfig:
    """
    Convenience function to get service configuration.

    Args:
        service_name: Name of the service
        environment: Environment name
        config_overrides: Additional configuration overrides

    Returns:
        ServiceConfig instance
    """
    return config_manager.load_service_config(
        service_name=service_name, environment=environment, config_overrides=config_overrides
    )


def validate_service_config(config: ServiceConfig) -> None:
    """
    Validate service configuration and raise exception if invalid.

    Args:
        config: ServiceConfig to validate

    Raises:
        ValueError: If configuration is invalid
    """
    errors = config_manager.validate_config(config)
    if errors:
        error_msg = "Configuration validation failed:\n" + "\n".join(
            f"  - {error}" for error in errors
        )
        raise ValueError(error_msg)


def get_database_url(config: ServiceConfig) -> str:
    """
    Get database URL with environment variable override support.

    Args:
        config: ServiceConfig instance

    Returns:
        Database URL string

    Raises:
        ValueError: If database URL is not configured
    """
    db_url = os.environ.get("DATABASE_URL", config.database_url)
    if not db_url:
        msg = "Database URL not configured"
        raise ValueError(msg)
    return db_url


def create_service_targets(config: ServiceConfig) -> dict[str, str]:
    """
    Create service target URLs for all configured services.

    Args:
        config: ServiceConfig instance

    Returns:
        Dictionary mapping service names to target URLs
    """
    targets = {}

    for service_name in config.ports:
        targets[service_name] = config_manager.get_service_target(
            service_name=service_name, config=config, use_tls=config.enable_tls
        )

    return targets
