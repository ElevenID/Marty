"""Compatibility names for the native ISO 18013 core types.

No protocol encoding or cryptography is implemented in this module. All
operations delegate to :mod:`marty_iso18013` through the fail-closed bridge.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from marty_plugin.iso18013_bridge import (
    DeviceEngagement,
    EngagementMethod,
    MdlRequest,
    MdlResponse,
    SelectiveDisclosure,
    Session,
    TransportMethod,
)
from marty_plugin.native_backends import NativeOperationError


class ProtocolVersion(Enum):
    """Supported compatibility-level protocol versions."""

    V1_0 = "1.0"


SessionManager = Session
mDLRequest = MdlRequest
mDLResponse = MdlResponse


def create_device_engagement_qr(
    transport_methods: list[Any] | None = None,
) -> bytes:
    """Create a QR PNG with transport metadata encoded by Rust."""
    engagement = DeviceEngagement()
    methods = transport_methods or [TransportMethod.BLE, TransportMethod.NFC]
    for method in methods:
        if method == TransportMethod.BLE:
            engagement.add_ble_transport("0000FFF0-0000-1000-8000-00805F9B34FB")
        elif method == TransportMethod.NFC:
            engagement.add_nfc_transport()
        elif method == TransportMethod.HTTPS:
            raise NativeOperationError(
                "HTTPS device engagement requires an explicit URL"
            )
        else:
            raise NativeOperationError(
                f"Unsupported device engagement transport: {method!r}"
            )
    return engagement.to_qr_code()


__all__ = [
    "DeviceEngagement",
    "EngagementMethod",
    "MdlRequest",
    "MdlResponse",
    "ProtocolVersion",
    "SelectiveDisclosure",
    "SessionManager",
    "TransportMethod",
    "create_device_engagement_qr",
    "mDLRequest",
    "mDLResponse",
]
