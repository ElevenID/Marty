"""
SOD (Security Object of Document) Parser and Processor.

This module provides comprehensive SOD parsing, hash extraction, and validation
functionality according to ICAO Doc 9303 specifications.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, ClassVar

from marty_plugin.common.models.asn1_structures import SOD, DataGroupHash, LDSSecurityObject

logger = logging.getLogger(__name__)


class SODParsingError(Exception):
    """Raised when SOD parsing fails."""

    def __init__(self, message: str, details: str | None = None) -> None:
        if details:
            message = f"{message}: {details}"
        super().__init__(message)


class HashAlgorithmError(Exception):
    """Raised when unsupported hash algorithm is encountered."""

    def __init__(self, algorithm: str) -> None:
        super().__init__(f"Unsupported hash algorithm: {algorithm}")


class SODProcessor:
    """
    Main processor for SOD parsing and validation.

    Handles parsing, hash extraction, and validation of Security Object of Document
    according to ICAO Doc 9303 standards.
    """

    # Supported hash algorithms mapping
    SUPPORTED_HASH_ALGORITHMS: ClassVar[dict[str, Any]] = {
        "sha1": hashlib.sha1,
        "sha224": hashlib.sha224,
        "sha256": hashlib.sha256,
        "sha384": hashlib.sha384,
        "sha512": hashlib.sha512,
    }

    # Algorithm OID mappings for ICAO standards
    ALGORITHM_OID_MAP: ClassVar[dict[str, str]] = {
        "1.3.14.3.2.26": "sha1",  # SHA-1
        "2.16.840.1.101.3.4.2.1": "sha256",  # SHA-256
        "2.16.840.1.101.3.4.2.2": "sha384",  # SHA-384
        "2.16.840.1.101.3.4.2.3": "sha512",  # SHA-512
        "2.16.840.1.101.3.4.2.4": "sha224",  # SHA-224
    }

    def __init__(self) -> None:
        """Initialize the SOD processor."""
        self.logger = logger

    def parse_sod_data(self, sod_data: str | bytes) -> SOD | None:
        """
        Parse SOD data from various input formats.

        Args:
            sod_data: The SOD data to parse (hex string or bytes)

        Returns:
            Parsed SOD object or None if parsing fails

        Raises:
            SODParsingError: If SOD parsing fails
        """
        try:
            # Handle hex string input
            if isinstance(sod_data, str):
                try:
                    sod_data = bytes.fromhex(sod_data.replace(" ", "").replace("\n", ""))
                except ValueError as hex_error:
                    self.logger.exception("Invalid hex string format")
                    msg = "Invalid hex string format"
                    raise SODParsingError(msg, str(hex_error)) from hex_error

            # Handle bytes input
            if isinstance(sod_data, bytes):
                return self._parse_binary_sod(sod_data)

            # Invalid type - moved outside try block
        except (SODParsingError, HashAlgorithmError):
            raise
        except Exception as e:
            self.logger.exception("Failed to parse SOD data")
            msg = "SOD parsing failed"
            raise SODParsingError(msg, str(e)) from e

        # Invalid type
        type_name = type(sod_data).__name__
        msg = f"Unsupported SOD data type: {type_name}"
        raise SODParsingError(msg)

    def _parse_binary_sod(self, sod_data: bytes) -> SOD | None:
        """Parse binary SOD data."""
        try:
            sod = SOD.load(sod_data)
        except Exception as e:
            self.logger.exception("Failed to parse binary SOD")
            msg = "Binary SOD parsing failed"
            raise SODParsingError(msg, str(e)) from e

        # Validate basic structure after successful parsing
        if not hasattr(sod, "signed_data") or sod.signed_data is None:
            msg = "SOD does not contain signed data"
            raise SODParsingError(msg)

        return sod

    def extract_hash_algorithm(self, sod: SOD) -> str:
        """
        Extract the hash algorithm used in the SOD.

        Args:
            sod: The parsed SOD object

        Returns:
            Hash algorithm name (e.g., 'sha256')

        Raises:
            HashAlgorithmError: If algorithm is not supported
        """
        try:
            # Navigate to LDS security object
            lds_security_object = self._extract_lds_security_object(sod)

            # Get digest algorithm from LDS security object
            if hasattr(lds_security_object, "digest_algorithm"):
                digest_alg = lds_security_object.digest_algorithm
                if hasattr(digest_alg, "algorithm"):
                    algorithm_oid = str(digest_alg.algorithm)

                    if algorithm_oid in self.ALGORITHM_OID_MAP:
                        return self.ALGORITHM_OID_MAP[algorithm_oid]

                    # Create helper function to avoid raise in try
                    self._raise_algorithm_error(algorithm_oid)

            # Create helper function to avoid raise in try
            self._raise_algorithm_error("unknown")

        except HashAlgorithmError:
            raise
        except Exception as e:
            raise HashAlgorithmError(str(e)) from e

    def _raise_algorithm_error(self, algorithm: str) -> None:
        """Helper method to raise algorithm error."""
        raise HashAlgorithmError(algorithm)

    def extract_data_group_hashes(self, sod: SOD) -> dict[int, bytes]:
        """
        Extract data group hashes from the SOD.

        Args:
            sod: The parsed SOD object

        Returns:
            Dictionary mapping data group numbers to their hash values

        Raises:
            SODParsingError: If hash extraction fails
        """
        try:
            hashes = {}
            lds_security_object = self._extract_lds_security_object(sod)

            if hasattr(lds_security_object, "data_group_hash_values"):
                for dg_hash in lds_security_object.data_group_hash_values:
                    if isinstance(dg_hash, DataGroupHash):
                        data_group_number = int(dg_hash.data_group_number)
                        hash_value = bytes(dg_hash.data_group_hash_value)
                        hashes[data_group_number] = hash_value

        except Exception as e:
            msg = "Failed to extract data group hashes"
            raise SODParsingError(msg, str(e)) from e
        else:
            return hashes

    def _extract_lds_security_object(self, sod: SOD) -> LDSSecurityObject:
        """Extract LDS Security Object from SOD."""
        try:
            # Validate SOD structure using helper methods
            signed_data = self._validate_and_get_signed_data(sod)
            encap_content = self._validate_and_get_encap_content(signed_data)
            lds_content = self._validate_and_get_content(encap_content)

            # Parse the LDS Security Object
            if isinstance(lds_content, bytes):
                return LDSSecurityObject.load(lds_content)

        except SODParsingError:
            raise
        except Exception as e:
            msg = "Failed to extract LDS Security Object"
            raise SODParsingError(msg, str(e)) from e
        else:
            return lds_content

    def _validate_and_get_signed_data(self, sod: SOD) -> object:
        """Helper to validate and get signed data."""
        if not hasattr(sod, "signed_data") or not sod.signed_data:
            msg = "SOD missing signed data"
            raise SODParsingError(msg)
        return sod.signed_data

    def _validate_and_get_encap_content(self, signed_data: object) -> object:
        """Helper to validate and get encapsulated content."""
        if not hasattr(signed_data, "encap_content_info"):
            msg = "SOD missing encapsulated content info"
            raise SODParsingError(msg)
        return signed_data.encap_content_info

    def _validate_and_get_content(self, encap_content: object) -> object:
        """Helper to validate and get content."""
        if not hasattr(encap_content, "content") or not encap_content.content:
            msg = "SOD missing content"
            raise SODParsingError(msg)
        return encap_content.content

    def verify_data_group_integrity(
        self, sod: SOD, data_groups: dict[int, bytes]
    ) -> tuple[bool, list[str]]:
        """
        Verify integrity of data groups against SOD hashes.

        Args:
            sod: The parsed SOD object
            data_groups: Dictionary of data group number -> data group content

        Returns:
            Tuple of (success, list of error messages)
        """
        errors = []

        try:
            # Extract expected hashes from SOD
            expected_hashes = self.extract_data_group_hashes(sod)
            algorithm = self.extract_hash_algorithm(sod)

            if algorithm not in self.SUPPORTED_HASH_ALGORITHMS:
                errors.append(f"Unsupported hash algorithm: {algorithm}")
                return False, errors

            hash_func = self.SUPPORTED_HASH_ALGORITHMS[algorithm]

            # Verify each data group
            for dg_number, dg_data in data_groups.items():
                if dg_number not in expected_hashes:
                    errors.append(f"Data group {dg_number} not found in SOD")
                    continue

                # Compute actual hash
                actual_hash = hash_func(dg_data).digest()
                expected_hash = expected_hashes[dg_number]

                if actual_hash != expected_hash:
                    actual_hex = actual_hash.hex()
                    expected_hex = expected_hash.hex()
                    error_msg = (
                        f"Data group {dg_number} hash mismatch. "
                        f"Expected: {expected_hex}, Got: {actual_hex}"
                    )
                    errors.append(error_msg)

            # Check for missing data groups
            errors.extend(
                f"Missing data group {dg_number}"
                for dg_number in expected_hashes
                if dg_number not in data_groups
            )

            return len(errors) == 0, errors

        except (ValueError, TypeError, AttributeError, KeyError) as e:
            errors.append(f"Verification failed: {e}")
            return False, errors

    def extract_sod_info(self, sod: SOD) -> dict[str, Any]:
        """
        Extract comprehensive information from SOD.

        Args:
            sod: The parsed SOD object

        Returns:
            Dictionary with SOD information
        """
        try:
            info = {
                "version": None,
                "hash_algorithm": None,
                "data_groups": {},
                "signer_info": {},
                "certificates": [],
            }

            # Extract hash algorithm
            try:
                info["hash_algorithm"] = self.extract_hash_algorithm(sod)
            except HashAlgorithmError as e:
                info["hash_algorithm"] = f"Error: {e}"

            # Extract data group hashes
            try:
                info["data_groups"] = self.extract_data_group_hashes(sod)
            except SODParsingError as e:
                info["data_groups"] = f"Error: {e}"

            # Extract LDS version if available
            try:
                lds_object = self._extract_lds_security_object(sod)
                if hasattr(lds_object, "version"):
                    info["version"] = str(lds_object.version)
            except SODParsingError:
                pass

        except Exception as e:
            msg = "Failed to extract SOD information"
            raise SODParsingError(msg, str(e)) from e
        else:
            return info


# Convenience functions for backwards compatibility
def parse_sod(sod_data: str | bytes) -> SOD | None:
    """Parse SOD data using default processor."""
    processor = SODProcessor()
    return processor.parse_sod_data(sod_data)


def extract_sod_hashes(sod_data: str | bytes) -> dict[int, bytes] | None:
    """Extract hashes from SOD data using default processor."""
    try:
        processor = SODProcessor()
        sod = processor.parse_sod_data(sod_data)
        if sod:
            return processor.extract_data_group_hashes(sod)
    except (SODParsingError, HashAlgorithmError):
        return None
    else:
        return None


def verify_data_group_integrity_from_sod(
    sod_data: str | bytes, data_groups: dict[int, bytes]
) -> tuple[bool, list[str]]:
    """Verify data group integrity using SOD data."""
    try:
        processor = SODProcessor()
        sod = processor.parse_sod_data(sod_data)
        if sod:
            return processor.verify_data_group_integrity(sod, data_groups)
    except (SODParsingError, HashAlgorithmError) as e:
        return False, [str(e)]
    else:
        return False, ["Failed to parse SOD data"]
