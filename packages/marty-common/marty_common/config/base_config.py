"""
Base configuration class for Marty services.

This module contains the Config class that provides service-specific database configuration.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from marty_common.infrastructure import (
    DatabaseConfig,
    EventBusConfig,
    KeyVaultConfig,
    ObjectStorageConfig,
)


class ConfigurationError(Exception):
    """Raised when there's an error loading configuration."""


class Config:
    """Configuration object for Marty services with enforced service-specific database isolation.

    This configuration class requires service names for database access to ensure proper
    database per service isolation.
    """

    def __init__(self, environment: str | None = None) -> None:
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

    # Get the project root (parent of the src directory)
    src_path = Path(__file__).resolve().parent.parent.parent
    project_root = src_path.parent
    config_path = project_root / "config" / f"{environment}.yaml"

    if not config_path.exists():
        raise ConfigurationError(f"Configuration file not found: {config_path}")

    return config_path


def load_config(environment: str | None = None) -> dict[str, Any]:
    """
    Load configuration from the appropriate YAML file.

    Args:
        environment: The environment to load config for. If None, uses get_environment()

    Returns:
        Configuration dictionary
    """
    config_path = get_config_path(environment)

    try:
        with open(config_path) as file:
            config_data = yaml.safe_load(file)

        # Expand environment variables in the configuration
        config_data = _expand_env_vars(config_data)

        return config_data
    except yaml.YAMLError as e:
        raise ConfigurationError(f"Error parsing YAML configuration file {config_path}: {e}")
    except OSError as e:
        raise ConfigurationError(f"Error reading configuration file {config_path}: {e}")


def get_service_config(service_name: str, environment: str | None = None) -> dict[str, Any]:
    """
    Get configuration for a specific service.

    Args:
        service_name: Name of the service
        environment: Environment to load config for

    Returns:
        Service-specific configuration
    """
    config = load_config(environment)
    services_config = config.get("services", {})

    if service_name not in services_config:
        raise ConfigurationError(f"No configuration found for service: {service_name}")

    return services_config[service_name]


def _expand_env_vars(obj: Any) -> Any:
    """
    Recursively expand environment variables in configuration values.

    Supports format: ${VAR_NAME:-default_value}
    """
    if isinstance(obj, dict):
        return {key: _expand_env_vars(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [_expand_env_vars(item) for item in obj]
    elif isinstance(obj, str):
        return _expand_env_var_string(obj)
    else:
        return obj


def _expand_env_var_string(value: str) -> str:
    """
    Expand environment variables in a string.

    Supports format: ${VAR_NAME:-default_value}
    """
    import re

    pattern = r"\$\{([^}]+)\}"

    def replace_var(match):
        var_expr = match.group(1)
        if ":-" in var_expr:
            var_name, default_value = var_expr.split(":-", 1)
            return os.environ.get(var_name, default_value)
        else:
            return os.environ.get(var_expr, "")

    return re.sub(pattern, replace_var, value)
