"""Compatibility service classes, loaded only when explicitly requested."""

from importlib import import_module

_EXPORTS = {
    "BaseGrpcService": ".base_grpc_service",
    "BaseOpenXPKIService": ".base_openxpki_service",
    "BaseService": ".base_service",
}
__all__ = list(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(_EXPORTS[name], __name__), name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))
