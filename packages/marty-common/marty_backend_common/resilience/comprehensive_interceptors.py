"""Comprehensive gRPC interceptors for resilience, error handling, and monitoring."""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Awaitable, Callable
from typing import Any

import grpc
from grpc import aio as grpc_aio

from .advanced_retry import AdvancedRetryConfig, AdvancedRetryManager
from .circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from .enhanced_interceptors import AdvancedFailureInjectionConfig
from .error_codes import map_exception_to_status
from .metrics import MetricsCollector

logger = logging.getLogger(__name__)


class ResilienceClientInterceptor(grpc.UnaryUnaryClientInterceptor):
    """Client-side interceptor for resilience patterns and error handling."""

    def __init__(
        self,
        service_name: str,
        retry_config: AdvancedRetryConfig | None = None,
        circuit_breaker_config: CircuitBreakerConfig | None = None,
        enable_metrics: bool = True,
    ) -> None:
        self.service_name = service_name
        self.enable_metrics = enable_metrics

        # Initialize retry manager
        self.retry_manager = AdvancedRetryManager(
            name=f"{service_name}_client", config=retry_config or AdvancedRetryConfig()
        )

        # Initialize circuit breaker
        cb_config = circuit_breaker_config or CircuitBreakerConfig()
        self.circuit_breaker = CircuitBreaker(f"{service_name}_client_cb", cb_config)

        # Initialize metrics
        self.metrics = MetricsCollector() if enable_metrics else None

        # Per-method circuit breakers
        self._method_circuit_breakers: dict[str, CircuitBreaker] = {}

    def _get_method_circuit_breaker(self, method: str) -> CircuitBreaker:
        """Get or create a circuit breaker for a specific method."""
        if method not in self._method_circuit_breakers:
            config = CircuitBreakerConfig(
                failure_threshold=3,  # Lower threshold for individual methods
                recovery_timeout=15.0,  # Faster recovery for methods
            )
            self._method_circuit_breaker = CircuitBreaker(f"{self.service_name}_{method}", config)
            self._method_circuit_breakers[method] = self._method_circuit_breaker
        return self._method_circuit_breakers[method]

    def _should_retry_grpc_error(self, error: grpc.RpcError) -> bool:
        """Determine if a gRPC error should be retried."""
        # Get the status code
        try:
            status_code = error.code()
        except AttributeError:
            return False

        # Retry on specific transient errors
        retryable_codes = {
            grpc.StatusCode.UNAVAILABLE,
            grpc.StatusCode.DEADLINE_EXCEEDED,
            grpc.StatusCode.RESOURCE_EXHAUSTED,
            grpc.StatusCode.ABORTED,
            grpc.StatusCode.INTERNAL,  # Sometimes transient
        }

        return status_code in retryable_codes

    def _record_request_metrics(
        self, method: str, start_time: float, success: bool, error: Exception | None = None
    ) -> None:
        """Record request metrics."""
        if not self.metrics:
            return

        duration_ms = (time.time() - start_time) * 1000

        # Record basic metrics
        labels = {"service": self.service_name, "method": method, "success": str(success)}

        self.metrics.increment_counter("grpc_client_requests_total", labels)
        self.metrics.observe_histogram("grpc_client_request_duration_ms", duration_ms, labels)

        if error:
            error_type = type(error).__name__
            if isinstance(error, grpc.RpcError):
                try:
                    error_code = error.code().name
                    self.metrics.increment_counter(
                        "grpc_client_errors_total",
                        {**labels, "error_type": error_type, "grpc_code": error_code},
                    )
                except AttributeError:
                    pass

    def intercept_unary_unary(
        self,
        continuation: Callable[[grpc.ClientCallDetails, Any], grpc.Call],
        client_call_details: grpc.ClientCallDetails,
        request: Any,
    ) -> grpc.Call:
        """Intercept unary-unary client calls for resilience."""
        method = client_call_details.method
        start_time = time.time()

        # Get method-specific circuit breaker
        method_cb = self._get_method_circuit_breaker(method)

        def make_call() -> grpc.Call:
            """Make the actual gRPC call."""
            # Check circuit breakers
            if not self.circuit_breaker.allow_request():
                error_msg = f"Service circuit breaker is open for {self.service_name}"
                raise grpc.RpcError(error_msg)

            if not method_cb.allow_request():
                error_msg = f"Method circuit breaker is open for {method}"
                raise grpc.RpcError(error_msg)

            try:
                # Make the call
                call = continuation(client_call_details, request)

                # Get the result to trigger any errors
                result = call.result()

                # Record success
                self.circuit_breaker.record_success()
                method_cb.record_success()
                self._record_request_metrics(method, start_time, True)

                return call

            except grpc.RpcError as error:
                # Record failure for circuit breakers
                if self._should_retry_grpc_error(error):
                    self.circuit_breaker.record_failure(error)
                    method_cb.record_failure(error)

                self._record_request_metrics(method, start_time, False, error)
                raise
            except Exception as error:
                # Record non-gRPC errors
                self.circuit_breaker.record_failure(error)
                method_cb.record_failure(error)
                self._record_request_metrics(method, start_time, False, error)
                raise

        # Use retry manager for resilient calls
        try:
            return self.retry_manager.retry_sync(make_call)
        except Exception as error:
            logger.exception("Client call failed after retries for %s", method)
            raise


