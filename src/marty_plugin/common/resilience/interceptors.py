"""Composite gRPC resilience interceptor.

Features:
 - Unified exception -> gRPC status translation (leveraging existing MartyServiceException + new MartyError)
 - Circuit breaker for each RPC method (optional, global shared registry)
 - Failure injection (chaos) via environment variable or incoming metadata key

Environment variables:
 MARTY_FAILURE_INJECTION=enabled -> activates failure injection logic
 MARTY_FAILURE_INJECTION_RATE=0.0-1.0 -> probability of injected failure
 MARTY_CIRCUIT_BREAKER_ENABLED=true|false

Client metadata key (for targeted tests):
 x-failure-inject: true (forces failure for that request if enabled)
"""

from __future__ import annotations

import logging
import os
import random
from collections import defaultdict
from collections.abc import Callable
from typing import Dict

import grpc
from grpc import aio as grpc_aio

from .circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from .error_codes import TransientBackendError, map_exception_to_status

LOGGER = logging.getLogger(__name__)


class FailureInjectionConfig:
    def __init__(self) -> None:
        self.enabled = os.environ.get("MARTY_FAILURE_INJECTION", "false").lower() in {
            "1",
            "true",
            "yes",
            "enabled",
        }
        try:
            self.rate = float(os.environ.get("MARTY_FAILURE_INJECTION_RATE", "0.0"))
        except ValueError:
            self.rate = 0.0
        self.rate = max(0.0, min(1.0, self.rate))

    def should_fail(self, force: bool = False) -> bool:
        if not self.enabled:
            return False
        if force:
            return True
        return random.random() < self.rate  # noqa: S311 (acceptable for testing)


_CIRCUIT_BREAKERS: dict[str, CircuitBreaker] = {}


def get_circuit_breaker(method_name: str) -> CircuitBreaker:
    enabled = os.environ.get("MARTY_CIRCUIT_BREAKER_ENABLED", "true").lower() in {
        "1",
        "true",
        "yes",
    }
    if not enabled:
        # return a no-op breaker
        if method_name not in _CIRCUIT_BREAKERS:
            _CIRCUIT_BREAKERS[method_name] = CircuitBreaker(
                method_name, CircuitBreakerConfig(failure_threshold=10, recovery_timeout=5)
            )
        return _CIRCUIT_BREAKERS[method_name]
    if method_name not in _CIRCUIT_BREAKERS:
        _CIRCUIT_BREAKERS[method_name] = CircuitBreaker(method_name)
    return _CIRCUIT_BREAKERS[method_name]


class ResilienceServerInterceptor(grpc_aio.ServerInterceptor):
    def __init__(self, failure_injection: FailureInjectionConfig | None = None) -> None:
        self.failure_injection = failure_injection or FailureInjectionConfig()

    async def intercept_service(self, continuation, handler_call_details):  # type: ignore[override]
        handler = await continuation(handler_call_details)
        if handler is None:
            return None
        method = handler_call_details.method
        breaker = get_circuit_breaker(method)

        # Wrap each handler type while preserving streaming semantics
        if handler.unary_unary:
            return grpc.unary_unary_rpc_method_handler(
                self._wrap_unary_unary(handler.unary_unary, breaker, method),
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )
        if handler.unary_stream:
            return grpc.unary_stream_rpc_method_handler(
                self._wrap_unary_stream(handler.unary_stream, breaker, method),
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )
        if handler.stream_unary:
            return grpc.stream_unary_rpc_method_handler(
                self._wrap_stream_unary(handler.stream_unary, breaker, method),
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )
        if handler.stream_stream:
            return grpc.stream_stream_rpc_method_handler(
                self._wrap_stream_stream(handler.stream_stream, breaker, method),
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )
        return handler

    # ----- Wrappers -----
    def _inject_failure_if_needed(self, context: grpc.ServicerContext) -> None:
        metadata = dict(context.invocation_metadata()) if context.invocation_metadata() else {}
        force = metadata.get("x-failure-inject", "false").lower() in {"1", "true", "yes"}
        if self.failure_injection.should_fail(force=force):
            raise TransientBackendError("Injected failure for resilience testing")

    def _is_retryable(self, exc: Exception) -> bool:
        # transient backend errors should be recorded as failure (retryable at client side)
        return isinstance(exc, TransientBackendError)

    def _wrap_unary_unary(self, func: Callable, breaker: CircuitBreaker, method: str):
        async def _wrapper(request, context):
            if not breaker.allow_request():
                await context.abort(grpc.StatusCode.UNAVAILABLE, f"Circuit open for {method}")
            try:
                self._inject_failure_if_needed(context)
                result = func(request, context)
                if hasattr(result, "__await__"):
                    result = await result
            except grpc.RpcError:
                raise
            except Exception as exc:  # noqa: BLE001
                status, message = map_exception_to_status(exc)
                if self._is_retryable(exc):
                    breaker.record_failure()
                else:
                    breaker.record_failure()
                await context.abort(status, message)
            else:
                breaker.record_success()
                return result

        return _wrapper

    def _wrap_unary_stream(self, func: Callable, breaker: CircuitBreaker, method: str):
        async def _wrapper(request, context):
            if not breaker.allow_request():
                await context.abort(grpc.StatusCode.UNAVAILABLE, f"Circuit open for {method}")
            try:
                self._inject_failure_if_needed(context)
                stream = func(request, context)
                if hasattr(stream, "__aiter__"):
                    async for item in stream:  # type: ignore[union-attr]
                        yield item
                else:
                    for item in stream:
                        yield item
            except grpc.RpcError:
                raise
            except Exception as exc:  # noqa: BLE001
                status, message = map_exception_to_status(exc)
                breaker.record_failure()
                await context.abort(status, message)
            else:
                breaker.record_success()

        return _wrapper

    def _wrap_stream_unary(self, func: Callable, breaker: CircuitBreaker, method: str):
        async def _wrapper(request_iterator, context):
            if not breaker.allow_request():
                await context.abort(grpc.StatusCode.UNAVAILABLE, f"Circuit open for {method}")
            try:
                self._inject_failure_if_needed(context)
                result = func(request_iterator, context)
                if hasattr(result, "__await__"):
                    result = await result
            except grpc.RpcError:
                raise
            except Exception as exc:  # noqa: BLE001
                status, message = map_exception_to_status(exc)
                breaker.record_failure()
                await context.abort(status, message)
            else:
                breaker.record_success()
                return result

        return _wrapper

    def _wrap_stream_stream(self, func: Callable, breaker: CircuitBreaker, method: str):
        async def _wrapper(request_iterator, context):
            if not breaker.allow_request():
                await context.abort(grpc.StatusCode.UNAVAILABLE, f"Circuit open for {method}")
            try:
                self._inject_failure_if_needed(context)
                stream = func(request_iterator, context)
                if hasattr(stream, "__aiter__"):
                    async for item in stream:  # type: ignore[union-attr]
                        yield item
                else:
                    for item in stream:
                        yield item
            except grpc.RpcError:
                raise
            except Exception as exc:  # noqa: BLE001
                status, message = map_exception_to_status(exc)
                breaker.record_failure()
                await context.abort(status, message)
            else:
                breaker.record_success()

        return _wrapper


__all__ = [
    "ResilienceServerInterceptor",
    "FailureInjectionConfig",
]
