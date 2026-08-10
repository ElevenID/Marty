"""Fail-closed Python adapter for the native ISO 18013-5 implementation."""

from __future__ import annotations

from typing import Any, Optional

from marty_plugin.native_backends import (
    NativeBackendError,
    NativeBackendUnavailable,
    NativeOperationError,
    require_backend,
)

_native = require_backend("marty_iso18013")
RUST_AVAILABLE = True
TransportMethod = _native.TransportMethod
EngagementMethod = _native.EngagementMethod
SessionState = _native.SessionState
ResponseStatus = _native.ResponseStatus


def _call(operation: Any, *args: Any) -> Any:
    """Invoke a native operation and normalize extension failures."""
    try:
        return operation(*args)
    except NativeBackendError:
        raise
    except Exception as exc:
        raise NativeOperationError(f"Native ISO 18013 operation failed: {exc}") from exc


class DeviceEngagement:
    """Python compatibility wrapper around the Rust device engagement."""

    def __init__(self) -> None:
        self._inner = _call(_native.DeviceEngagement.new)

    @classmethod
    def from_bytes(cls, data: bytes) -> "DeviceEngagement":
        instance = cls.__new__(cls)
        instance._inner = _call(_native.DeviceEngagement.from_bytes, data)
        return instance

    from_cbor = from_bytes

    def add_ble_transport(self, service_uuid: str) -> None:
        _call(self._inner.add_ble, service_uuid)

    def add_nfc_transport(self) -> None:
        _call(self._inner.add_nfc)

    def add_https_transport(self, url: str) -> None:
        _call(self._inner.add_https, url)

    def to_bytes(self) -> bytes:
        return bytes(_call(self._inner.to_bytes))

    to_cbor = to_bytes

    def to_qr_code(self) -> bytes:
        return bytes(_call(self._inner.to_qr_code))

    generate_qr_code = to_qr_code


class MdlRequest:
    """Native mDL request wrapper with Rust-generated nonces by default."""

    def __init__(
        self,
        doc_type: str = "org.iso.18013.5.1.mDL",
        data_elements: Optional[dict[str, list[str]]] = None,
        nonce: Optional[bytes] = None,
    ) -> None:
        elements = data_elements or {}
        self._inner = _call(_native.MdlRequest, doc_type, elements, nonce)

    @classmethod
    def from_bytes(cls, data: bytes) -> "MdlRequest":
        instance = cls.__new__(cls)
        instance._inner = _call(_native.MdlRequest.from_bytes, data)
        return instance

    from_cbor = from_bytes

    def to_bytes(self) -> bytes:
        return bytes(_call(self._inner.to_bytes))

    to_cbor = to_bytes

    @property
    def doc_type(self) -> str:
        return str(self._inner.doc_type)

    @property
    def data_elements(self) -> dict[str, list[str]]:
        return dict(self._inner.data_elements)

    @property
    def nonce(self) -> bytes:
        return bytes(self._inner.nonce)


class MdlResponse:
    """Native mDL response wrapper."""

    def __init__(
        self,
        doc_type: str,
        data: bytes,
        status: Any = None,
    ) -> None:
        self._inner = _call(_native.MdlResponse, doc_type, data, status)

    @classmethod
    def from_bytes(cls, data: bytes) -> "MdlResponse":
        instance = cls.__new__(cls)
        instance._inner = _call(_native.MdlResponse.from_bytes, data)
        return instance

    from_cbor = from_bytes

    def to_bytes(self) -> bytes:
        return bytes(_call(self._inner.to_bytes))

    to_cbor = to_bytes

    @property
    def doc_type(self) -> str:
        return str(self._inner.doc_type)

    @property
    def data(self) -> bytes:
        return bytes(self._inner.data)

    @property
    def status(self) -> Any:
        return self._inner.status


class SelectiveDisclosure:
    """Native selective-disclosure policy wrapper."""

    def __init__(self) -> None:
        self._inner = _call(_native.SelectiveDisclosure)

    def add_namespace(self, namespace: str, elements: list[str]) -> None:
        _call(self._inner.add_namespace, namespace, elements)

    def add_mandatory(self, element: str) -> None:
        _call(self._inner.add_mandatory, element)

    def filter_request(
        self,
        requested: dict[str, list[str]],
        user_approved: dict[str, list[str]],
    ) -> dict[str, list[str]]:
        return dict(_call(self._inner.filter_request, requested, user_approved))