class AsyncResilienceClientInterceptor(grpc_aio.UnaryUnaryClientInterceptor):
    """Async client-side interceptor for resilience patterns and error handling."""

    def __init__(
        self,
        service_name: str,
        retry_config: AdvancedRetryConfig | None = None,
        circuit_breaker_config: CircuitBreakerConfig | None = None,
        enable_metrics: bool = True,
    ) -> None:
        self.service_name = service_name
        self.enable_metrics = enable_metrics

        # Initialize retry manager
        self.retry_manager = AdvancedRetryManager(
            name=f"{service_name}_async_client", config=retry_config or AdvancedRetryConfig()
        )

        # Initialize circuit breaker
        cb_config = circuit_breaker_config or CircuitBreakerConfig()
        self.circuit_breaker = CircuitBreaker(f"{service_name}_async_client_cb", cb_config)

        # Initialize metrics
        self.metrics = MetricsCollector() if enable_metrics else None

        # Per-method circuit breakers
        self._method_circuit_breakers: dict[str, CircuitBreaker] = {}

    def _get_method_circuit_breaker(self, method: str) -> CircuitBreaker:
        """Get or create a circuit breaker for a specific method."""
        if method not in self._method_circuit_breakers:
            config = CircuitBreakerConfig(
                failure_threshold=3,
                recovery_timeout=15.0,
            )
            self._method_circuit_breakers[method] = CircuitBreaker(
                f"{self.service_name}_{method}_async", config
            )
        return self._method_circuit_breakers[method]

    def _should_retry_grpc_error(self, error: grpc.aio.AioRpcError) -> bool:
        """Determine if an async gRPC error should be retried."""
        try:
            status_code = error.code()
        except AttributeError:
            return False

        retryable_codes = {
            grpc.StatusCode.UNAVAILABLE,
            grpc.StatusCode.DEADLINE_EXCEEDED,
            grpc.StatusCode.RESOURCE_EXHAUSTED,
            grpc.StatusCode.ABORTED,
            grpc.StatusCode.INTERNAL,
        }

        return status_code in retryable_codes

    async def _record_request_metrics(
        self, method: str, start_time: float, success: bool, error: Exception | None = None
    ) -> None:
        """Record request metrics asynchronously."""
        if not self.metrics:
            return

        duration_ms = (time.time() - start_time) * 1000

        labels = {"service": self.service_name, "method": method, "success": str(success)}

        self.metrics.increment_counter("grpc_async_client_requests_total", labels)
        self.metrics.observe_histogram("grpc_async_client_request_duration_ms", duration_ms, labels)

        if error:
            error_type = type(error).__name__
            if isinstance(error, grpc.aio.AioRpcError):
                try:
                    error_code = error.code().name
                    self.metrics.increment_counter(
                        "grpc_async_client_errors_total",
                        {**labels, "error_type": error_type, "grpc_code": error_code},
                    )
                except AttributeError:
                    pass

    async def intercept_unary_unary(
        self,
        continuation: Callable[[grpc.ClientCallDetails, Any], Awaitable[grpc.Call]],
        client_call_details: grpc.ClientCallDetails,
        request: Any,
    ) -> grpc.Call:
        """Intercept async unary-unary client calls for resilience."""
        method = client_call_details.method
        start_time = time.time()

        # Get method-specific circuit breaker
        method_cb = self._get_method_circuit_breaker(method)

        async def make_call() -> grpc.Call:
            """Make the actual async gRPC call."""
            # Check circuit breakers
            if not self.circuit_breaker.allow_request():
                error_msg = f"Service circuit breaker is open for {self.service_name}"
                raise grpc.aio.AioRpcError(grpc.StatusCode.UNAVAILABLE, error_msg)

            if not method_cb.allow_request():
                error_msg = f"Method circuit breaker is open for {method}"
                raise grpc.aio.AioRpcError(grpc.StatusCode.UNAVAILABLE, error_msg)

            try:
                # Make the call
                call = await continuation(client_call_details, request)

                # Record success
                self.circuit_breaker.record_success()
                method_cb.record_success()
                await self._record_request_metrics(method, start_time, True)

                return call

            except grpc.aio.AioRpcError as error:
                # Record failure for circuit breakers
                if self._should_retry_grpc_error(error):
                    self.circuit_breaker.record_failure(error)
                    method_cb.record_failure(error)

                await self._record_request_metrics(method, start_time, False, error)
                raise
            except Exception as error:
                # Record non-gRPC errors
                self.circuit_breaker.record_failure(error)
                method_cb.record_failure(error)
                await self._record_request_metrics(method, start_time, False, error)
                raise

        # Use retry manager for resilient calls
        try:
            return await self.retry_manager.retry_async(make_call)
        except Exception as error:
            logger.exception("Async client call failed after retries for %s", method)
            raise


