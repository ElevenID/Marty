"""
gRPC interceptor for Prometheus metrics collection in Marty microservices.

This module provides interceptors that automatically collect metrics for all
gRPC method calls, including request rates, durations, and error rates.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

import grpc
from grpc import aio as grpc_aio

from .metrics_server import get_metrics_server

logger = logging.getLogger(__name__)


class MetricsInterceptor(grpc.ServerInterceptor):
    """gRPC server interceptor for collecting Prometheus metrics."""

    def __init__(self, service_name: str):
        self.service_name = service_name

    def intercept_service(
        self,
        continuation: Callable[..., Any],
        handler_call_details: grpc.HandlerCallDetails,
    ) -> Any:
        """Intercept gRPC service calls to collect metrics."""

        def wrapper(behavior: Callable[..., Any]) -> Callable[..., Any]:
            def wrapped_behavior(request: Any, context: grpc.ServicerContext) -> Any:
                method = handler_call_details.method
                start_time = time.time()

                try:
                    response = behavior(request, context)
                    duration = time.time() - start_time

                    # Record successful request
                    metrics_server = get_metrics_server()
                    if metrics_server:
                        metrics_server.metrics.record_request(method, "OK", duration)
                        metrics_server.metrics.record_successful_operation(method)

                    return response

                except Exception as e:
                    duration = time.time() - start_time
                    error_type = type(e).__name__

                    # Record error
                    metrics_server = get_metrics_server()
                    if metrics_server:
                        metrics_server.metrics.record_request(method, "ERROR", duration)
                        metrics_server.metrics.record_error(method, error_type)

                    raise

            return wrapped_behavior

        return wrapper(continuation(handler_call_details))


class AsyncMetricsInterceptor(grpc_aio.ServerInterceptor):
    """Async gRPC server interceptor for collecting Prometheus metrics."""

    def __init__(self, service_name: str):
        self.service_name = service_name

    async def intercept_service(
        self,
        continuation: Callable[..., Any],
        handler_call_details: grpc.HandlerCallDetails,
    ) -> Any:
        """Intercept async gRPC service calls to collect metrics."""

        def wrapper(behavior: Callable[..., Any]) -> Callable[..., Any]:
            async def wrapped_behavior(request: Any, context: grpc_aio.ServicerContext) -> Any:
                method = handler_call_details.method
                start_time = time.time()

                try:
                    response = await behavior(request, context)
                    duration = time.time() - start_time

                    # Record successful request
                    metrics_server = get_metrics_server()
                    if metrics_server:
                        metrics_server.metrics.record_request(method, "OK", duration)
                        metrics_server.metrics.record_successful_operation(method)

                    return response

                except Exception as e:
                    duration = time.time() - start_time
                    error_type = type(e).__name__

                    # Record error
                    metrics_server = get_metrics_server()
                    if metrics_server:
                        metrics_server.metrics.record_request(method, "ERROR", duration)
                        metrics_server.metrics.record_error(method, error_type)

                    raise

            return wrapped_behavior

        return wrapper(await continuation(handler_call_details))


def create_metrics_interceptor(service_name: str) -> MetricsInterceptor:
    """Create a sync gRPC metrics interceptor."""
    return MetricsInterceptor(service_name)


def create_async_metrics_interceptor(service_name: str) -> AsyncMetricsInterceptor:
    """Create an async gRPC metrics interceptor."""
    return AsyncMetricsInterceptor(service_name)
