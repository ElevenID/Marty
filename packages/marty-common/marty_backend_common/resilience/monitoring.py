"""Enhanced monitoring and observability for resilience patterns."""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

from .advanced_retry import AdvancedRetryManager
from .circuit_breaker import CircuitBreaker
from .metrics import MetricsCollector


@dataclass
class ResilienceHealthCheck:
    """Health check result for resilience components."""

    component_name: str
    healthy: bool
    status: str
    details: dict[str, Any] = field(default_factory=dict)
    last_check_time: float = field(default_factory=time.time)


class ResilienceMonitor:
    """Centralized monitoring for all resilience patterns."""

    def __init__(self) -> None:
        self.metrics = MetricsCollector()
        self._circuit_breakers: dict[str, CircuitBreaker] = {}
        self._retry_managers: dict[str, AdvancedRetryManager] = {}
        self._lock = Lock()

        # Health thresholds
        self.circuit_breaker_failure_threshold = 0.8
        self.retry_failure_threshold = 0.7

    def register_circuit_breaker(self, name: str, circuit_breaker: CircuitBreaker) -> None:
        """Register a circuit breaker for monitoring."""
        with self._lock:
            self._circuit_breakers[name] = circuit_breaker

    def register_retry_manager(self, name: str, retry_manager: AdvancedRetryManager) -> None:
        """Register a retry manager for monitoring."""
        with self._lock:
            self._retry_managers[name] = retry_manager

    def get_circuit_breaker_health(self, name: str) -> ResilienceHealthCheck:
        """Get health status for a specific circuit breaker."""
        if name not in self._circuit_breakers:
            return ResilienceHealthCheck(
                component_name=name, healthy=False, status="Circuit breaker not found"
            )

        cb = self._circuit_breakers[name]
        health_info = cb.health_check()
        stats = cb.stats()

        # Calculate failure rate
        total_requests = stats["total_requests"]
        failure_rate = stats["total_failures"] / total_requests if total_requests > 0 else 0.0

        # Determine health based on state and failure rate
        healthy = health_info["healthy"] and failure_rate < self.circuit_breaker_failure_threshold

        return ResilienceHealthCheck(
            component_name=name,
            healthy=healthy,
            status=f"State: {health_info['state']}, Failure rate: {failure_rate:.2%}",
            details={
                "state": health_info["state"],
                "failure_rate": failure_rate,
                "total_requests": total_requests,
                "time_until_recovery": health_info.get("time_until_recovery"),
                **stats,
            },
        )

    def get_retry_manager_health(self, name: str) -> ResilienceHealthCheck:
        """Get health status for a specific retry manager."""
        if name not in self._retry_managers:
            return ResilienceHealthCheck(
                component_name=name, healthy=False, status="Retry manager not found"
            )

        rm = self._retry_managers[name]
        stats = rm.metrics.get_stats()

        success_rate = stats["overall_success_rate"]
        healthy = success_rate >= self.retry_failure_threshold

        return ResilienceHealthCheck(
            component_name=name,
            healthy=healthy,
            status=f"Success rate: {success_rate:.2%}",
            details=stats,
        )

    def get_overall_health(self) -> dict[str, Any]:
        """Get overall health status of all resilience components."""
        circuit_breaker_health = {}
        retry_manager_health = {}

        with self._lock:
            # Check all circuit breakers
            for name in self._circuit_breakers:
                health = self.get_circuit_breaker_health(name)
                circuit_breaker_health[name] = {
                    "healthy": health.healthy,
                    "status": health.status,
                    "details": health.details,
                }

            # Check all retry managers
            for name in self._retry_managers:
                health = self.get_retry_manager_health(name)
                retry_manager_health[name] = {
                    "healthy": health.healthy,
                    "status": health.status,
                    "details": health.details,
                }

        # Calculate overall health
        all_components_healthy = all(h["healthy"] for h in circuit_breaker_health.values()) and all(
            h["healthy"] for h in retry_manager_health.values()
        )

        return {
            "overall_healthy": all_components_healthy,
            "circuit_breakers": circuit_breaker_health,
            "retry_managers": retry_manager_health,
            "timestamp": time.time(),
        }

    def get_metrics_summary(self) -> dict[str, Any]:
        """Get a summary of all collected metrics."""
        # Get metrics from the centralized collector
        metrics_data = {}

        # Add circuit breaker metrics
        cb_metrics = {}
        with self._lock:
            for name, cb in self._circuit_breakers.items():
                cb_metrics[name] = cb.stats()

        # Add retry manager metrics
        rm_metrics = {}
        with self._lock:
            for name, rm in self._retry_managers.items():
                rm_metrics[name] = rm.metrics.get_stats()

        return {
            "circuit_breakers": cb_metrics,
            "retry_managers": rm_metrics,
            "system_metrics": {
                "total_circuit_breakers": len(self._circuit_breakers),
                "total_retry_managers": len(self._retry_managers),
                "timestamp": time.time(),
            },
        }

    def generate_health_report(self) -> str:
        """Generate a human-readable health report."""
        health = self.get_overall_health()

        report_lines = [
            "Resilience Health Report",
            "=" * 50,
            f"Overall Status: {'HEALTHY' if health['overall_healthy'] else 'UNHEALTHY'}",
            f"Generated at: {time.ctime(health['timestamp'])}",
            "",
        ]

        # Circuit breaker status
        if health["circuit_breakers"]:
            report_lines.extend(
                [
                    "Circuit Breakers:",
                    "-" * 20,
                ]
            )
            for name, status in health["circuit_breakers"].items():
                health_icon = "✅" if status["healthy"] else "❌"
                report_lines.append(f"{health_icon} {name}: {status['status']}")
            report_lines.append("")

        # Retry manager status
        if health["retry_managers"]:
            report_lines.extend(
                [
                    "Retry Managers:",
                    "-" * 20,
                ]
            )
            for name, status in health["retry_managers"].items():
                health_icon = "✅" if status["healthy"] else "❌"
                report_lines.append(f"{health_icon} {name}: {status['status']}")
            report_lines.append("")

        return "\n".join(report_lines)


# Global monitor instance
_global_monitor = ResilienceMonitor()


def get_global_monitor() -> ResilienceMonitor:
    """Get the global resilience monitor instance."""
    return _global_monitor


def register_circuit_breaker_for_monitoring(name: str, circuit_breaker: CircuitBreaker) -> None:
    """Register a circuit breaker with the global monitor."""
    _global_monitor.register_circuit_breaker(name, circuit_breaker)


def register_retry_manager_for_monitoring(name: str, retry_manager: AdvancedRetryManager) -> None:
    """Register a retry manager with the global monitor."""
    _global_monitor.register_retry_manager(name, retry_manager)


def get_resilience_health_status() -> dict[str, Any]:
    """Get overall resilience health status from the global monitor."""
    return _global_monitor.get_overall_health()


def generate_resilience_health_report() -> str:
    """Generate a health report from the global monitor."""
    return _global_monitor.generate_health_report()


__all__ = [
    "ResilienceHealthCheck",
    "ResilienceMonitor",
    "generate_resilience_health_report",
    "get_global_monitor",
    "get_resilience_health_status",
    "register_circuit_breaker_for_monitoring",
    "register_retry_manager_for_monitoring",
]
