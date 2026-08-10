"""Compatibility boundary for the Rust ISO 18013 state machine."""

from __future__ import annotations

from typing import Any

from marty_plugin.iso18013.core import create_device_engagement_qr
from marty_plugin.iso18013_bridge import Session, SessionConfig, SessionState
from marty_plugin.native_backends import NativeOperationError

ProtocolState = SessionState
SessionContext = Session


class ProtocolError(NativeOperationError):
    """Base native protocol error."""


class SessionEstablishmentError(ProtocolError):
    """Native session establishment failed."""


class MessageProtocolError(ProtocolError):
    """Native secure-message processing failed."""


class _UseNativeSession:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise NativeOperationError(
            "The Python ISO 18013 state machine was removed; construct "
            "marty_plugin.iso18013_bridge.Session with a DeviceEngagement"
        )


ISO18013_5Protocol = _UseNativeSession
ISO18013_7Protocol = _UseNativeSession


def create_device_engagement_qr_demo() -> bytes:
    """Create the native BLE/NFC demonstration engagement QR image."""
    return create_device_engagement_qr()


async def simulate_offline_transaction() -> dict[str, Any]:
    raise NativeOperationError(
        "The simulated Python protocol was removed; use two native Session instances"
    )


__all__ = [
    "ISO18013_5Protocol",
    "ISO18013_7Protocol",
    "MessageProtocolError",
    "ProtocolError",
    "ProtocolState",
    "SessionConfig",
    "SessionContext",
    "SessionEstablishmentError",
    "create_device_engagement_qr_demo",
    "simulate_offline_transaction",
]
