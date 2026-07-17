"""
Base service class providing common patterns for all services
"""

from __future__ import annotations

import os
from abc import ABC
from pathlib import Path
from typing import Any

from marty_common.grpc_types import ServiceDependencies
from marty_common.logging import ServiceLogger


class BaseService(ABC):
    """
    Base service class providing common initialization and configuration patterns.

    All services should inherit from this to get consistent:
    - Logging setup
    - Configuration management
    - Environment variable handling
    - Service dependency injection
    - Error handling patterns
    """

    def __init__(
        self,
        dependencies: ServiceDependencies | None = None,
        service_name: str | None = None,
        channels: dict[str, Any] | None = None,
    ) -> None:
        """
        Initialize base service with common patterns.

        Args:
            dependencies: Service dependencies (database, storage, etc.)
            service_name: Name of the service for logging and config
            channels: gRPC channels for inter-service communication
        """
        # Service name for logging and configuration
        self.service_name = service_name or self.__class__.__name__

        # Setup consolidated logging
        self.logger = ServiceLogger(
            service_name=self.service_name,
            module_name=f"{self.__module__}.{self.service_name}",
        )

        # Store dependencies
        if dependencies is None:
            self.logger.warning(
                "%s initialized without service dependencies - some features may be unavailable",
                self.service_name,
            )
        self.dependencies = dependencies

        # Store channels for inter-service communication
        self.channels = channels or {}

        # Initialize configuration
        self._init_config()

        self.logger.info("%s service initialized", self.service_name)

    def _init_config(self) -> None:
        """Initialize service-specific configuration from dependencies or environment."""
        self.config = {}

        if self.dependencies and hasattr(self.dependencies, "runtime_config"):
            try:
                service_config = self.dependencies.runtime_config.get_service(
                    self.service_name.lower()
                )
                self.config.update(service_config)
                self.logger.debug("Loaded configuration from runtime config")
            except Exception:
                self.logger.debug("No runtime configuration found, using defaults")

        # Load additional config from environment variables
        self._load_env_config()

    def _load_env_config(self) -> None:
        """Load configuration from environment variables."""
        # Common environment variables that all services might use
        env_mappings = {
            "LOG_LEVEL": "log_level",
            "SERVICE_PORT": "port",
            "SERVICE_HOST": "host",
            "HEALTH_CHECK_INTERVAL": "health_check_interval",
            "METRICS_ENABLED": "metrics_enabled",
        }

        for env_var, config_key in env_mappings.items():
            value = os.environ.get(env_var)
            if value is not None:
                # Convert common boolean values
                if value.lower() in ("true", "false"):
                    value = value.lower() == "true"
                # Convert numeric values
                elif value.isdigit():
                    value = int(value)

                self.config[config_key] = value

    def get_config(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value with fallback to default.

        Args:
            key: Configuration key
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        return self.config.get(key, default)

    def resolve_secret(
        self,
        env_var: str,
        file_var: str,
        secret_name: str | None = None,
    ) -> str:
        """
        Resolve secret from env var or *_FILE indirection.

        Precedence:
          1. Direct environment variable
          2. File path specified via *_FILE environment variable

        Args:
            env_var: Direct environment variable name
            file_var: File path environment variable name
            secret_name: Human-readable name for logging

        Returns:
            Secret value or empty string if not found
        """
        # Try direct environment variable first
        direct = os.environ.get(env_var)
        if direct:
            return direct

        # Try file-based secret
        file_path = os.environ.get(file_var)
        if file_path:
            try:
                content = Path(file_path).read_text(encoding="utf-8").strip()
                if content:
                    return content
                self.logger.warning("%s file %s is empty", secret_name or env_var, file_path)
            except FileNotFoundError:
                self.logger.warning("%s file %s not found", secret_name or env_var, file_path)
            except Exception:
                self.logger.exception(
                    "Unexpected error reading secret file %s (%s)", file_path, env_var
                )

        return ""

    def validate_required_config(self, required_keys: list[str]) -> None:
        """
        Validate that required configuration keys are present.

        Args:
            required_keys: List of required configuration keys

        Raises:
            ValueError: If any required configuration is missing
        """
        missing_keys = []
        for key in required_keys:
            if key not in self.config or self.config[key] is None:
                missing_keys.append(key)

        if missing_keys:
            raise ValueError(f"{self.service_name} missing required configuration: {missing_keys}")

    def setup_health_check(self) -> dict[str, Any]:
        """
        Setup basic health check information.

        Returns:
            Health check status dictionary
        """
        return {
            "service": self.service_name,
            "status": "healthy",
            "timestamp": self._get_current_timestamp(),
            "config_loaded": bool(self.config),
            "dependencies_available": self.dependencies is not None,
        }

    def _get_current_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).isoformat()

    async def publish_event(
        self,
        topic: str,
        payload: dict[str, Any],
        *,
        session: Any = None,
        key: str | None = None,
    ) -> None:
        """
        Publish event to the event bus (if available).

        Args:
            topic: Event topic
            payload: Event payload
            session: Database session (if needed)
            key: Event key for partitioning
        """
        if not self.dependencies or not hasattr(self.dependencies, "database"):
            self.logger.warning("Event publishing unavailable - no database dependency")
            return

        try:
            import json

            from marty_common.infrastructure import OutboxRepository

            serialized = json.dumps(payload).encode("utf-8")

            async def handler(db_session) -> None:
                outbox = OutboxRepository(db_session)
                await outbox.enqueue(
                    topic=topic,
                    payload=serialized,
                    key=key.encode("utf-8") if key else None,
                )

            if session is None:
                await self.dependencies.database.run_within_transaction(handler)
            else:
                await handler(session)

            self.logger.debug("Published event to topic %s", topic)

        except Exception:
            self.logger.exception("Failed to publish event to topic %s", topic)

    def get_database(self):
        """Get database connection from dependencies."""
        if not self.dependencies:
            raise ValueError(
                f"{self.service_name} requires service dependencies for database access"
            )
        return self.dependencies.database

    def get_object_storage(self):
        """Get object storage client from dependencies."""
        if not self.dependencies:
            raise ValueError(
                f"{self.service_name} requires service dependencies for object storage"
            )
        return self.dependencies.object_storage

    def get_key_vault(self):
        """Get key vault client from dependencies."""
        if not self.dependencies:
            raise ValueError(f"{self.service_name} requires service dependencies for key vault")
        return self.dependencies.key_vault
