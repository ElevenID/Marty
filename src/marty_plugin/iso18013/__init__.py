"""Fail-closed compatibility package for the native ISO 18013 backend."""

from marty_plugin.iso18013_bridge import (
    BleTransport,
    DeviceEngagement,
    EngagementMethod,
    HttpsTransport,
    MdlRequest,
    MdlResponse,
    NfcTransport,
    ResponseStatus,
    SelectiveDisclosure,
    Session,
    SessionConfig,
    SessionState,
    TransportMethod,
    get_implementation,
    get_version,
    transport_capabilities,
)

BLETransport = BleTransport
NFCTransport = NfcTransport
HTTPSTransport = HttpsTransport
SessionManager = Session
ProtocolState = SessionState
mDLRequest = MdlRequest
mDLResponse = MdlResponse

__version__ = get_version()

__all__ = [
    "BLETransport",
    "DeviceEngagement",
    "EngagementMethod",
    "HTTPSTransport",
    "MdlRequest",
    "MdlResponse",
    "NFCTransport",
    "ProtocolState",
    "ResponseStatus",
    "SelectiveDisclosure",
    "Session",
    "SessionConfig",
    "SessionManager",
    "SessionState",
    "TransportMethod",
    "get_implementation",
    "get_version",
    "mDLRequest",
    "mDLResponse",
    "transport_capabilities",
]
