"""Enhanced gRPC interceptors with comprehensive error handling and monitoring."""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from typing import Any

import grpc
from grpc import aio as grpc_aio

from .circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from .error_codes import ErrorCategory, MartyError, TransientBackendError, map_exception_to_status

logger = logging.getLogger(__name__)


class AdvancedFailureInjectionConfig:
    """Enhanced failure injection configuration with more control options."""

    def __init__(
        self,
        enabled: bool = False,
        base_failure_rate: float = 0.0,
        method_specific_rates: dict[str, float] | None = None,
        error_types: list[type[Exception]] | None = None,
        target_metadata_key: str = "x-failure-inject",
    ) -> None:
        self.enabled = enabled
        self.base_failure_rate = max(0.0, min(1.0, base_failure_rate))
        self.method_specific_rates = method_specific_rates or {}
        self.error_types = error_types or [TransientBackendError]
        self.target_metadata_key = target_metadata_key

    def should_fail(self, method: str = "", force: bool = False) -> bool:
        """Determine if failure should be injected for this request."""
        if not self.enabled:
            return False
        if force:
            return True

        # Check method-specific rate first
        failure_rate = self.method_specific_rates.get(method, self.base_failure_rate)
        return random.random() < failure_rate  # noqa: S311

    def get_error_to_inject(self) -> Exception:
        """Get a random error from the configured error types."""
        error_class = random.choice(self.error_types)  # noqa: S311
        if error_class == TransientBackendError:
            return TransientBackendError("Injected failure for resilience testing")
        return error_class("Injected failure for testing")


class RequestMetrics:
    """Track metrics for individual requests and methods."""

    def __init__(self) -> None:
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.circuit_breaker_rejections = 0
        self.injected_failures = 0
        self.error_counts_by_type: dict[str, int] = {}
        self.last_request_time = 0.0
        self.average_response_time = 0.0
        self._response_times: list[float] = []

    def record_request_start(self) -> float:
        """Record the start of a request and return start time."""
        self.total_requests += 1
        self.last_request_time = time.time()
        return self.last_request_time

    def record_request_success(self, start_time: float) -> None:
        """Record a successful request completion."""
        self.successful_requests += 1
        self._record_response_time(start_time)

    def record_request_failure(
        self, start_time: float, error_type: str, is_injected: bool = False
    ) -> None:
        """Record a failed request."""
        self.failed_requests += 1
        if is_injected:
            self.injected_failures += 1
        self.error_counts_by_type[error_type] = self.error_counts_by_type.get(error_type, 0) + 1
        self._record_response_time(start_time)

    def record_circuit_breaker_rejection(self) -> None:
        """Record a circuit breaker rejection."""
        self.circuit_breaker_rejections += 1

    def _record_response_time(self, start_time: float) -> None:
        """Record response time and update average."""
        response_time = time.time() - start_time
        self._response_times.append(response_time)

        # Keep only last 100 response times for rolling average
        if len(self._response_times) > 100:
            self._response_times.pop(0)

        self.average_response_time = sum(self._response_times) / len(self._response_times)

    def get_stats(self) -> dict[str, Any]:
        """Get comprehensive statistics."""
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "circuit_breaker_rejections": self.circuit_breaker_rejections,
            "injected_failures": self.injected_failures,
            "error_counts_by_type": dict(self.error_counts_by_type),
            "success_rate": (
                self.successful_requests / self.total_requests if self.total_requests > 0 else 0.0
            ),
            "average_response_time": self.average_response_time,
            "last_request_time": self.last_request_time,
        }


