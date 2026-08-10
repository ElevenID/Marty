"""Compatibility types for the retired Python ISO 18013 reader demo.

All reader protocol and cryptographic processing must use ``marty_iso18013``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from marty_plugin.native_backends import NativeOperationError


class ReaderMode(Enum):
    OFFLINE_BLE = "offline_ble"
    OFFLINE_NFC = "offline_nfc"
    ONLINE_HTTPS = "online_https"
    MULTI_TRANSPORT = "multi_transport"


class VerificationLevel(Enum):
    BASIC = "basic"
    STANDARD = "standard"
    ENHANCED = "enhanced"


@dataclass
class ReaderConfig:
    reader_id: str
    organization: str
    supported_transports: list[str]
    verification_level: VerificationLevel = VerificationLevel.STANDARD
    key_storage_path: str = "./keys"
    log_level: str = "INFO"
    session_timeout: int = 300
    ble_scan_timeout: float = 10.0
    nfc_reader_name: str | None = None
    https_base_url: str | None = None
    trusted_issuers: list[str] | None = None
    revocation_check: bool = True
    policy_url: str | None = None

    def __post_init__(self) -> None:
        if self.trusted_issuers is None:
            self.trusted_issuers = []


class ISO18013ReaderApp:
    def __init__(self, _config: ReaderConfig) -> None:
        raise NativeOperationError(
            "The Python ISO 18013 reader demo was retired; orchestrate the native "
            "DeviceEngagement, Session, SelectiveDisclosure, and transport bindings"
        )
