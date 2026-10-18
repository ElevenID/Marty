"""Shared fail-closed loading primitives for Marty native extensions."""

from __future__ import annotations

from collections.abc import Iterable
from importlib import import_module
from types import ModuleType

from marty_common.native_policy import OPTIONAL_VERIFICATION_OPERATIONS, RETIRED_PRIVATE_OPERATIONS
from marty_common.native_public_exports import PUBLIC_NATIVE_EXPORTS


class NativeBackendError(RuntimeError):
    """Base error for unavailable or unusable native Marty backends."""


class NativeBackendUnavailable(NativeBackendError):  # noqa: N818
    """Raised when a required Rust extension cannot be loaded."""


class NativeOperationError(NativeBackendError):
    """Raised when a native operation cannot be completed safely."""


def _public_backend(module_name: str, native: ModuleType) -> ModuleType:
    """Expose reviewed operations without returning a legacy private-key module."""
    canonical_name = {
        "marty_verification_py": "marty_verification",
        "marty_verification_py._marty_verification": "marty_verification",
        "_marty_verification": "marty_verification",
        "marty_rs": "_marty_rs",
    }.get(module_name, module_name)
    if canonical_name not in PUBLIC_NATIVE_EXPORTS:
        return native
    allowed = set(PUBLIC_NATIVE_EXPORTS[canonical_name]) | {"__version__", "version"}
    if canonical_name == "marty_verification":
        allowed.update(OPTIONAL_VERIFICATION_OPERATIONS)
    view = ModuleType(module_name)

    def public_attribute(name: str):
        if name in RETIRED_PRIVATE_OPERATIONS:
            raise NativeOperationError(
                f"{name} is retired from Python compatibility; "
                "use the Rust managed-KMS workflow for long-term keys and signing"
            )
        if name not in allowed:
            raise AttributeError(f"{module_name} does not expose reviewed public operation {name}")
        return getattr(native, name)

    view.__getattr__ = public_attribute
    view.__dir__ = lambda: sorted(name for name in allowed if hasattr(native, name))
    return view


def load_native_backend(
    module_name: str,
    required_capabilities: Iterable[str] = (),
) -> ModuleType:
    """Load a reviewed public surface and reject legacy private-key operations."""

    try:
        module = import_module(module_name)
    except (ImportError, ModuleNotFoundError) as exc:
        raise NativeBackendUnavailable(
            f"Required native backend {module_name!r} is unavailable. "
            "Install the corresponding Rust extension before starting this service."
        ) from exc

    module = _public_backend(module_name, module)
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
