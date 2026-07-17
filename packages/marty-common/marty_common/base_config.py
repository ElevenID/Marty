"""
Shared configuration base classes for Marty services.

This module provides base configuration classes that can be inherited by
service-specific configuration to reduce duplication.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from marty_common.logging_config import setup_logging


class BaseServiceConfig(BaseModel):
    """Base configuration class for all Marty services.

    This class provides common configuration options that should be inherited
    by all service-specific configuration classes.
    """

    # Service identification
    service_name: str = Field(description="Name of the service")
    version: str = Field(default="1.0.0", description="Service version")

    # Environment configuration
    environment: str = Field(
        default="development", description="Environment (development, testing, staging, production)"
    )
    debug: bool = Field(default=False, description="Enable debug mode")

    # Logging configuration
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: str = Field(default="json", description="Log format (json, text)")
    enable_grpc_logging: bool = Field(
        default=False, description="Enable gRPC request/response logging"
    )

    # Server configuration
    host: str = Field(default="127.0.0.1", description="Host to bind to")
    port: int = Field(default=8000, description="Port to bind to")

    # Security configuration
    allowed_hosts: list[str] = Field(default=["*"], description="Allowed hosts")
    cors_origins: list[str] = Field(default=["*"], description="Allowed CORS origins")
    cors_methods: list[str] = Field(
        default=["GET", "POST", "PUT", "DELETE"], description="Allowed CORS methods"
    )
    cors_headers: list[str] = Field(default=["*"], description="Allowed CORS headers")

    # Health check configuration
    health_check_path: str = Field(default="/health", description="Health check endpoint path")

    # Database configuration (if applicable)
    database_url: str | None = Field(default=None, description="Database connection URL")

    # Metrics configuration
    metrics_enabled: bool = Field(default=True, description="Enable metrics collection")
    metrics_path: str = Field(default="/metrics", description="Metrics endpoint path")

    # gRPC configuration
    grpc_port: int = Field(default=50051, description="gRPC server port")
    grpc_max_workers: int = Field(default=10, description="Maximum gRPC worker threads")
    grpc_max_send_message_length: int = Field(
        default=100 * 1024 * 1024, description="gRPC max send message length"
    )
    grpc_max_receive_message_length: int = Field(
        default=100 * 1024 * 1024, description="gRPC max receive message length"
    )
    grpc_keepalive_time: int = Field(default=30, description="gRPC keepalive time")
    grpc_keepalive_timeout: int = Field(default=5, description="gRPC keepalive timeout")
    grpc_keepalive_permit_without_calls: bool = Field(
        default=True, description="gRPC keepalive permit without calls"
    )
    grpc_http2_max_pings_without_data: int = Field(
        default=0, description="gRPC HTTP/2 max pings without data"
    )
    grpc_http2_min_time_between_pings: int = Field(
        default=10, description="gRPC HTTP/2 min time between pings"
    )
    grpc_http2_min_ping_interval_without_data: int = Field(
        default=300, description="gRPC HTTP/2 min ping interval without data"
    )

    # TLS configuration
    tls_enabled: bool = Field(default=False, description="Enable TLS")
    tls_cert_file: str | None = Field(default=None, description="TLS certificate file path")
    tls_key_file: str | None = Field(default=None, description="TLS private key file path")
    tls_ca_file: str | None = Field(default=None, description="TLS CA file path")

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Validate environment setting."""
        valid_environments = {"development", "testing", "staging", "production"}
        if v not in valid_environments:
            msg = f"Environment must be one of {valid_environments}"
            raise ValueError(msg)
        return v

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level setting."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid_levels:
            msg = f"Log level must be one of {valid_levels}"
            raise ValueError(msg)
        return v.upper()

    @field_validator("debug")
    @classmethod
    def auto_set_debug(cls, v: bool, info) -> bool:
        """Auto-set debug based on environment."""
        if hasattr(info, "data") and info.data.get("environment") == "development":
            return True
        return v

    def get_tls_config(self) -> dict[str, Any]:
        """Get TLS configuration dictionary."""
        if not self.tls_enabled:
            return {}

        return {
            "cert_file": self.tls_cert_file,
            "key_file": self.tls_key_file,
            "ca_file": self.tls_ca_file,
        }

    def get_cors_config(self) -> dict[str, Any]:
        """Get CORS configuration dictionary."""
        return {
            "allow_origins": self.cors_origins,
            "allow_methods": self.cors_methods,
            "allow_headers": self.cors_headers,
        }

    def get_server_config(self) -> dict[str, Any]:
        """Get basic server configuration dictionary."""
        return {
            "host": self.host,
            "port": self.port,
            "debug": self.debug,
        }

    def get_grpc_config(self) -> dict[str, Any]:
        """Get gRPC server configuration dictionary."""
        config = {
            "port": self.grpc_port,
            "max_workers": self.grpc_max_workers,
            "options": [
                ("grpc.max_send_message_length", self.grpc_max_send_message_length),
                ("grpc.max_receive_message_length", self.grpc_max_receive_message_length),
                ("grpc.keepalive_time_ms", self.grpc_keepalive_time * 1000),
                ("grpc.keepalive_timeout_ms", self.grpc_keepalive_timeout * 1000),
                ("grpc.keepalive_permit_without_calls", self.grpc_keepalive_permit_without_calls),
                ("grpc.http2.max_pings_without_data", self.grpc_http2_max_pings_without_data),
                (
                    "grpc.http2.min_time_between_pings_ms",
                    self.grpc_http2_min_time_between_pings * 1000,
                ),
                (
                    "grpc.http2.min_ping_interval_without_data_ms",
                    self.grpc_http2_min_ping_interval_without_data * 1000,
                ),
            ],
        }

        if self.tls_enabled:
            config.update(self.get_tls_config())

        return config

    def setup_logging(self) -> None:
        """Set up logging using the shared logging configuration."""
        setup_logging(
            service_name=self.service_name,
            log_level_env_var="LOG_LEVEL",
            log_format_env_var="LOG_FORMAT",
            enable_grpc_logging=self.enable_grpc_logging,
        )


