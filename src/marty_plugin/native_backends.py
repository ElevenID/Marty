"""Fail-closed loading and diagnostics for native Marty backends."""

from __future__ import annotations

from importlib import import_module
from types import ModuleType
from typing import Any


class NativeBackendError(RuntimeError):
    """Base error for unavailable or unusable native Marty backends."""


class NativeBackendUnavailable(NativeBackendError):
    """Raised when a required Rust extension cannot be imported."""


class NativeOperationError(NativeBackendError):
    """Raised when a native operation fails."""


def require_backend(module_name: str) -> ModuleType:
    """Load a required native module without falling back to Python code."""

    try:
        return import_module(module_name)
    except (ImportError, ModuleNotFoundError) as exc:
        raise NativeBackendUnavailable(
            f"Required native backend {module_name!r} is unavailable. "
            "Install the corresponding Rust extension before starting this service."
        ) from exc


def backend_diagnostics() -> dict[str, Any]:
    """Return native backend availability for health checks and diagnostics."""

    result: dict[str, Any] = {}
    for name in ("marty_iso18013", "marty_verification", "_marty_rs"):
        try:
            module = require_backend(name)
        except NativeBackendUnavailable as exc:
            result[name] = {"available": False, "error": str(exc)}
        else:
            result[name] = {
                "available": True,
                "version": getattr(module, "__version__", "unknown"),
            }
    return result
