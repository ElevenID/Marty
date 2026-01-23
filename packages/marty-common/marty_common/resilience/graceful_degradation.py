"""Graceful degradation and fallback mechanisms for service resilience."""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypeVar

logger = logging.getLogger(__name__)
T = TypeVar("T")


class DegradationLevel(str, Enum):
    """Levels of service degradation."""

    NONE = "none"
    MINIMAL = "minimal"
    PARTIAL = "partial"
    SIGNIFICANT = "significant"
    EMERGENCY = "emergency"


class FallbackStrategy(str, Enum):
    """Different fallback strategies."""

    CACHED_RESPONSE = "cached_response"
    DEFAULT_VALUE = "default_value"
    SIMPLIFIED_RESPONSE = "simplified_response"
    REDIRECT_TO_BACKUP = "redirect_to_backup"
    GRACEFUL_FAILURE = "graceful_failure"
    FEATURE_TOGGLE_OFF = "feature_toggle_off"


@dataclass
class DegradationConfig:
    """Configuration for graceful degradation behavior."""

    level: DegradationLevel = DegradationLevel.NONE
    enabled_features: list[str] = field(default_factory=list)
    disabled_features: list[str] = field(default_factory=list)
    cache_ttl_seconds: int = 300
    timeout_seconds: float = 5.0
    max_concurrent_requests: int = 100

    def is_feature_enabled(self, feature: str) -> bool:
        """Check if a feature is enabled in this degradation level."""
        if self.disabled_features and feature in self.disabled_features:
            return False
        if self.enabled_features:
            return feature in self.enabled_features
        # If no explicit configuration, assume enabled for minimal degradation
        return self.level in {DegradationLevel.NONE, DegradationLevel.MINIMAL}


class FallbackProvider(ABC):
    """Abstract base class for fallback value providers."""

    @abstractmethod
    async def get_fallback(self, context: dict[str, Any]) -> Any:
        """Get fallback value for the given context."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this fallback provider is currently available."""
        pass


class CachedResponseProvider(FallbackProvider):
    """Fallback provider that returns cached responses."""

    def __init__(self, cache_ttl: int = 300) -> None:
        self.cache: dict[str, tuple[Any, float]] = {}
        self.cache_ttl = cache_ttl

    async def get_fallback(self, context: dict[str, Any]) -> Any:
        """Get cached response if available and not expired."""
        cache_key = self._generate_cache_key(context)
        if cache_key in self.cache:
            value, timestamp = self.cache[cache_key]
            if time.time() - timestamp < self.cache_ttl:
                logger.info("Returning cached fallback response for key: %s", cache_key)
                return value
        return None

    def cache_response(self, context: dict[str, Any], response: Any) -> None:
        """Cache a successful response for future fallback use."""
        cache_key = self._generate_cache_key(context)
        self.cache[cache_key] = (response, time.time())

    def is_available(self) -> bool:
        """Check if cache has any valid entries."""
        current_time = time.time()
        return any(
            current_time - timestamp < self.cache_ttl for _, timestamp in self.cache.values()
        )

    def _generate_cache_key(self, context: dict[str, Any]) -> str:
        """Generate cache key from context."""
        # Simple key generation - in production, use more sophisticated hashing
        key_parts = []
        for key in sorted(context.keys()):
            if isinstance(context[key], (str, int, float, bool)):
                key_parts.append(f"{key}:{context[key]}")
        return "|".join(key_parts)


class DefaultValueProvider(FallbackProvider):
    """Fallback provider that returns configured default values."""

    def __init__(self, default_value: Any) -> None:
        self.default_value = default_value

    async def get_fallback(self, context: dict[str, Any]) -> Any:
        """Return the configured default value."""
        logger.info("Returning default fallback value")
        return self.default_value

    def is_available(self) -> bool:
        """Default values are always available."""
        return True


