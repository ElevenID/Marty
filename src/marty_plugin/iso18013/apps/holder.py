"""Compatibility types for the retired Python ISO 18013 holder demo.

Protocol, key-management, and transport execution belongs to ``marty_iso18013``.
The historical demo application cannot safely emulate that native path, so its
entry point fails closed while its passive configuration/data types remain
import-compatible.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from marty_plugin.native_backends import NativeOperationError


class HolderMode(Enum):
    PASSIVE_BLE = "passive_ble"
    PASSIVE_NFC = "passive_nfc"
    ACTIVE_HTTPS = "active_https"
    QR_ENGAGEMENT = "qr_engagement"


class ConsentLevel(Enum):
    AUTOMATIC = "automatic"
    PROMPT_ONLY = "prompt_only"
    DETAILED = "detailed"
    SECURE_ENTRY = "secure_entry"


@dataclass
class mDLCredential:
    document_number: str
    issuing_country: str
    issuing_authority: str
    family_name: str
    given_name: str
    birth_date: str
    expiry_date: str
    portrait: bytes | None = None
    signature: bytes | None = None
    issuing_date: str | None = None
    driving_privileges: list[dict[str, Any]] | None = None
    administrative_number: str | None = None
    sex: str | None = None
    height: str | None = None
    weight: str | None = None
    eye_color: str | None = None
    hair_color: str | None = None
    nationality: str | None = None
    resident_address: str | None = None

    def to_cbor(self) -> dict[str, Any]:
        """Return document elements for construction by the native bindings."""
        required = {
            "family_name": self.family_name,
            "given_name": self.given_name,
            "birth_date": self.birth_date,
            "document_number": self.document_number,
            "issuing_country": self.issuing_country,
            "issuing_authority": self.issuing_authority,
            "expiry_date": self.expiry_date,
        }
        optional = (
            "issuing_date",
            "driving_privileges",
            "administrative_number",
            "sex",
            "height",
            "weight",
            "eye_color",
            "hair_color",
            "nationality",
            "resident_address",
            "portrait",
        )
        required.update(
            (name, value)
            for name in optional
            if (value := getattr(self, name)) is not None
        )
        return required


@dataclass
class HolderConfig:
    holder_id: str
    wallet_name: str = "ISO 18013 Reference Wallet"
    consent_level: ConsentLevel = ConsentLevel.DETAILED
    key_storage_path: str = "./wallet_keys"
    credential_storage_path: str = "./credentials"
    log_level: str = "INFO"
    ble_device_name: str = "mDL Wallet"
    ble_advertise_timeout: float = 60.0
    nfc_card_name: str = "mDL Card"
    pin_required: bool = True
    biometric_enabled: bool = False
    auto_consent_trusted: list[str] | None = None
    session_timeout: int = 300
    minimize_disclosure: bool = True
    audit_presentations: bool = True

    def __post_init__(self) -> None:
        if self.auto_consent_trusted is None:
            self.auto_consent_trusted = []


def _retired() -> NativeOperationError:
    return NativeOperationError(
        "The Python ISO 18013 holder demo was retired; orchestrate the native "
        "DeviceEngagement, Session, SelectiveDisclosure, and transport bindings"
    )


class ConsentManager:
    def __init__(self, _config: HolderConfig) -> None:
        raise _retired()


class ISO18013HolderApp:
    def __init__(self, _config: HolderConfig) -> None:
        raise _retired()
