"""Fail-closed loading and diagnostics for native Marty backends."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as distribution_version
from types import ModuleType
from typing import Any

from marty_common.native_backends import (
    NativeBackendError as NativeBackendError,
)
from marty_common.native_backends import (
    NativeBackendUnavailable,
    load_native_backend,
)
from marty_common.native_backends import (
    NativeOperationError as NativeOperationError,
)
from marty_common.native_policy import REQUIRED_NATIVE_BACKENDS

NATIVE_DISTRIBUTIONS = {
    "marty_iso18013": "marty-iso18013",
    "marty_verification": "marty-verification-py",
    "_marty_rs": "marty-rs",
}


def require_backend(module_name: str) -> ModuleType:
    """Load a required native module without falling back to Python code."""

    return load_native_backend(
        module_name,
        REQUIRED_NATIVE_BACKENDS.get(module_name, ()),
    )


def require_native_backends() -> dict[str, ModuleType]:
    """Load every production-required native backend or raise a typed error."""
    loaded: dict[str, ModuleType] = {}
    errors: list[str] = []
    for name in REQUIRED_NATIVE_BACKENDS:
        try:
            loaded[name] = require_backend(name)
        except NativeBackendUnavailable as exc:
            errors.append(str(exc))
    if errors:
        raise NativeBackendUnavailable("; ".join(errors))
    return loaded


def backend_diagnostics() -> dict[str, Any]:
    """Return native backend availability for health checks and diagnostics."""

    result: dict[str, Any] = {}
    for name in REQUIRED_NATIVE_BACKENDS:
        try:
            module = require_backend(name)
        except NativeBackendUnavailable as exc:
            result[name] = {"available": False, "error": str(exc)}
        else:
            result[name] = {
                "available": True,
                "version": _backend_version(name, module),
            }
    return result


def _backend_version(module_name: str, module: ModuleType) -> str:
    native_version = getattr(module, "__version__", None)
    if native_version:
        return str(native_version)
    version_function = getattr(module, "version", None)
    if callable(version_function):
        return str(version_function())
    try:
        return distribution_version(NATIVE_DISTRIBUTIONS[module_name])
    except PackageNotFoundError:
        return "unknown"
