"""Configuration management for resilience patterns."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .advanced_retry import AdvancedRetryConfig, BackoffStrategy
from .circuit_breaker import CircuitBreakerConfig
from .enhanced_interceptors import AdvancedFailureInjectionConfig


@dataclass
class ResilienceConfig:
    """Comprehensive configuration for all resilience patterns."""

    # Service identification
    service_name: str = "default_service"
    environment: str = "development"

    # Circuit breaker configuration
    circuit_breaker: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)

    # Retry configuration
    retry: AdvancedRetryConfig = field(default_factory=AdvancedRetryConfig)

    # Failure injection configuration (for testing)
    failure_injection: AdvancedFailureInjectionConfig = field(
        default_factory=AdvancedFailureInjectionConfig
    )

    # Monitoring and metrics
    enable_metrics: bool = True
    enable_health_checks: bool = True
    enable_request_logging: bool = True

    # Performance tuning
    max_concurrent_requests: int = 100
    request_timeout_seconds: float = 30.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResilienceConfig:
        """Create configuration from dictionary."""
        config = cls()

        # Basic settings
        config.service_name = data.get("service_name", config.service_name)
        config.environment = data.get("environment", config.environment)
        config.enable_metrics = data.get("enable_metrics", config.enable_metrics)
        config.enable_health_checks = data.get("enable_health_checks", config.enable_health_checks)
        config.enable_request_logging = data.get(
            "enable_request_logging", config.enable_request_logging
        )
        config.max_concurrent_requests = data.get(
            "max_concurrent_requests", config.max_concurrent_requests
        )
        config.request_timeout_seconds = data.get(
            "request_timeout_seconds", config.request_timeout_seconds
        )

        # Circuit breaker configuration
        if "circuit_breaker" in data:
            cb_data = data["circuit_breaker"]
            config.circuit_breaker = CircuitBreakerConfig(
                failure_threshold=cb_data.get("failure_threshold", 5),
                recovery_timeout=cb_data.get("recovery_timeout", 30.0),
                half_open_success_threshold=cb_data.get("half_open_success_threshold", 2),
                failure_reset_timeout=cb_data.get("failure_reset_timeout", 60.0),
                max_concurrent_requests=cb_data.get("max_concurrent_requests", 10),
                enable_metrics=cb_data.get("enable_metrics", True),
            )

        # Retry configuration
        if "retry" in data:
            retry_data = data["retry"]
            backoff_strategy = BackoffStrategy(
                retry_data.get("backoff_strategy", BackoffStrategy.EXPONENTIAL_JITTER.value)
            )

            retry_exceptions = tuple(
                getattr(__builtins__, exc_name, Exception)
                for exc_name in retry_data.get(
                    "retry_on_exceptions", ["ConnectionError", "TimeoutError"]
                )
            )

            abort_exceptions = tuple(
                getattr(__builtins__, exc_name, ValueError)
                for exc_name in retry_data.get("abort_on_exceptions", ["ValueError", "TypeError"])
            )

            config.retry = AdvancedRetryConfig(
                max_attempts=retry_data.get("max_attempts", 5),
                base_delay=retry_data.get("base_delay", 0.1),
                max_delay=retry_data.get("max_delay", 60.0),
                total_timeout=retry_data.get("total_timeout", 300.0),
                backoff_strategy=backoff_strategy,
                jitter_factor=retry_data.get("jitter_factor", 0.1),
                multiplier=retry_data.get("multiplier", 2.0),
                retry_on_exceptions=retry_exceptions,
                abort_on_exceptions=abort_exceptions,
                enable_circuit_breaker=retry_data.get("enable_circuit_breaker", True),
                enable_adaptive_delays=retry_data.get("enable_adaptive_delays", False),
                success_rate_threshold=retry_data.get("success_rate_threshold", 0.8),
                failure_window_size=retry_data.get("failure_window_size", 100),
                max_concurrent_retries=retry_data.get("max_concurrent_retries", 50),
            )

        # Failure injection configuration
        if "failure_injection" in data:
            fi_data = data["failure_injection"]
            config.failure_injection = AdvancedFailureInjectionConfig(
                enabled=fi_data.get("enabled", False),
                base_failure_rate=fi_data.get("base_failure_rate", 0.0),
                method_specific_rates=fi_data.get("method_specific_rates", {}),
                target_metadata_key=fi_data.get("target_metadata_key", "x-failure-inject"),
            )

        return config

    @classmethod
    def from_yaml_file(cls, file_path: str | Path) -> ResilienceConfig:
        """Load configuration from YAML file."""
        path = Path(file_path)
        if not path.exists():
            msg = f"Configuration file not found: {path}"
            raise FileNotFoundError(msg)

        with path.open() as f:
            data = yaml.safe_load(f)

        return cls.from_dict(data)

    @classmethod
    def from_environment(cls, prefix: str = "MARTY_RESILIENCE") -> ResilienceConfig:
        """Load configuration from environment variables."""
        config = cls()

        # Basic settings
        config.service_name = os.getenv(f"{prefix}_SERVICE_NAME", config.service_name)
        config.environment = os.getenv(f"{prefix}_ENVIRONMENT", config.environment)
        config.enable_metrics = os.getenv(f"{prefix}_ENABLE_METRICS", "true").lower() == "true"
        config.enable_health_checks = (
            os.getenv(f"{prefix}_ENABLE_HEALTH_CHECKS", "true").lower() == "true"
        )
        config.enable_request_logging = (
            os.getenv(f"{prefix}_ENABLE_REQUEST_LOGGING", "true").lower() == "true"
        )

        # Circuit breaker settings
        cb_prefix = f"{prefix}_CIRCUIT_BREAKER"
        if os.getenv(f"{cb_prefix}_FAILURE_THRESHOLD"):
            config.circuit_breaker.failure_threshold = int(
                os.getenv(f"{cb_prefix}_FAILURE_THRESHOLD")
            )
        if os.getenv(f"{cb_prefix}_RECOVERY_TIMEOUT"):
            config.circuit_breaker.recovery_timeout = float(
                os.getenv(f"{cb_prefix}_RECOVERY_TIMEOUT")
            )

        # Retry settings
        retry_prefix = f"{prefix}_RETRY"
        if os.getenv(f"{retry_prefix}_MAX_ATTEMPTS"):
            config.retry.max_attempts = int(os.getenv(f"{retry_prefix}_MAX_ATTEMPTS"))
        if os.getenv(f"{retry_prefix}_BASE_DELAY"):
            config.retry.base_delay = float(os.getenv(f"{retry_prefix}_BASE_DELAY"))
        if os.getenv(f"{retry_prefix}_MAX_DELAY"):
            config.retry.max_delay = float(os.getenv(f"{retry_prefix}_MAX_DELAY"))

        # Failure injection settings
        fi_prefix = f"{prefix}_FAILURE_INJECTION"
        config.failure_injection.enabled = (
            os.getenv(f"{fi_prefix}_ENABLED", "false").lower() == "true"
        )
        if os.getenv(f"{fi_prefix}_BASE_FAILURE_RATE"):
            config.failure_injection.base_failure_rate = float(
                os.getenv(f"{fi_prefix}_BASE_FAILURE_RATE")
            )

        return config

    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "service_name": self.service_name,
            "environment": self.environment,
            "enable_metrics": self.enable_metrics,
            "enable_health_checks": self.enable_health_checks,
            "enable_request_logging": self.enable_request_logging,
            "max_concurrent_requests": self.max_concurrent_requests,
            "request_timeout_seconds": self.request_timeout_seconds,
            "circuit_breaker": {
                "failure_threshold": self.circuit_breaker.failure_threshold,
                "recovery_timeout": self.circuit_breaker.recovery_timeout,
                "half_open_success_threshold": self.circuit_breaker.half_open_success_threshold,
                "failure_reset_timeout": self.circuit_breaker.failure_reset_timeout,
                "max_concurrent_requests": self.circuit_breaker.max_concurrent_requests,
                "enable_metrics": self.circuit_breaker.enable_metrics,
            },
            "retry": {
                "max_attempts": self.retry.max_attempts,
                "base_delay": self.retry.base_delay,
                "max_delay": self.retry.max_delay,
                "total_timeout": self.retry.total_timeout,
                "backoff_strategy": self.retry.backoff_strategy.value,
                "jitter_factor": self.retry.jitter_factor,
                "multiplier": self.retry.multiplier,
                "enable_circuit_breaker": self.retry.enable_circuit_breaker,
                "enable_adaptive_delays": self.retry.enable_adaptive_delays,
                "success_rate_threshold": self.retry.success_rate_threshold,
                "failure_window_size": self.retry.failure_window_size,
                "max_concurrent_retries": self.retry.max_concurrent_retries,
            },
            "failure_injection": {
                "enabled": self.failure_injection.enabled,
                "base_failure_rate": self.failure_injection.base_failure_rate,
                "method_specific_rates": self.failure_injection.method_specific_rates,
                "target_metadata_key": self.failure_injection.target_metadata_key,
            },
        }

    def save_to_yaml_file(self, file_path: str | Path) -> None:
        """Save configuration to YAML file."""
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with path.open("w") as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False, indent=2)


def load_config(
    config_file: str | Path | None = None,
    environment_prefix: str = "MARTY_RESILIENCE",
    use_defaults: bool = True,
) -> ResilienceConfig:
    """Load resilience configuration from various sources.

    Priority order:
    1. Explicit config file (if provided)
    2. Environment variables
    3. Default configuration (if use_defaults=True)
    """
    if config_file:
        return ResilienceConfig.from_yaml_file(config_file)

    # Try to load from environment
    try:
        return ResilienceConfig.from_environment(environment_prefix)
    except Exception:
        if use_defaults:
            return ResilienceConfig()
        raise


# Environment-specific configurations
def get_development_config() -> ResilienceConfig:
    """Get configuration optimized for development environment."""
    config = ResilienceConfig()
    config.environment = "development"

    # More lenient settings for development
    config.circuit_breaker.failure_threshold = 10
    config.circuit_breaker.recovery_timeout = 10.0
    config.retry.max_attempts = 3
    config.retry.base_delay = 0.1
    config.retry.max_delay = 5.0

    # Enable failure injection for testing
    config.failure_injection.enabled = True
    config.failure_injection.base_failure_rate = 0.05

    return config


def get_production_config() -> ResilienceConfig:
    """Get configuration optimized for production environment."""
    config = ResilienceConfig()
    config.environment = "production"

    # More conservative settings for production
    config.circuit_breaker.failure_threshold = 5
    config.circuit_breaker.recovery_timeout = 30.0
    config.retry.max_attempts = 5
    config.retry.base_delay = 0.2
    config.retry.max_delay = 60.0

    # Disable failure injection in production
    config.failure_injection.enabled = False
    config.failure_injection.base_failure_rate = 0.0

    # Enable comprehensive monitoring
    config.enable_metrics = True
    config.enable_health_checks = True
    config.enable_request_logging = False  # Reduce log volume in production

    return config


def get_testing_config() -> ResilienceConfig:
    """Get configuration optimized for testing environment."""
    config = ResilienceConfig()
    config.environment = "testing"

    # Fast recovery for testing
    config.circuit_breaker.failure_threshold = 3
    config.circuit_breaker.recovery_timeout = 5.0
    config.retry.max_attempts = 2
    config.retry.base_delay = 0.05
    config.retry.max_delay = 1.0

    # Enable failure injection for testing
    config.failure_injection.enabled = True
    config.failure_injection.base_failure_rate = 0.1

    return config


__all__ = [
    "ResilienceConfig",
    "get_development_config",
    "get_production_config",
    "get_testing_config",
    "load_config",
]
