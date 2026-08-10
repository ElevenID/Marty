"""Async compatibility adapters for native ISO 18013 transports."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from marty_plugin.iso18013_bridge import (
    BleTransport as _NativeBleTransport,
)
from marty_plugin.iso18013_bridge import (
    HttpsTransport as _NativeHttpsTransport,
)
from marty_plugin.iso18013_bridge import (
    NfcTransport as _NativeNfcTransport,
)
from marty_plugin.iso18013_bridge import (
    Transport as _NativeTransport,
)
from marty_plugin.native_backends import NativeOperationError


class TransportState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


class TransportError(NativeOperationError):
    """Base native transport error."""


class BLEError(TransportError):
    """Native BLE transport error."""


class NFCError(TransportError):
    """Native NFC transport error."""


class HTTPError(TransportError):
    """Native HTTPS transport error."""


@dataclass(frozen=True)
class TransportMessage:
    data: bytes
    message_type: str
    timestamp: float
    source: str
    destination: str | None = None


class TransportInterface:
    """Legacy method names delegated to one native transport instance."""

    source = "native"

    def __init__(self, transport: _NativeTransport) -> None:
        self._transport = transport
        self.state = TransportState.DISCONNECTED

    async def connect(self) -> bool:
        self.state = TransportState.CONNECTING
        try:
            await self._transport.connect()
        except Exception:
            self.state = TransportState.ERROR
            raise
        self.state = TransportState.CONNECTED
        return True

    async def disconnect(self) -> None:
        await self._transport.close()
        self.state = TransportState.DISCONNECTED

    async def send_message(self, message: bytes, message_type: str = "data") -> bool:
        del message_type
        await self._transport.send(message)
        return True

    async def receive_message(self, timeout: float = 30.0) -> TransportMessage:
        del timeout  # The native transport enforces its protocol timeout.
        data = await self._transport.receive()
        return TransportMessage(data, "data", time.time(), self.source)


class BLETransport(TransportInterface):
    source = "ble"

    def __init__(
        self,
        device_address: str | None = None,
        *,
        service_uuid: str | None = None,
    ) -> None:
        if device_address is not None:
            raise NativeOperationError(
                "Address-pinned BLE sessions are unsupported; native discovery "
                "selects an ISO 18013 service"
            )
        super().__init__(_NativeBleTransport(service_uuid))


class NFCTransport(TransportInterface):
    source = "nfc"

    def __init__(self, reader_id: str | None = None) -> None:
        if reader_id is not None:
            raise NativeOperationError(
                "Reader-pinned NFC sessions are unsupported by the native backend"
            )
        super().__init__(_NativeNfcTransport())


class HTTPSTransport(TransportInterface):
    source = "https"

    def __init__(self, base_url: str, verify_ssl: bool = True) -> None:
        if not verify_ssl:
            raise NativeOperationError(
                "TLS certificate verification cannot be disabled for native HTTPS transport"
            )
        super().__init__(_NativeHttpsTransport(base_url))


def create_transport(transport_type: str, **kwargs: Any) -> TransportInterface:
    normalized = transport_type.strip().lower()
    if normalized == "ble":
        return BLETransport(**kwargs)
    if normalized == "nfc":
        return NFCTransport(**kwargs)
    if normalized in {"http", "https"}:
        return HTTPSTransport(**kwargs)
    raise NativeOperationError(f"Unsupported native transport type: {transport_type}")


async def discover_devices(
    transport_type: str = "ble", timeout: float = 10.0
) -> list[dict[str, Any]]:
    del transport_type, timeout
    raise NativeOperationError(
        "Standalone Python transport discovery was removed; connect a native BLE transport"
    )


__all__ = [
    "BLEError",
    "BLETransport",
    "HTTPError",
    "HTTPSTransport",
    "NFCError",
    "NFCTransport",
    "TransportError",
    "TransportInterface",
    "TransportMessage",
    "TransportState",
    "create_transport",
    "discover_devices",
]
