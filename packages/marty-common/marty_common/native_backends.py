"""Shared fail-closed loading primitives for Marty native extensions."""

from __future__ import annotations

from collections.abc import Iterable
from importlib import import_module
from types import ModuleType


class NativeBackendError(RuntimeError):
    """Base error for unavailable or unusable native Marty backends."""


class NativeBackendUnavailable(NativeBackendError):  # noqa: N818
    """Raised when a required Rust extension cannot be loaded."""


class NativeOperationError(NativeBackendError):
    """Raised when a native operation cannot be completed safely."""


def load_native_backend(
    module_name: str,
    required_capabilities: Iterable[str] = (),
) -> ModuleType:
    """Import a Rust extension and validate its required public surface."""

    try:
        module = import_module(module_name)
    except (ImportError, ModuleNotFoundError) as exc:
        raise NativeBackendUnavailable(
            f"Required native backend {module_name!r} is unavailable. "
            "Install the corresponding Rust extension before starting this service."
        ) from exc

    missing = [name for name in required_capabilities if not hasattr(module, name)]
    if missing:
        raise NativeBackendUnavailable(
            f"Required native backend {module_name!r} is incompatible; missing: "
            f"{', '.join(missing)}. Install matching Marty native wheels."
        )
    return module


__all__ = [
    "NativeBackendError",
    "NativeBackendUnavailable",
    "NativeOperationError",
    "load_native_backend",
]