class EnhancedResilienceServerInterceptor(grpc.ServerInterceptor):
    """Enhanced server-side interceptor with comprehensive error handling and monitoring."""

    def __init__(
        self,
        service_name: str,
        failure_injection_config: AdvancedFailureInjectionConfig | None = None,
        enable_metrics: bool = True,
        enable_request_logging: bool = True,
    ) -> None:
        self.service_name = service_name
        self.failure_config = failure_injection_config or AdvancedFailureInjectionConfig()
        self.enable_metrics = enable_metrics
        self.enable_request_logging = enable_request_logging

        # Initialize metrics
        self.metrics = MetricsCollector() if enable_metrics else None

        # Request tracking
        self._active_requests = 0

    def _should_inject_failure(self, method: str, context: grpc.ServicerContext) -> bool:
        """Determine if failure should be injected for this request."""
        if not self.failure_config.enabled:
            return False

        # Check for forced failure via metadata
        metadata_dict = dict(context.invocation_metadata())
        force_failure = metadata_dict.get(self.failure_config.target_metadata_key) == "true"

        return self.failure_config.should_fail(method, force_failure)

    def _inject_failure(self, method: str, context: grpc.ServicerContext) -> None:
        """Inject a failure into the request."""
        # Choose a random error type from the configured list
        if self.failure_config.error_types:
            error_type = random.choice(self.failure_config.error_types)
            error_msg = f"Injected failure for {method} (testing)"

            if issubclass(error_type, grpc.RpcError):
                context.abort(grpc.StatusCode.INTERNAL, error_msg)
            else:
                raise error_type(error_msg)

    def _record_server_metrics(
        self, method: str, start_time: float, success: bool, error: Exception | None = None
    ) -> None:
        """Record server-side metrics."""
        if not self.metrics:
            return

        duration_ms = (time.time() - start_time) * 1000

        labels = {"service": self.service_name, "method": method, "success": str(success)}

        self.metrics.increment_counter("grpc_server_requests_total", labels)
        self.metrics.observe_histogram("grpc_server_request_duration_ms", duration_ms, labels)
        self.metrics.set_gauge(
            "grpc_server_active_requests", self._active_requests, {"service": self.service_name}
        )

        if error:
            error_type = type(error).__name__
            self.metrics.increment_counter(
                "grpc_server_errors_total", {**labels, "error_type": error_type}
            )

    def intercept_service(
        self, continuation: Callable, handler_call_details: grpc.HandlerCallDetails
    ) -> grpc.RpcMethodHandler:
        """Intercept server calls for enhanced error handling."""
        original_handler = continuation(handler_call_details)

        if not original_handler:
            return original_handler

        method = handler_call_details.method

        def enhanced_unary_unary(request: Any, context: grpc.ServicerContext) -> Any:
            """Enhanced unary-unary handler with resilience features."""
            start_time = time.time()
            self._active_requests += 1

            if self.enable_request_logging:
                logger.debug("Handling request for %s", method)

            try:
                # Check for failure injection
                if self._should_inject_failure(method, context):
                    self._inject_failure(method, context)

                # Call the original handler
                result = original_handler.unary_unary(request, context)

                # Record success
                self._record_server_metrics(method, start_time, True)

                if self.enable_request_logging:
                    logger.debug("Successfully handled request for %s", method)

                return result

            except Exception as error:
                # Map exception to appropriate gRPC status
                status, details = map_exception_to_status(error)

                # Record failure
                self._record_server_metrics(method, start_time, False, error)

                logger.exception("Request failed for %s", method)

                # Set gRPC status and abort
                context.abort(status, details)

            finally:
                self._active_requests = max(0, self._active_requests - 1)

        # Return the enhanced handler
        if original_handler.unary_unary:
            return grpc.unary_unary_rpc_method_handler(enhanced_unary_unary)

        # Handle other RPC types as needed
        return original_handler