class BackupServiceProvider(FallbackProvider):
    """Fallback provider that redirects to backup service."""

    def __init__(self, backup_service_call: Callable[[dict[str, Any]], Awaitable[Any]]) -> None:
        self.backup_service_call = backup_service_call
        self._available = True

    async def get_fallback(self, context: dict[str, Any]) -> Any:
        """Call backup service."""
        try:
            logger.info("Calling backup service for fallback")
            return await self.backup_service_call(context)
        except Exception as exc:
            logger.warning("Backup service call failed: %s", exc)
            self._available = False
            raise

    def is_available(self) -> bool:
        """Check if backup service is available."""
        return self._available


@dataclass
class GracefulDegradationManager:
    """Manages graceful degradation across service features."""

    current_level: DegradationLevel = DegradationLevel.NONE
    config: DegradationConfig = field(default_factory=DegradationConfig)
    fallback_providers: dict[str, list[FallbackProvider]] = field(default_factory=dict)
    feature_health: dict[str, bool] = field(default_factory=dict)

    def set_degradation_level(self, level: DegradationLevel) -> None:
        """Set the current degradation level."""
        old_level = self.current_level
        self.current_level = level
        self.config.level = level

        logger.warning(
            "Service degradation level changed from %s to %s", old_level.value, level.value
        )

    def add_fallback_provider(self, feature: str, provider: FallbackProvider) -> None:
        """Add a fallback provider for a specific feature."""
        if feature not in self.fallback_providers:
            self.fallback_providers[feature] = []
        self.fallback_providers[feature].append(provider)

    def set_feature_health(self, feature: str, healthy: bool) -> None:
        """Set the health status of a feature."""
        was_healthy = self.feature_health.get(feature, True)
        self.feature_health[feature] = healthy

        if was_healthy and not healthy:
            logger.warning("Feature '%s' marked as unhealthy", feature)
        elif not was_healthy and healthy:
            logger.info("Feature '%s' recovered and marked as healthy", feature)

    async def execute_with_fallback(
        self,
        feature: str,
        primary_operation: Callable[[], Awaitable[T]],
        context: dict[str, Any] | None = None,
    ) -> T:
        """Execute operation with fallback handling."""
        context = context or {}

        # Check if feature is enabled at current degradation level
        if not self.config.is_feature_enabled(feature):
            logger.info(
                "Feature '%s' disabled at degradation level %s", feature, self.current_level.value
            )
            return await self._get_fallback_response(feature, context)

        # Check feature health
        if not self.feature_health.get(feature, True):
            logger.info("Feature '%s' unhealthy, using fallback", feature)
            return await self._get_fallback_response(feature, context)

        # Try primary operation with timeout
        try:
            result = await asyncio.wait_for(
                primary_operation(), timeout=self.config.timeout_seconds
            )

            # Cache successful response if we have a cache provider
            await self._cache_successful_response(feature, context, result)
            return result

        except asyncio.TimeoutError:
            logger.warning("Feature '%s' timed out, using fallback", feature)
            self.set_feature_health(feature, False)
            return await self._get_fallback_response(feature, context)

        except Exception as exc:
            logger.warning("Feature '%s' failed with error: %s, using fallback", feature, exc)
            self.set_feature_health(feature, False)
            return await self._get_fallback_response(feature, context)

    async def _get_fallback_response(self, feature: str, context: dict[str, Any]) -> Any:
        """Get fallback response using available providers."""
        providers = self.fallback_providers.get(feature, [])

        for provider in providers:
            if provider.is_available():
                try:
                    result = await provider.get_fallback(context)
                    if result is not None:
                        return result
                except Exception as exc:
                    logger.warning("Fallback provider failed: %s", exc)
                    continue

        # No fallback available
        logger.error("No fallback available for feature '%s'", feature)
        from .enhanced_errors import TransientError

        raise TransientError(f"Feature '{feature}' unavailable and no fallback configured")

    async def _cache_successful_response(
        self, feature: str, context: dict[str, Any], response: Any
    ) -> None:
        """Cache successful response in available cache providers."""
        providers = self.fallback_providers.get(feature, [])
        for provider in providers:
            if isinstance(provider, CachedResponseProvider):
                provider.cache_response(context, response)
                break


