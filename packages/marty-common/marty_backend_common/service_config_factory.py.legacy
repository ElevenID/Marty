"""
Service Configuration Factory for Marty services.

This module provides a centralized factory for creating and managing
service configurations, eliminating duplicate configuration loading
patterns across services.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, ClassVar

from marty_common.config import ConfigurationManager
from marty_common.logging_config import get_logger

logger = get_logger(__name__)


class ServiceConfigFactory:
    """Factory for creating standardized service configurations."""

    # Standard service configuration defaults
    DEFAULT_CONFIGS: ClassVar[dict[str, dict[str, Any]]] = {
        "grpc": {
            "grpc_port": 9000,
            "grpc_max_workers": 10,
            "reflection_enabled": True,
            "health_check_enabled": True,
        },
        "fastapi": {
            "api_port": 8000,
            "api_host": "127.0.0.1",
            "docs_enabled": True,
            "cors_enabled": True,
        },
        "database": {
            "host": "localhost",
            "port": 5432,
            "pool_size": 10,
            "max_overflow": 20,
            "pool_timeout": 30,
        },
        "logging": {
            "level": "INFO",
            "format": "structured",
            "enable_file_logging": False,
        },
    }

    # Service-specific configuration overrides
    SERVICE_OVERRIDES: ClassVar[dict[str, dict[str, Any]]] = {
        "mdoc-engine": {
            "grpc_port": 8086,
            "service_description": "mDoc Engine for mobile document processing",
        },
        "mdl-engine": {
            "grpc_port": 8085,
            "service_description": "MDL Engine for mobile driver's license processing",
        },
        "trust-anchor": {
            "grpc_port": 9080,
            "service_description": "Trust Anchor service for certificate management",
        },
        "pkd-service": {
            "api_port": 8088,
            "service_description": "PKD service for public key directory",
        },
        "document-signer": {"grpc_port": 9082, "service_description": "Document signing service"},
        "inspection-system": {
            "grpc_port": 8083,
            "service_description": "Document inspection system",
        },
    }

    @classmethod
    @lru_cache(maxsize=32)
    def create_service_config(
        cls, service_name: str, config_type: str = "grpc", **overrides
    ) -> dict[str, Any]:
        """Create standardized service configuration.

        Args:
            service_name: Name of the service
            config_type: Type of configuration ("grpc", "fastapi", or "hybrid")
            **overrides: Additional configuration overrides

        Returns:
            Complete service configuration dictionary
        """
        # Start with base defaults
        config = {
            "service_name": service_name,
            "environment": os.getenv("MARTY_ENV", "development"),
            "debug": os.getenv("MARTY_DEBUG", "false").lower() == "true",
        }

        # Add type-specific defaults
        if config_type in cls.DEFAULT_CONFIGS:
            config.update(cls.DEFAULT_CONFIGS[config_type])

        # Add database defaults for all services
        config["database"] = cls.DEFAULT_CONFIGS["database"].copy()

        # Add logging defaults for all services
        config["logging"] = cls.DEFAULT_CONFIGS["logging"].copy()

        # Apply service-specific overrides
        if service_name in cls.SERVICE_OVERRIDES:
            config.update(cls.SERVICE_OVERRIDES[service_name])

        # Apply environment variable overrides
        config.update(cls._get_env_overrides(service_name))

        # Apply manual overrides (highest priority)
        config.update(overrides)

        logger.debug("Created configuration for %s: %s", service_name, config)
        return config

    @classmethod
    def _get_env_overrides(cls, service_name: str) -> dict[str, Any]:
        """Get configuration overrides from environment variables."""
        overrides = {}
        service_prefix = service_name.replace("-", "_").upper()

        # Standard environment variable patterns
        env_mappings = {
            f"{service_prefix}_PORT": "grpc_port",
            f"{service_prefix}_API_PORT": "api_port",
            f"{service_prefix}_MAX_WORKERS": "grpc_max_workers",
            f"{service_prefix}_DEBUG": "debug",
            "GRPC_PORT": "grpc_port",  # Generic fallback
            "API_PORT": "api_port",  # Generic fallback
        }

        for env_var, config_key in env_mappings.items():
            value = os.getenv(env_var)
            if value is not None:
                # Try to convert to appropriate type
                try:
                    if config_key.endswith(("_port", "workers")):
                        overrides[config_key] = int(value)
                    elif config_key.endswith(("debug", "enabled")):
                        overrides[config_key] = value.lower() in ("true", "1", "yes")
                    else:
                        overrides[config_key] = value
                except ValueError:
                    logger.warning("Invalid value for %s: %s", env_var, value)

        return overrides

    @classmethod
    @lru_cache(maxsize=16)
    def create_config_manager(cls, service_name: str) -> ConfigurationManager:
        """Create a pre-configured ConfigurationManager for a service.

        Args:
            service_name: Name of the service

        Returns:
            Configured ConfigurationManager instance
        """
        # Create configuration manager with service-specific settings
        config_manager = ConfigurationManager()

        # Set service-specific environment variables if not already set
        service_config = cls.create_service_config(service_name)

        # Apply configuration to environment if not already set
        for key, value in service_config.items():
            env_var = key.upper()
            if os.getenv(env_var) is None:
                os.environ[env_var] = str(value)

        return config_manager


# Convenience functions for common patterns
@lru_cache(maxsize=32)
def get_service_config(service_name: str, config_type: str = "grpc", **overrides) -> dict[str, Any]:
    """Get standardized service configuration.

    Args:
        service_name: Name of the service
        config_type: Type of configuration
        **overrides: Configuration overrides

    Returns:
        Service configuration dictionary
    """
    return ServiceConfigFactory.create_service_config(service_name, config_type, **overrides)


@lru_cache(maxsize=16)
def get_config_manager(service_name: str) -> ConfigurationManager:
    """Get pre-configured ConfigurationManager for a service.

    Args:
        service_name: Name of the service

    Returns:
        Configured ConfigurationManager instance
    """
    return ServiceConfigFactory.create_config_manager(service_name)


def get_service_port(service_name: str, default: int = 9000) -> int:
    """Get the standard port for a service.

    Args:
        service_name: Name of the service
        default: Default port if not configured

    Returns:
        Service port number
    """
    config = get_service_config(service_name)
    return config.get("grpc_port", config.get("api_port", default))


def get_service_description(service_name: str) -> str:
    """Get the description for a service.

    Args:
        service_name: Name of the service

    Returns:
        Service description
    """
    config = get_service_config(service_name)
    return config.get("service_description", f"{service_name.title()} Service")