class EnhancedResilienceInterceptor(grpc_aio.ServerInterceptor):
    """Enhanced resilience interceptor with comprehensive error handling and monitoring."""

    def __init__(
        self,
        failure_injection: AdvancedFailureInjectionConfig | None = None,
        circuit_breaker_config: CircuitBreakerConfig | None = None,
        enable_detailed_logging: bool = True,
    ) -> None:
        self.failure_injection = failure_injection or AdvancedFailureInjectionConfig()
        self.circuit_breaker_config = circuit_breaker_config or CircuitBreakerConfig()
        self.enable_detailed_logging = enable_detailed_logging

        # Per-method circuit breakers and metrics
        self._circuit_breakers: dict[str, CircuitBreaker] = {}
        self._method_metrics: dict[str, RequestMetrics] = {}

    def get_circuit_breaker(self, method: str) -> CircuitBreaker:
        """Get or create circuit breaker for a method."""
        if method not in self._circuit_breakers:
            self._circuit_breakers[method] = CircuitBreaker(
                name=f"grpc.{method}", config=self.circuit_breaker_config
            )
        return self._circuit_breakers[method]

    def get_method_metrics(self, method: str) -> RequestMetrics:
        """Get or create metrics for a method."""
        if method not in self._method_metrics:
            self._method_metrics[method] = RequestMetrics()
        return self._method_metrics[method]

    def get_all_metrics(self) -> dict[str, dict[str, Any]]:
        """Get metrics for all methods."""
        return {method: metrics.get_stats() for method, metrics in self._method_metrics.items()}

    def get_circuit_breaker_stats(self) -> dict[str, dict[str, Any]]:
        """Get circuit breaker statistics for all methods."""
        return {method: breaker.stats() for method, breaker in self._circuit_breakers.items()}

    async def intercept_service(self, continuation, handler_call_details):  # type: ignore[override]
        """Intercept and enhance gRPC service calls."""
        handler = await continuation(handler_call_details)
        if handler is None:
            return None

        method = handler_call_details.method
        breaker = self.get_circuit_breaker(method)
        metrics = self.get_method_metrics(method)

        # Enhanced wrapper that preserves streaming semantics
        if handler.unary_unary:
            return grpc.unary_unary_rpc_method_handler(
                self._wrap_unary_unary(handler.unary_unary, breaker, metrics, method),
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )

        if handler.unary_stream:
            return grpc.unary_stream_rpc_method_handler(
                self._wrap_unary_stream(handler.unary_stream, breaker, metrics, method),
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )

        if handler.stream_unary:
            return grpc.stream_unary_rpc_method_handler(
                self._wrap_stream_unary(handler.stream_unary, breaker, metrics, method),
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )

        if handler.stream_stream:
            return grpc.stream_stream_rpc_method_handler(
                self._wrap_stream_stream(handler.stream_stream, breaker, metrics, method),
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )

        return handler

    def _should_inject_failure(self, context: grpc.ServicerContext, method: str) -> bool:
        """Check if failure should be injected for this request."""
        metadata = dict(context.invocation_metadata()) if context.invocation_metadata() else {}
        force = metadata.get(self.failure_injection.target_metadata_key, "false").lower() in {
            "1",
            "true",
            "yes",
        }
        return self.failure_injection.should_fail(method=method, force=force)

    def _classify_error(self, exc: Exception) -> tuple[bool, str]:
        """Classify error for circuit breaker and metrics."""
        error_type = type(exc).__name__

        # Don't trip circuit breaker on client errors
        client_errors = (ValueError, TypeError)
        if isinstance(exc, client_errors):
            return False, error_type

        # Check if it's a MartyError with specific category
        if isinstance(exc, MartyError):
            should_trip = exc.category in {ErrorCategory.TRANSIENT, ErrorCategory.INTERNAL}
            return should_trip, f"MartyError.{exc.category.value}"

        # Default: most exceptions should trip the circuit breaker
        return True, error_type

    def _log_request_details(
        self,
        method: str,
        success: bool,
        duration: float,
        error_type: str | None = None,
        injected: bool = False,
    ) -> None:
        """Log detailed request information if enabled."""
        if not self.enable_detailed_logging:
            return

        log_data = {
            "method": method,
            "success": success,
            "duration_ms": duration * 1000,
        }

        if not success:
            log_data["error_type"] = error_type
            log_data["injected_failure"] = injected

        if success:
            logger.debug("gRPC request completed successfully", extra=log_data)
        else:
            logger.warning("gRPC request failed", extra=log_data)

    def _wrap_unary_unary(
        self, func: Callable, breaker: CircuitBreaker, metrics: RequestMetrics, method: str
    ):
        async def _wrapper(request, context):
            start_time = metrics.record_request_start()

            # Check circuit breaker
            if not breaker.allow_request():
                metrics.record_circuit_breaker_rejection()
                self._log_request_details(method, False, 0.0, "CircuitBreakerOpen")
                await context.abort(
                    grpc.StatusCode.UNAVAILABLE, f"Circuit breaker is open for {method}"
                )

            # Check for failure injection
            if self._should_inject_failure(context, method):
                injected_error = self.failure_injection.get_error_to_inject()
                breaker.record_failure(injected_error)
                duration = time.time() - start_time
                metrics.record_request_failure(start_time, type(injected_error).__name__, True)
                self._log_request_details(
                    method, False, duration, type(injected_error).__name__, True
                )
                status, message = map_exception_to_status(injected_error)
                await context.abort(status, message)

            try:
                result = func(request, context)
                if hasattr(result, "__await__"):
                    result = await result

                # Success
                breaker.record_success()
                duration = time.time() - start_time
                metrics.record_request_success(start_time)
                self._log_request_details(method, True, duration)
                return result

            except grpc.RpcError:
                # Let gRPC errors pass through unchanged
                duration = time.time() - start_time
                metrics.record_request_failure(start_time, "gRPC.RpcError")
                self._log_request_details(method, False, duration, "gRPC.RpcError")
                raise
            except Exception as exc:
                # Handle and translate application exceptions
                should_trip, error_type = self._classify_error(exc)
                duration = time.time() - start_time

                if should_trip:
                    breaker.record_failure(exc)

                metrics.record_request_failure(start_time, error_type)
                self._log_request_details(method, False, duration, error_type)

                status, message = map_exception_to_status(exc)
                await context.abort(status, message)

        return _wrapper

    def _wrap_unary_stream(
        self, func: Callable, breaker: CircuitBreaker, metrics: RequestMetrics, method: str
    ):
        async def _wrapper(request, context):
            start_time = metrics.record_request_start()

            if not breaker.allow_request():
                metrics.record_circuit_breaker_rejection()
                await context.abort(
                    grpc.StatusCode.UNAVAILABLE, f"Circuit breaker is open for {method}"
                )

            if self._should_inject_failure(context, method):
                injected_error = self.failure_injection.get_error_to_inject()
                breaker.record_failure(injected_error)
                metrics.record_request_failure(start_time, type(injected_error).__name__, True)
                status, message = map_exception_to_status(injected_error)
                await context.abort(status, message)

            try:
                stream = func(request, context)
                async for item in stream:  # type: ignore[union-attr]
                    yield item

                breaker.record_success()
                metrics.record_request_success(start_time)

            except grpc.RpcError:
                metrics.record_request_failure(start_time, "gRPC.RpcError")
                raise
            except Exception as exc:
                should_trip, error_type = self._classify_error(exc)
                if should_trip:
                    breaker.record_failure(exc)
                metrics.record_request_failure(start_time, error_type)
                status, message = map_exception_to_status(exc)
                await context.abort(status, message)

        return _wrapper

    def _wrap_stream_unary(
        self, func: Callable, breaker: CircuitBreaker, metrics: RequestMetrics, method: str
    ):
        async def _wrapper(request_iterator, context):
            start_time = metrics.record_request_start()

            if not breaker.allow_request():
                metrics.record_circuit_breaker_rejection()
                await context.abort(
                    grpc.StatusCode.UNAVAILABLE, f"Circuit breaker is open for {method}"
                )

            if self._should_inject_failure(context, method):
                injected_error = self.failure_injection.get_error_to_inject()
                breaker.record_failure(injected_error)
                metrics.record_request_failure(start_time, type(injected_error).__name__, True)
                status, message = map_exception_to_status(injected_error)
                await context.abort(status, message)

            try:
                result = func(request_iterator, context)
                if hasattr(result, "__await__"):
                    result = await result

                breaker.record_success()
                metrics.record_request_success(start_time)
                return result

            except grpc.RpcError:
                metrics.record_request_failure(start_time, "gRPC.RpcError")
                raise
            except Exception as exc:
                should_trip, error_type = self._classify_error(exc)
                if should_trip:
                    breaker.record_failure(exc)
                metrics.record_request_failure(start_time, error_type)
                status, message = map_exception_to_status(exc)
                await context.abort(status, message)

        return _wrapper

    def _wrap_stream_stream(
        self, func: Callable, breaker: CircuitBreaker, metrics: RequestMetrics, method: str
    ):
        async def _wrapper(request_iterator, context):
            start_time = metrics.record_request_start()

            if not breaker.allow_request():
                metrics.record_circuit_breaker_rejection()
                await context.abort(
                    grpc.StatusCode.UNAVAILABLE, f"Circuit breaker is open for {method}"
                )

            if self._should_inject_failure(context, method):
                injected_error = self.failure_injection.get_error_to_inject()
                breaker.record_failure(injected_error)
                metrics.record_request_failure(start_time, type(injected_error).__name__, True)
                status, message = map_exception_to_status(injected_error)
                await context.abort(status, message)

            try:
                stream = func(request_iterator, context)
                async for item in stream:  # type: ignore[union-attr]
                    yield item

                breaker.record_success()
                metrics.record_request_success(start_time)

            except grpc.RpcError:
                metrics.record_request_failure(start_time, "gRPC.RpcError")
                raise
            except Exception as exc:
                should_trip, error_type = self._classify_error(exc)
                if should_trip:
                    breaker.record_failure(exc)
                metrics.record_request_failure(start_time, error_type)
                status, message = map_exception_to_status(exc)
                await context.abort(status, message)

        return _wrapper


__all__ = [
    "AdvancedFailureInjectionConfig",
    "EnhancedResilienceInterceptor",
    "RequestMetrics",
]
