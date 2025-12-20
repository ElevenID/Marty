"""
ISO/IEC 18013-5 and 18013-7 Mobile Driving License (mDL) Implementation

This package provides a complete implementation of ISO/IEC 18013-5:2021
and ISO/IEC 18013-7:2024 for mobile driving license (mDL) operations
including offline and online flows.

The implementation supports:
- Device engagement and session establishment (ISO 18013-5 §8)
- Multiple transport protocols: BLE, NFC, HTTPS (ISO 18013-5 §8.2)
- Selective disclosure and privacy protection (ISO 18013-5 §9.3)
- Cryptographic operations and key management (ISO 18013-5 §9)
- Online verification flows (ISO 18013-7 §6)
- Reader and holder reference applications
- Comprehensive test vectors and simulators
- Full EUDI ARF compliance

Components:
- core: Core protocol implementation (DeviceEngagement, SessionManager, etc.)
- transport: Transport layer implementations (BLE, NFC, HTTPS)
- crypto: Cryptographic operations (SessionEncryption, KeyManager, etc.)
- protocols: Complete protocol flows (ISO18013_5Protocol)
- online: ISO 18013-7 online verification flows
- apps: Reference reader and holder applications
- testing: Test vectors, simulators, and CI test suites

References:
- ISO/IEC 18013-5:2021 - Personal identification — ISO-compliant driving licence — Part 5: Mobile driving licence (mDL) application
- ISO/IEC 18013-7:2024 - Personal identification — ISO-compliant driving licence — Part 7: Mobile driving licence (mDL) add-on functions
"""

# Core components
from .core import (
    DeviceEngagement,
    EngagementMethod,
    ProtocolVersion,
    SelectiveDisclosure,
    SessionManager,
    TransportMethod,
    create_device_engagement_qr,
    mDLRequest,
    mDLResponse,
)

# Cryptographic components
from .crypto import (
    DigitalSignature,
    KeyDerivation,
    KeyManager,
    MessageAuthentication,
    SelectiveDisclosureCrypto,
    SessionEncryption,
    constant_time_compare,
    generate_random_bytes,
)

# Protocols
from .protocols import (
    ISO18013_5Protocol,
    ISO18013_7Protocol,
    ProtocolState,
    SessionContext,
    create_device_engagement_qr_demo,
    simulate_offline_transaction,
)

# Transport layers
from .transport import (
    BLETransport,
    HTTPSTransport,
    NFCTransport,
    TransportInterface,
    TransportMessage,
    TransportState,
    create_transport,
    discover_devices,
)

__version__ = "1.0.0"
__all__ = [
    # Core components
    "DeviceEngagement",
    "SessionManager",
    "mDLRequest",
    "mDLResponse",
    "SelectiveDisclosure",
    "ProtocolVersion",
    "TransportMethod",
    "EngagementMethod",
    "create_device_engagement_qr",
    # Transport layers
    "BLETransport",
    "NFCTransport",
    "HTTPSTransport",
    "TransportInterface",
    "TransportMessage",
    "TransportState",
    "create_transport",
    "discover_devices",
    # Cryptographic components
    "SessionEncryption",
    "KeyDerivation",
    "MessageAuthentication",
    "DigitalSignature",
    "SelectiveDisclosureCrypto",
    "KeyManager",
    "generate_random_bytes",
    "constant_time_compare",
    # Protocols
    "ISO18013_5Protocol",
    "ISO18013_7Protocol",
    "ProtocolState",
    "SessionContext",
    "create_device_engagement_qr_demo",
    "simulate_offline_transaction",
]
