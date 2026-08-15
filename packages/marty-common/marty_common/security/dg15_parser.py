"""Compatibility surface for native eMRTD DG15 processing.

ASN.1, DER, RSA validation, SubjectPublicKeyInfo canonicalization, and key
fingerprinting are implemented by the canonical Rust eMRTD kernel. Python
retains chip-reader orchestration and the established result model.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from marty_common.crypto_bridge import RSAPublicKeyBridge
from marty_common.emrtd_native import parse_dg15 as _native_parse_dg15
from marty_common.native_backends import NativeBackendError

logger = logging.getLogger(__name__)


@dataclass
class ChipAuthenticationInfo:
    """Chip Authentication information from DG15."""

    public_key: RSAPublicKeyBridge
    algorithm_oid: str
    key_size: int
    public_exponent: int
    modulus: int
    key_usage: str = "chip_authentication"


class DG15Parser:
    """Stable Python surface over native DG15 parsing and validation."""

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)
        self.rsa_encryption_oid = "1.2.840.113549.1.1.1"
        self.ecdsa_oids = {
            "1.2.840.10045.2.1",
            "1.2.840.10045.4.1",
            "1.2.840.10045.4.3.2",
        }

    def parse_dg15(self, dg15_data: bytes) -> ChipAuthenticationInfo:
        """Parse and validate DG15 using Rust."""

        result = _native_parse_dg15(dg15_data)
        public_key = RSAPublicKeyBridge.from_native_dg15(
            spki_der=bytes(result["spki_der"]),
            key_size=int(result["key_size"]),
            fingerprint_sha256=str(result["fingerprint_sha256"]),
            valid_for_active_authentication=bool(result["valid_for_active_authentication"]),
        )
        return ChipAuthenticationInfo(
            public_key=public_key,
            algorithm_oid=str(result["algorithm_oid"]),
            key_size=int(result["key_size"]),
            public_exponent=int(result["public_exponent"]),
            modulus=int(result["modulus"]),
            key_usage=str(result["key_usage"]),
        )

    def validate_chip_key(self, chip_info: ChipAuthenticationInfo) -> bool:
        """Return the native active-authentication suitability decision."""

        return chip_info.public_key.valid_for_active_authentication

    def extract_key_fingerprint(self, chip_info: ChipAuthenticationInfo) -> str:
        """Return the native SHA-256 SubjectPublicKeyInfo fingerprint."""

        fingerprint = chip_info.public_key.fingerprint_sha256
        if fingerprint is None:
            msg = "Native RSA key metadata does not include a fingerprint"
            raise ValueError(msg)
        return fingerprint


class DG15Manager:
    """High-level DG15 chip-reader orchestration."""

    def __init__(self) -> None:
        self.parser = DG15Parser()
        self.logger = logging.getLogger(__name__)

    def read_and_parse_dg15(self, reader) -> ChipAuthenticationInfo | None:
        """Read DG15 through an application reader and parse it natively."""

        try:
            from marty_common.rfid.apdu_commands import PassportAPDU

            passport_apdu = PassportAPDU()
            select_cmd = passport_apdu.select_elementary_file([0x75, 0x0F])
            response = reader.transmit_apdu(select_cmd.to_bytes())
            if not passport_apdu.is_success_response(response):
                self.logger.warning("Failed to select DG15")
                return None

            read_cmd = passport_apdu.read_binary(0, 255)
            dg15_data = reader.transmit_apdu(read_cmd.to_bytes())
            if not passport_apdu.is_success_response(dg15_data):
                self.logger.warning("Failed to read DG15 data")
                return None

            chip_info = self.parser.parse_dg15(dg15_data[:-2])
            if self.parser.validate_chip_key(chip_info):
                self.logger.info("Successfully extracted chip public key from DG15")
                return chip_info
            self.logger.error("Chip public key validation failed")
        except NativeBackendError:
            raise
        except Exception:
            self.logger.exception("Failed to read/parse DG15")
        return None

    def get_chip_capabilities(self, chip_info: ChipAuthenticationInfo) -> dict[str, Any]:
        """Return the established capability view for a native DG15 result."""

        if chip_info.key_size >= 2048:
            security_level = "high"
        elif chip_info.key_size >= 1024:
            security_level = "medium"
        else:
            security_level = "low"
        return {
            "active_authentication": True,
            "key_algorithm": "RSA",
            "key_size": chip_info.key_size,
            "public_exponent": chip_info.public_exponent,
            "supports_iso9796": True,
            "fingerprint": self.parser.extract_key_fingerprint(chip_info),
            "security_level": security_level,
        }


__all__ = ["ChipAuthenticationInfo", "DG15Manager", "DG15Parser"]