class CompositeResilienceInterceptor:
    """Composite interceptor that combines multiple resilience patterns."""

    def __init__(
        self,
        service_name: str,
        client_retry_config: AdvancedRetryConfig | None = None,
        client_circuit_breaker_config: CircuitBreakerConfig | None = None,
        server_failure_injection_config: AdvancedFailureInjectionConfig | None = None,
        enable_metrics: bool = True,
    ) -> None:
        self.service_name = service_name

        # Create individual interceptors
        self.client_interceptor = ResilienceClientInterceptor(
            service_name=service_name,
            retry_config=client_retry_config,
            circuit_breaker_config=client_circuit_breaker_config,
            enable_metrics=enable_metrics,
        )

        self.async_client_interceptor = AsyncResilienceClientInterceptor(
            service_name=service_name,
            retry_config=client_retry_config,
            circuit_breaker_config=client_circuit_breaker_config,
            enable_metrics=enable_metrics,
        )

        self.server_interceptor = EnhancedResilienceServerInterceptor(
            service_name=service_name,
            failure_injection_config=server_failure_injection_config,
            enable_metrics=enable_metrics,
        )

    def get_client_interceptors(self) -> list[grpc.UnaryUnaryClientInterceptor]:
        """Get client-side interceptors."""
        return [self.client_interceptor]

    def get_async_client_interceptors(self) -> list[grpc_aio.UnaryUnaryClientInterceptor]:
        """Get async client-side interceptors."""
        return [self.async_client_interceptor]

    def get_server_interceptors(self) -> list[grpc.ServerInterceptor]:
        """Get server-side interceptors."""
        return [self.server_interceptor]

    def get_health_status(self) -> dict[str, Any]:
        """Get health status of all resilience components."""
        return {
            "service": self.service_name,
            "client_circuit_breaker": self.client_interceptor.circuit_breaker.health_check(),
            "async_client_circuit_breaker": self.async_client_interceptor.circuit_breaker.health_check(),
            "client_retry_stats": self.client_interceptor.retry_manager.metrics.get_stats(),
            "async_client_retry_stats": self.async_client_interceptor.retry_manager.metrics.get_stats(),
        }


__all__ = [
    "AsyncResilienceClientInterceptor",
    "CompositeResilienceInterceptor",
    "EnhancedResilienceServerInterceptor",
    "ResilienceClientInterceptor",
]
