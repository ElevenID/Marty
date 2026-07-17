"""DG15 Public Key Extraction for Active Authentication.

Parses Data Group 15 (DG15) from ePassport chips to extract the
chip authentication public key used for Active Authentication.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

# Use Rust crypto_bridge for key operations
from marty_common.crypto_bridge import RSAPublicKeyBridge, Encoding, PublicFormat
from pyasn1.codec.der import decoder as der_decoder
from pyasn1.type import namedtype, univ

logger = logging.getLogger(__name__)


class RSAPublicKey(univ.Sequence):
    """ASN.1 structure for RSA public key."""

    componentType = namedtype.NamedTypes(
        namedtype.NamedType("modulus", univ.Integer()),
        namedtype.NamedType("publicExponent", univ.Integer()),
    )


class AlgorithmIdentifier(univ.Sequence):
    """ASN.1 structure for algorithm identifier."""

    componentType = namedtype.NamedTypes(
        namedtype.NamedType("algorithm", univ.ObjectIdentifier()),
        namedtype.OptionalNamedType("parameters", univ.Any()),
    )


class SubjectPublicKeyInfo(univ.Sequence):
    """ASN.1 structure for subject public key info."""

    componentType = namedtype.NamedTypes(
        namedtype.NamedType("algorithm", AlgorithmIdentifier()),
        namedtype.NamedType("subjectPublicKey", univ.BitString()),
    )


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
    """Parser for Data Group 15 (DG15) containing chip authentication public key."""

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)
        # RSA encryption OID
        self.rsa_encryption_oid = "1.2.840.113549.1.1.1"
        # ECDSA OIDs (for future support)
        self.ecdsa_oids = {
            "1.2.840.10045.2.1",  # ecPublicKey
            "1.2.840.10045.4.1",  # ecdsa-with-SHA1
            "1.2.840.10045.4.3.2",  # ecdsa-with-SHA256
        }

    def parse_dg15(self, dg15_data: bytes) -> ChipAuthenticationInfo:
        """Parse DG15 data to extract chip authentication public key.

        Args:
            dg15_data: Raw DG15 data from passport chip

        Returns:
            ChipAuthenticationInfo containing the public key and metadata

        Raises:
            ValueError: If DG15 data is invalid or unsupported
        """
        if not dg15_data:
            msg = "DG15 data is empty"
            raise ValueError(msg)

        try:
            # Parse the TLV structure to extract the public key info
            public_key_info = self._extract_subject_public_key_info(dg15_data)

            # Parse the SubjectPublicKeyInfo structure
            spki, _ = der_decoder.decode(public_key_info, asn1Spec=SubjectPublicKeyInfo())

            # Extract algorithm information
            algorithm = spki.getComponentByName("algorithm")
            algorithm_oid = str(algorithm.getComponentByName("algorithm"))

            # Extract public key bits
            public_key_bits = spki.getComponentByName("subjectPublicKey")
            public_key_bytes = self._bitstring_to_bytes(public_key_bits)

            # Parse based on algorithm
            if algorithm_oid == self.rsa_encryption_oid:
                return self._parse_rsa_public_key(public_key_bytes, algorithm_oid)
            if algorithm_oid in self.ecdsa_oids:
                msg = "ECDSA keys not yet supported in DG15 parsing"
                raise ValueError(msg)
            msg = f"Unsupported public key algorithm: {algorithm_oid}"
            raise ValueError(msg)

        except Exception as e:
            self.logger.exception("Failed to parse DG15 data")
            msg = f"DG15 parsing error: {e!s}"
            raise ValueError(msg) from e

    def _extract_subject_public_key_info(self, dg15_data: bytes) -> bytes:
        """Extract SubjectPublicKeyInfo from DG15 TLV structure.

        DG15 structure (simplified):
        - Tag: 0x6F (File Control Information)
        - Length: Variable
        - Value: SubjectPublicKeyInfo DER encoding
        """
        offset = 0

        # Check for DG15 tag (0x6F)
        if len(dg15_data) < 2:
            msg = "DG15 data too short"
            raise ValueError(msg)

        tag_byte = dg15_data[offset]
        if tag_byte != 0x6F:
            msg = f"Invalid DG15 tag: 0x{tag_byte:02X}, expected 0x6F"
            raise ValueError(msg)

        offset += 1

        # Parse length
        length, length_bytes = self._parse_der_length(dg15_data[offset:])
        offset += length_bytes

        # Extract the value (SubjectPublicKeyInfo)
        if offset + length > len(dg15_data):
            msg = "DG15 data truncated"
            raise ValueError(msg)

        return dg15_data[offset : offset + length]

    def _parse_der_length(self, data: bytes) -> tuple[int, int]:
        """Parse DER length encoding.

        Returns:
            Tuple of (length_value, bytes_consumed)
        """
        if len(data) == 0:
            msg = "No length data available"
            raise ValueError(msg)

        first_byte = data[0]

        # Short form (length < 128)
        if first_byte & 0x80 == 0:
            return first_byte, 1

        # Long form
        length_bytes = first_byte & 0x7F
        if length_bytes == 0:
            msg = "Indefinite length not allowed in DER"
            raise ValueError(msg)

        if len(data) < 1 + length_bytes:
            msg = "Insufficient data for long form length"
            raise ValueError(msg)

        length_value = 0
        for i in range(1, 1 + length_bytes):
            length_value = (length_value << 8) | data[i]

        return length_value, 1 + length_bytes

    def _bitstring_to_bytes(self, bit_string: univ.BitString) -> bytes:
        """Convert ASN.1 BitString to bytes."""
        # Prefer direct octet extraction when available
        if hasattr(bit_string, "asOctets"):
            return bit_string.asOctets()

        bit_string_bytes = bytes(bit_string)

        # BitString format: first byte is number of unused bits
        if len(bit_string_bytes) == 0:
            return b""

        unused_bits = bit_string_bytes[0]
        if unused_bits > 7:
            msg = f"Invalid unused bits count: {unused_bits}"
            raise ValueError(msg)

        # Return the actual key data (skip the unused bits byte)
        return bit_string_bytes[1:]

    def _parse_rsa_public_key(self, key_bytes: bytes, algorithm_oid: str) -> ChipAuthenticationInfo:
        """Parse RSA public key from DER encoded bytes."""
        try:
            # Parse RSA public key structure
            rsa_key, _ = der_decoder.decode(key_bytes, asn1Spec=RSAPublicKey())

            # Extract modulus and public exponent
            modulus = int(rsa_key.getComponentByName("modulus"))
            public_exponent = int(rsa_key.getComponentByName("publicExponent"))

            # Create crypto_bridge RSA public key
            public_key = RSAPublicKeyBridge(modulus, public_exponent)

            key_size = public_key.key_size

            self.logger.info("Parsed RSA public key from DG15: %d bits", key_size)

            return ChipAuthenticationInfo(
                public_key=public_key,
                algorithm_oid=algorithm_oid,
                key_size=key_size,
                public_exponent=public_exponent,
                modulus=modulus,
            )

        except Exception as e:
            msg = f"Failed to parse RSA public key: {e!s}"
            raise ValueError(msg) from e

    def validate_chip_key(self, chip_info: ChipAuthenticationInfo) -> bool:
        """Validate chip authentication public key.

        Args:
            chip_info: Chip authentication information

        Returns:
            True if key is valid for Active Authentication
        """
        try:
            # Check key size (typical range for passport chips)
            if chip_info.key_size < 1024:
                self.logger.warning("RSA key too small: %d bits", chip_info.key_size)
                return False

            if chip_info.key_size > 4096:
                self.logger.warning("RSA key unusually large: %d bits", chip_info.key_size)

            # Check public exponent (common values: 65537, 3)
            if chip_info.public_exponent not in (3, 65537):
                self.logger.warning("Unusual public exponent: %d", chip_info.public_exponent)

            # Verify key can be used for verification
            try:
                # Test key serialization
                pem_data = chip_info.public_key.public_bytes(
                    encoding=Encoding.PEM,
                    format=PublicFormat.SubjectPublicKeyInfo,
                )
                if not pem_data:
                    return False

                self.logger.debug("Chip public key validation successful")

            except Exception as e:
                self.logger.exception("Key validation failed: %s", str(e))
                return False
            else:
                return True

        except Exception:
            self.logger.exception("Key validation error")
            return False

    def extract_key_fingerprint(self, chip_info: ChipAuthenticationInfo) -> str:
        """Extract key fingerprint for identification.

        Args:
            chip_info: Chip authentication information

        Returns:
            Hex-encoded SHA-256 fingerprint of the public key
        """
        import hashlib

        try:
            # Serialize public key in DER format
            der_bytes = chip_info.public_key.public_bytes(
                encoding=Encoding.DER,
                format=PublicFormat.SubjectPublicKeyInfo,
            )

            # Compute SHA-256 fingerprint
            fingerprint = hashlib.sha256(der_bytes).hexdigest()

            self.logger.debug("Generated key fingerprint: %s", fingerprint[:16] + "...")

        except Exception:
            self.logger.exception("Failed to generate key fingerprint")
            return ""
        else:
            return fingerprint


class DG15Manager:
    """High-level manager for DG15 operations."""

    def __init__(self) -> None:
        self.parser = DG15Parser()
        self.logger = logging.getLogger(__name__)

    def read_and_parse_dg15(self, reader) -> ChipAuthenticationInfo | None:
        """Read DG15 from chip and parse the public key.

        Args:
            reader: RFID reader interface

        Returns:
            ChipAuthenticationInfo if successful, None otherwise
        """
        try:
            from marty_common.rfid.apdu_commands import PassportAPDU

            # Create APDU handler
            passport_apdu = PassportAPDU()

            # Select DG15 file
            select_cmd = passport_apdu.select_elementary_file([0x75, 0x0F])  # DG15
            response = reader.transmit_apdu(select_cmd.to_bytes())

            if not passport_apdu.is_success_response(response):
                self.logger.warning("Failed to select DG15")
                return None

            # Read DG15 data
            read_cmd = passport_apdu.read_binary(0, 255)  # Read up to 255 bytes
            dg15_data = reader.transmit_apdu(read_cmd.to_bytes())

            if not passport_apdu.is_success_response(dg15_data):
                self.logger.warning("Failed to read DG15 data")
                return None

            # Remove status word
            dg15_content = dg15_data[:-2]

            # Parse DG15
            chip_info = self.parser.parse_dg15(dg15_content)

            # Validate the key
            if self.parser.validate_chip_key(chip_info):
                self.logger.info("Successfully extracted chip public key from DG15")
                return chip_info
            self.logger.error("Chip public key validation failed")

        except Exception as e:
            self.logger.exception("Failed to read/parse DG15: %s", str(e))
            return None
        else:
            return None

    def get_chip_capabilities(self, chip_info: ChipAuthenticationInfo) -> dict[str, Any]:
        """Get chip capabilities based on public key information.

        Args:
            chip_info: Chip authentication information

        Returns:
            Dictionary containing chip capabilities
        """
        capabilities = {
            "active_authentication": True,
            "key_algorithm": "RSA",
            "key_size": chip_info.key_size,
            "public_exponent": chip_info.public_exponent,
            "supports_iso9796": True,  # Most passport chips support this
            "fingerprint": self.parser.extract_key_fingerprint(chip_info),
        }

        # Determine security level based on key size
        if chip_info.key_size >= 2048:
            capabilities["security_level"] = "high"
        elif chip_info.key_size >= 1024:
            capabilities["security_level"] = "medium"
        else:
            capabilities["security_level"] = "low"

        return capabilities