class FastAPIServiceConfig(BaseServiceConfig):
    """Configuration for FastAPI-based services."""

    # FastAPI specific configuration
    title: str = Field(description="API title")
    description: str = Field(default="", description="API description")
    docs_url: str = Field(default="/docs", description="Swagger UI path")
    redoc_url: str = Field(default="/redoc", description="ReDoc path")
    openapi_url: str = Field(default="/openapi.json", description="OpenAPI schema path")
    root_path: str = Field(default="", description="Root path for the API")

    # HTTP server configuration
    http_port: int = Field(default=8080, description="HTTP server port")

    def get_fastapi_config(self) -> dict[str, Any]:
        """Get FastAPI configuration dictionary."""
        return {
            "title": self.title,
            "description": self.description,
            "version": self.version,
            "docs_url": self.docs_url,
            "redoc_url": self.redoc_url,
            "openapi_url": self.openapi_url,
            "root_path": self.root_path,
        }


class GRPCServiceConfig(BaseServiceConfig):
    """Configuration for gRPC-only services."""

    # gRPC specific configuration
    reflection_enabled: bool = Field(default=True, description="Enable gRPC reflection")
    interceptors_enabled: bool = Field(default=True, description="Enable gRPC interceptors")


class HybridServiceConfig(FastAPIServiceConfig, GRPCServiceConfig):
    """Configuration for services that run both FastAPI and gRPC."""

    # Additional configuration for hybrid services
    concurrent_servers: bool = Field(default=True, description="Run servers concurrently")


def create_service_config(service_type: str, **kwargs) -> BaseServiceConfig:
    """Factory function to create appropriate service configuration.

    Args:
        service_type: Type of service ("base", "fastapi", "grpc", "hybrid")
        **kwargs: Configuration parameters

    Returns:
        Appropriate configuration instance
    """
    config_classes = {
        "base": BaseServiceConfig,
        "fastapi": FastAPIServiceConfig,
        "grpc": GRPCServiceConfig,
        "hybrid": HybridServiceConfig,
    }

    config_class = config_classes.get(service_type, BaseServiceConfig)
    return config_class(**kwargs)