class FeatureToggle:
    """Feature toggle with degradation-aware behavior."""

    def __init__(
        self,
        name: str,
        default_enabled: bool = True,
        degradation_manager: GracefulDegradationManager | None = None,
    ) -> None:
        self.name = name
        self.default_enabled = default_enabled
        self.degradation_manager = degradation_manager
        self._force_enabled: bool | None = None
        self._force_disabled: bool | None = None

    def is_enabled(self) -> bool:
        """Check if feature is enabled considering degradation level."""
        if self._force_disabled:
            return False
        if self._force_enabled:
            return True

        if self.degradation_manager:
            return self.degradation_manager.config.is_feature_enabled(self.name)

        return self.default_enabled

    def force_enable(self) -> None:
        """Force enable this feature regardless of degradation level."""
        self._force_enabled = True
        self._force_disabled = False

    def force_disable(self) -> None:
        """Force disable this feature regardless of degradation level."""
        self._force_disabled = True
        self._force_enabled = False

    def reset(self) -> None:
        """Reset to default behavior."""
        self._force_enabled = None
        self._force_disabled = None


class HealthBasedDegradationMonitor:
    """Monitor system health and automatically adjust degradation levels."""

    def __init__(self, degradation_manager: GracefulDegradationManager) -> None:
        self.degradation_manager = degradation_manager
        self.health_checks: list[Callable[[], Awaitable[bool]]] = []
        self.monitoring_enabled = False
        self.check_interval = 30.0  # seconds

    def add_health_check(self, health_check: Callable[[], Awaitable[bool]]) -> None:
        """Add a health check function."""
        self.health_checks.append(health_check)

    async def start_monitoring(self) -> None:
        """Start continuous health monitoring."""
        self.monitoring_enabled = True
        logger.info("Starting health-based degradation monitoring")

        while self.monitoring_enabled:
            try:
                await self._perform_health_checks()
                await asyncio.sleep(self.check_interval)
            except Exception as exc:
                logger.error("Error in health monitoring: %s", exc)
                await asyncio.sleep(self.check_interval)

    def stop_monitoring(self) -> None:
        """Stop health monitoring."""
        self.monitoring_enabled = False
        logger.info("Stopped health-based degradation monitoring")

    async def _perform_health_checks(self) -> None:
        """Perform all health checks and adjust degradation level."""
        if not self.health_checks:
            return

        healthy_checks = 0
        total_checks = len(self.health_checks)

        for health_check in self.health_checks:
            try:
                if await health_check():
                    healthy_checks += 1
            except Exception as exc:
                logger.warning("Health check failed: %s", exc)

        health_ratio = healthy_checks / total_checks

        # Determine appropriate degradation level based on health
        if health_ratio >= 0.9:
            target_level = DegradationLevel.NONE
        elif health_ratio >= 0.7:
            target_level = DegradationLevel.MINIMAL
        elif health_ratio >= 0.5:
            target_level = DegradationLevel.PARTIAL
        elif health_ratio >= 0.3:
            target_level = DegradationLevel.SIGNIFICANT
        else:
            target_level = DegradationLevel.EMERGENCY

        if target_level != self.degradation_manager.current_level:
            self.degradation_manager.set_degradation_level(target_level)


# Convenience decorators for graceful degradation
def with_graceful_degradation(
    feature: str,
    degradation_manager: GracefulDegradationManager | None = None,
    fallback_value: Any = None,
):
    """Decorator to add graceful degradation to a function."""

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            manager = degradation_manager or GracefulDegradationManager()

            # Add default fallback if provided
            if fallback_value is not None and feature not in manager.fallback_providers:
                manager.add_fallback_provider(feature, DefaultValueProvider(fallback_value))

            return await manager.execute_with_fallback(
                feature, lambda: func(*args, **kwargs), {"args": args, "kwargs": kwargs}
            )

        return wrapper

    return decorator


__all__ = [
    "BackupServiceProvider",
    "CachedResponseProvider",
    "DefaultValueProvider",
    "DegradationConfig",
    "DegradationLevel",
    "FallbackProvider",
    "FallbackStrategy",
    "FeatureToggle",
    "GracefulDegradationManager",
    "HealthBasedDegradationMonitor",
    "with_graceful_degradation",
]