class SessionConfig:
    """Configuration passed directly to the Rust session."""

    def __init__(
        self,
        timeout_secs: int = 300,
        max_message_size: int = 1024 * 1024,
        verbose: bool = False,
    ) -> None:
        self._inner = _call(
            _native.SessionConfig, timeout_secs, max_message_size, verbose
        )

    @property
    def _native_config(self) -> Any:
        return self._inner

    @property
    def timeout_secs(self) -> int:
        return self._inner.timeout_secs

    @timeout_secs.setter
    def timeout_secs(self, value: int) -> None:
        self._inner.timeout_secs = value

    @property
    def max_message_size(self) -> int:
        return self._inner.max_message_size

    @max_message_size.setter
    def max_message_size(self, value: int) -> None:
        self._inner.max_message_size = value


class Session:
    """Async-compatible adapter around the synchronous PyO3 Rust methods."""

    def __init__(
        self, engagement: DeviceEngagement, config: Optional[SessionConfig] = None
    ) -> None:
        native_config = config._native_config if config else None
        self._inner = _call(
            _native.Session.from_engagement_py, engagement._inner, native_config
        )

    async def public_key(self) -> bytes:
        return bytes(_call(self._inner.public_key_py))

    async def establish(self, peer_public_key: bytes) -> None:
        _call(self._inner.establish_py, peer_public_key)

    async def send_encrypted(self, message: bytes) -> bytes:
        return bytes(_call(self._inner.send_encrypted_py, message))

    async def receive_encrypted(self, ciphertext: bytes) -> bytes:
        return bytes(_call(self._inner.receive_encrypted_py, ciphertext))

    async def state(self) -> Any:
        return _call(self._inner.state_py)

    async def terminate(self) -> None:
        _call(self._inner.terminate_py)


class Transport:
    """Async-compatible adapter over a synchronous native transport."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    async def connect(self) -> None:
        _call(self._inner.connect)

    async def send(self, data: bytes) -> None:
        _call(self._inner.send, data)

    async def receive(self) -> bytes:
        return bytes(_call(self._inner.receive))

    async def close(self) -> None:
        _call(self._inner.close)

    def is_connected(self) -> bool:
        return bool(self._inner.is_connected())


class BleTransport(Transport):
    """Native BLE transport adapter."""

    def __init__(self, service_uuid: Optional[str] = None) -> None:
        native_type = getattr(_native, "BleTransport", None)
        if native_type is None:
            raise NativeBackendUnavailable(
                "The installed marty_iso18013 module was built without BLE transport support"
            )
        super().__init__(native_type(service_uuid))


class NfcTransport(Transport):
    """Native NFC transport adapter."""

    def __init__(self) -> None:
        native_type = getattr(_native, "NfcTransport", None)
        if native_type is None:
            raise NativeBackendUnavailable(
                "The installed marty_iso18013 module was built without NFC transport support"
            )
        super().__init__(native_type())


class HttpsTransport(Transport):
    """Native HTTPS transport adapter."""

    def __init__(self, url: str) -> None:
        native_type = getattr(_native, "HttpsTransport", None)
        if native_type is None:
            raise NativeBackendUnavailable(
                "The installed marty_iso18013 module was built without HTTPS transport support"
            )
        super().__init__(native_type(url))


def transport_capabilities() -> dict[str, bool]:
    """Report which native transport classes are present in the installed wheel."""
    return {
        "ble": hasattr(_native, "BleTransport"),
        "nfc": hasattr(_native, "NfcTransport"),
        "https": hasattr(_native, "HttpsTransport"),
    }


def get_implementation() -> str:
    return "rust"


def get_version() -> str:
    return getattr(_native, "__version__", "unknown")


__all__ = [
    "BleTransport",
    "DeviceEngagement",
    "EngagementMethod",
    "HttpsTransport",
    "MdlRequest",
    "MdlResponse",
    "NativeBackendUnavailable",
    "NativeOperationError",
    "NfcTransport",
    "ResponseStatus",
    "RUST_AVAILABLE",
    "Session",
    "SessionConfig",
    "SessionState",
    "SelectiveDisclosure",
    "Transport",
    "TransportMethod",
    "get_implementation",
    "get_version",
    "transport_capabilities",
]
