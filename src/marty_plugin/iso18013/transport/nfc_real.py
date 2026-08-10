"""Retired pyscard transport names backed by the native NFC transport."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from marty_plugin.iso18013.transport import NFCTransport
from marty_plugin.native_backends import NativeOperationError


class RealNFCTransport(NFCTransport):
    """Compatibility alias for native PC/SC NFC transport."""


class NFCCardObserver:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise NativeOperationError("Python NFC card observation was removed")


class NFCCardEmulator:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise NativeOperationError(
            "Python NFC card emulation was removed; use a native holder transport"
        )


class NFCReaderManager:
    async def create_connection(
        self, reader_name: str | None = None
    ) -> RealNFCTransport:
        transport = RealNFCTransport(reader_name)
        await transport.connect()
        return transport

    async def close_connection(self, transport: RealNFCTransport) -> None:
        await transport.disconnect()

    def start_monitoring(self, _callback: Callable[..., Any]) -> None:
        raise NativeOperationError("Python NFC reader monitoring was removed")

    def stop_monitoring(self) -> None:
        raise NativeOperationError("Python NFC reader monitoring was removed")


async def discover_nfc_readers() -> list[dict[str, Any]]:
    raise NativeOperationError(
        "Standalone Python NFC reader discovery was removed; connect native NFC"
    )


async def wait_for_mdl_card(timeout: float = 30.0) -> RealNFCTransport:
    del timeout
    transport = RealNFCTransport()
    await transport.connect()
    return transport


__all__ = [
    "NFCCardEmulator",
    "NFCCardObserver",
    "NFCReaderManager",
    "RealNFCTransport",
    "discover_nfc_readers",
    "wait_for_mdl_card",
]
