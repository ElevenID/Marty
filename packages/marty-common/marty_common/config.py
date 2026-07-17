"""
DEPRECATED: Legacy configuration loading utilities.

This module is DEPRECATED. Use the unified configuration system instead:

    # Instead of:
    from marty_common.config import Config
    config = Config()
    
    # Use:
    from framework.config_factory import create_service_config
    config = create_service_config("config/services/your_service.yaml")

The unified configuration system provides:
- Type safety with dataclasses
- Environment variable expansion  
- Service-specific configuration files
- Validation and error handling
- Modern configuration patterns

For migration guide, see: marty-microservices-framework/docs/modern_service_guide.md
"""

from __future__ import annotations

import os
import warnings
from pathlib import Path
from typing import Any

import yaml

from marty_common.infrastructure import (
    DatabaseConfig,
    EventBusConfig,
    KeyVaultConfig,
    ObjectStorageConfig,
)

# Issue deprecation warning
warnings.warn(
    "marty_common.config is deprecated. Use the unified configuration system: "
    "framework.config_factory.create_service_config()",
    DeprecationWarning,
    stacklevel=2
)


class ConfigurationError(Exception):
    """Raised when there's an error loading configuration."""


class Config:
    """
    DEPRECATED: Legacy configuration object.
    
    Use the unified configuration system instead:
        from framework.config_factory import create_service_config
        config = create_service_config("config/services/your_service.yaml")
    """

    def __init__(self, environment: str | None = None) -> None:
        warnings.warn(
            "Config class is deprecated. Use framework.config_factory.create_service_config()",
            DeprecationWarning,
            stacklevel=2
        )
        self._environment = (environment or get_environment()).lower()
        self._config = load_config(self._environment)

    @property
    def environment(self) -> str:
        """Get the current environment name (development, testing, production)."""
        return self._environment

    def get_service(self, service_name: str) -> dict[str, Any]:
        """Get configuration for a specific service by name."""
        return get_service_config(service_name, self._environment)

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by key with optional default."""
        return self._config.get(key, default)

    def database(self, service_name: str | None = None) -> DatabaseConfig:
        """
        Get database configuration for a specific service.

        Args:
            service_name: The name of the service (required for per-service databases)

        Returns:
            DatabaseConfig for the specified service

        Raises:
            ValueError: If service_name is not provided or service config not found
        """
        if not service_name:
            raise ValueError(
                "service_name is required for database configuration. "
                "Each service must use its own dedicated database."
            )

        database_config = self._config.get("database", {})

        # Ensure we have per-service configuration
        if not isinstance(database_config, dict):
            raise ValueError("Database configuration must be a dictionary with per-service configs")

        # Check if service-specific config exists
        if service_name not in database_config:
            raise ValueError(
                f"No database configuration found for service '{service_name}'. "
                f"Available services: {list(database_config.keys())}"
            )

        service_db_config = database_config[service_name]
        if isinstance(service_db_config, dict):
            return DatabaseConfig.from_dict(service_db_config)
        elif isinstance(service_db_config, str):
            # Handle simple DSN string format
            return DatabaseConfig.from_dict({"url": service_db_config})
        else:
            raise ValueError(f"Invalid database configuration format for service '{service_name}'")

    def object_storage(self) -> ObjectStorageConfig:
        return ObjectStorageConfig.from_dict(self._config.get("object_storage", {}))

    def key_vault(self) -> KeyVaultConfig:
        return KeyVaultConfig.from_dict(self._config.get("key_vault", {}))

    def event_bus(self) -> EventBusConfig:
        return EventBusConfig.from_dict(self._config.get("event_bus", {}))

    def grpc_tls(self) -> dict[str, Any]:
        security_config = self._config.get("security", {})
        return security_config.get("grpc_tls", {})

    def __getitem__(self, item: str) -> Any:
        return self._config[item]


def get_environment() -> str:
    """
    Get the current environment from MARTY_ENV environment variable.
    Defaults to 'development' if not set.
    """
    return os.environ.get("MARTY_ENV", "development").lower()


def get_config_path(environment: str | None = None) -> Path:
    """
    Get the path to the configuration file for the specified environment.

    Args:
        environment: The environment to use. If None, uses the value from get_environment()

    Returns:
        Path to the configuration file
    """
    if environment is None:
        environment = get_environment()

    # Project root directory is two levels up from this file
    project_root = Path(__file__).parent.parent.parent
    config_path = project_root / "config" / f"{environment}.yaml"

    if not config_path.exists():
        msg = f"Configuration file not found: {config_path}"
        raise ConfigurationError(msg)

    return config_path


def load_config(environment: str | None = None) -> dict[str, Any]:
    """
    Load configuration from the appropriate YAML file based on environment.

    Args:
        environment: The environment to use. If None, uses the value from get_environment()

    Returns:
        Dictionary containing the configuration
    """
    config_path = get_config_path(environment)

    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)

        # Expand environment variables in strings
        return _expand_env_vars(config)

    except Exception as e:
        msg = f"Error loading configuration: {e!s}"
        raise ConfigurationError(msg)


def _expand_env_vars(config: dict[str, Any]) -> dict[str, Any]:
    """
    Recursively expand environment variables in configuration strings.

    Args:
        config: Configuration dictionary

    Returns:
        Configuration with environment variables expanded
    """
    result = {}

    for key, value in config.items():
        if isinstance(value, dict):
            result[key] = _expand_env_vars(value)
        elif isinstance(value, str) and "${" in value and "}" in value:
            # Extract environment variable pattern
            var_pattern = value.split("${")[1].split("}")[0]

            if ":-" in var_pattern:
                env_var, default = var_pattern.split(":-", 1)
                env_value = os.environ.get(env_var)
                if env_value is not None:
                    result[key] = value.replace(f"${{{var_pattern}}}", env_value)
                else:
                    result[key] = value.replace(f"${{{var_pattern}}}", default)
            else:
                env_var = var_pattern
                env_value = os.environ.get(env_var)
                if env_value is not None:
                    result[key] = value.replace(f"${{{env_var}}}", env_value)
                else:
                    # Keep the original if environment variable is not set
                    result[key] = value
        else:
            result[key] = value

    return result


def get_service_config(service_name: str, environment: str | None = None) -> dict[str, Any]:
    """
    Get configuration specific to a service.

    Args:
        service_name: The name of the service
        environment: The environment to use. If None, uses the value from get_environment()

    Returns:
        Service-specific configuration
    """
    config = load_config(environment)

    # Common configuration for all services
    result = {
        "environment": get_environment(),
        "logging": config.get("logging", {}),
    }

    # Add service-specific configuration if available
    if "services" in config and service_name in config["services"]:
        result.update(config["services"][service_name])

    # Add general configuration
    if "ports" in config and service_name in config["ports"]:
        result["port"] = config["ports"][service_name]

    if "hosts" in config and service_name in config["hosts"]:
        result["host"] = config["hosts"][service_name]

    return result
