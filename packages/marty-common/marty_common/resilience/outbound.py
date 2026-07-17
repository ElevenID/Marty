"""Outbound client-side resilience helpers.

Provides a single convenience coroutine ``async_call_with_resilience`` that applies:
 - Circuit breaker gate
 - Retry policy (tenacity) for transient errors

Intended usage (example):

    from marty_common.resilience import async_call_with_resilience

    async def fetch_document(stub, request):
        return await async_call_with_resilience(
            "document_signer.GetDocument",  # circuit breaker name
            lambda: stub.GetDocument(request),  # lazy call factory
        )

The call factory must produce either an awaitable or a direct response when invoked.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from .circuit_breaker import CircuitBreaker
from .retry import retry_async

T = TypeVar("T")


_OUTBOUND_BREAKERS: dict[str, CircuitBreaker] = {}


def _get_breaker(name: str) -> CircuitBreaker:
    if name not in _OUTBOUND_BREAKERS:
        _OUTBOUND_BREAKERS[name] = CircuitBreaker(name)
    return _OUTBOUND_BREAKERS[name]


async def async_call_with_resilience(
    breaker_name: str,
    call_factory: Callable[[], Awaitable[T] | T],
    *,
    retry_kwargs: dict[str, Any] | None = None,
) -> T:
    """Execute a gRPC stub call with circuit breaker + retry.

    Parameters
    ----------
    breaker_name: Identifier for the circuit breaker bucket (e.g. ``service.Method``).
    call_factory: Zero-arg callable producing the underlying awaitable (or value).
    retry_kwargs: Optional overrides passed to ``default_retry`` (e.g. max_attempts).
    """
    breaker = _get_breaker(breaker_name)

    if not breaker.allow_request():  # fast-fail without consuming a retry attempt
        raise RuntimeError(f"Circuit '{breaker_name}' is OPEN")

    policy = retry_async(**(retry_kwargs or {}))

    @policy  # type: ignore[misc]
    async def _attempt() -> T:
        try:
            result = call_factory()
            if hasattr(result, "__await__"):
                return await result  # type: ignore[return-value]
            return result  # type: ignore[return-value]
        except Exception:  # noqa: BLE001
            breaker.record_failure()
            raise
        else:  # pragma: no cover - success path trivial
            breaker.record_success()

    return await _attempt()


__all__ = ["async_call_with_resilience"]
