"""RFID Communication Module.

Provides RFID/NFC communication capabilities for passport and document reading.
Supports ISO 14443 Type A/B, ISO 15693, and ICAO Doc 9303 protocols.
"""

from __future__ import annotations

__all__ = [
    "APDUCommand",
    "APDUResponse",
    "BACKeys",
    "BiometricInfo",
    "BiometricTemplateProcessor",
    "BiometricType",
    "DataGroup",
    "EFData",
    "ElementaryFileParser",
    "FacialImageTemplate",
    "FingerprintTemplate",
    "IrisTemplate",
    "MRZInfo",
    "MockNFCInterface",
    "NFCDevice",
    "NFCInterface",
    "NFCProtocol",
    "NFCProtocolHandler",
    "PassportAPDU",
    "SecureMessaging",
    "SessionKeys",
]

# Core APDU command processing
from .apdu_commands import APDUCommand, APDUResponse, PassportAPDU

# Biometric template processing
from .biometric_templates import (
    BiometricTemplateProcessor,
    BiometricType,
    FacialImageTemplate,
    FingerprintTemplate,
    IrisTemplate,
)

# Elementary file parsing for passport data
from .elementary_files import BiometricInfo, DataGroup, EFData, ElementaryFileParser, MRZInfo

# NFC protocol handling for mobile integration
from .nfc_protocols import (
    MockNFCInterface,
    NFCDevice,
    NFCInterface,
    NFCProtocol,
    NFCProtocolHandler,
)

# Secure messaging for BAC/EAC protocols
from .secure_messaging import BACKeys, SecureMessaging, SessionKeys
