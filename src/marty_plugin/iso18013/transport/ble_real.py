"""Retired Bleak transport names backed by the native BLE transport."""

from __future__ import annotations

from typing import Any

from marty_plugin.iso18013.transport import BLETransport
from marty_plugin.native_backends import NativeOperationError


class RealBLETransport(BLETransport):
    """Compatibility alias for native BLE central-mode transport."""


class BLEPeripheralServer:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise NativeOperationError(
            "Python BLE peripheral emulation was removed; use a native holder transport"
        )


async def discover_mdl_devices(
    timeout: float = 10.0,
) -> list[dict[str, Any]]:
    del timeout
    raise NativeOperationError(
        "Standalone Bleak discovery was removed; native BLE connect performs discovery"
    )


async def create_ble_connection(
    device_info: dict[str, Any] | None = None,
) -> RealBLETransport:
    info = device_info or {}
    unsupported = set(info) - {"service_uuid"}
    if unsupported:
        raise NativeOperationError(
            f"Native BLE connection does not accept: {', '.join(sorted(unsupported))}"
        )
    transport = RealBLETransport(service_uuid=info.get("service_uuid"))
    await transport.connect()
    return transport


__all__ = [
    "BLEPeripheralServer",
    "RealBLETransport",
    "create_ble_connection",
    "discover_mdl_devices",
]
