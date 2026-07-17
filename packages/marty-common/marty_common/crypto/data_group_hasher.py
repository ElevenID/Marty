"""
Data Group Hash Computation Service.

This module provides comprehensive hash computation and verification
for passport data groups according to ICAO Doc 9303 standards.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from marty_common.crypto.sod_parser import SODParsingError, SODProcessor

logger = logging.getLogger(__name__)


class DataGroupHashingError(Exception):
    """Raised when data group hashing fails."""

    def __init__(self, message: str, details: str | None = None) -> None:
        if details:
            message = f"{message}: {details}"
        super().__init__(message)


class DataGroupHashComputer:
    """
    Computes and validates data group hashes for passport verification.

    This class handles the computation of data group hashes using the
    appropriate algorithm specified in the SOD, and validates them
    against the expected values from the Security Object.
    """

    def __init__(self) -> None:
        """Initialize the data group hash computer."""
        self.logger = logger
        self.sod_processor = SODProcessor()

    def compute_data_group_hash(self, data_group_content: bytes, hash_algorithm: str) -> bytes:
        """
        Compute hash for a single data group.

        Args:
            data_group_content: The raw data group content
            hash_algorithm: Hash algorithm name (e.g., 'sha256')

        Returns:
            Hash digest as bytes

        Raises:
            DataGroupHashingError: If hash computation fails
        """
        try:
            hash_func = getattr(hashlib, hash_algorithm.lower())
            return hash_func(data_group_content).digest()
        except AttributeError as e:
            msg = f"Unsupported hash algorithm: {hash_algorithm}"
            raise DataGroupHashingError(msg) from e

    def compute_all_data_group_hashes(
        self, data_groups: dict[int, bytes], hash_algorithm: str
    ) -> dict[int, bytes]:
        """
        Compute hashes for all provided data groups.

        Args:
            data_groups: Dictionary mapping data group numbers to content
            hash_algorithm: Hash algorithm to use

        Returns:
            Dictionary mapping data group numbers to hash values

        Raises:
            DataGroupHashingError: If hash computation fails
        """
        try:
            computed_hashes = {}

            for dg_number, dg_content in data_groups.items():
                computed_hash = self.compute_data_group_hash(dg_content, hash_algorithm)
                computed_hashes[dg_number] = computed_hash

                self.logger.debug(f"Computed hash for DG{dg_number}: {computed_hash.hex()}")

        except DataGroupHashingError:
            raise
        except Exception as e:
            msg = "Failed to compute data group hashes"
            raise DataGroupHashingError(msg, str(e)) from e
        else:
            return computed_hashes

    def verify_data_group_integrity_with_sod(
        self, sod_data: str | bytes, data_groups: dict[int, bytes]
    ) -> tuple[bool, list[str], dict[str, Any]]:
        """
        Verify data group integrity using SOD.

        Args:
            sod_data: The SOD data (hex string or bytes)
            data_groups: Dictionary of data group number -> content

        Returns:
            Tuple containing:
            - success: True if verification passes
            - errors: List of error messages
            - details: Dictionary with verification details

        Raises:
            DataGroupHashingError: If verification process fails
        """
        try:
            # Parse the SOD
            sod = self.sod_processor.parse_sod_data(sod_data)
        except Exception as e:
            msg = "Failed to parse SOD data or perform verification"
            raise DataGroupHashingError(msg, str(e)) from e

        if not sod:
            msg = "Failed to parse SOD data"
            raise DataGroupHashingError(msg)

        try:
            # Extract hash algorithm and expected hashes
            hash_algorithm = self.sod_processor.extract_hash_algorithm(sod)
            expected_hashes = self.sod_processor.extract_data_group_hashes(sod)

            # Compute actual hashes
            computed_hashes = self.compute_all_data_group_hashes(data_groups, hash_algorithm)

            # Verify integrity using SOD processor
            success, errors = self.sod_processor.verify_data_group_integrity(sod, data_groups)

            # Compile detailed results
            details = {
                "hash_algorithm": hash_algorithm,
                "expected_hashes": {
                    dg_num: hash_val.hex() for dg_num, hash_val in expected_hashes.items()
                },
                "computed_hashes": {
                    dg_num: hash_val.hex() for dg_num, hash_val in computed_hashes.items()
                },
                "data_groups_verified": len(computed_hashes),
                "data_groups_expected": len(expected_hashes),
            }

        except (SODParsingError, DataGroupHashingError):
            raise
        except Exception as e:
            msg = "Data group integrity verification failed"
            raise DataGroupHashingError(msg, str(e)) from e
        else:
            return success, errors, details

    def extract_data_group_content(
        self, data_group_raw: bytes | str | dict[str, Any] | object
    ) -> bytes:
        """
        Extract raw content from various data group formats.

        Args:
            data_group_raw: Raw data group data (various formats)

        Returns:
            Data group content as bytes

        Raises:
            DataGroupHashingError: If content extraction fails
        """
        try:
            result: bytes = b""

            # Handle bytes directly
            if isinstance(data_group_raw, bytes):
                result = data_group_raw

            # Handle hex strings
            elif isinstance(data_group_raw, str):
                try:
                    result = bytes.fromhex(data_group_raw.replace(" ", "").replace("\n", ""))
                except ValueError:
                    # If not hex, encode as UTF-8
                    result = data_group_raw.encode("utf-8")

            # Handle dictionary with content field
            elif isinstance(data_group_raw, dict) and "content" in data_group_raw:
                result = self.extract_data_group_content(data_group_raw["content"])

            # Handle objects with content attribute
            elif hasattr(data_group_raw, "content"):
                result = self.extract_data_group_content(data_group_raw.content)

            # Handle Pydantic models with dict conversion
            elif hasattr(data_group_raw, "model_dump"):
                # Convert to JSON bytes for consistent hashing
                json_str = json.dumps(data_group_raw.model_dump(), sort_keys=True)
                result = json_str.encode("utf-8")

            # Fallback: convert to string and encode
            else:
                result = str(data_group_raw).encode("utf-8")

        except Exception as e:
            msg = "Failed to extract data group content"
            raise DataGroupHashingError(msg, str(e)) from e
        else:
            return result

    def prepare_data_groups_for_verification(
        self, data_groups_dict: dict[str, Any]
    ) -> dict[int, bytes]:
        """
        Prepare data groups dictionary for hash verification.

        Args:
            data_groups_dict: Dictionary with string keys and various content formats

        Returns:
            Dictionary with integer keys and bytes content

        Raises:
            DataGroupHashingError: If preparation fails
        """
        try:
            prepared = {}

            for dg_key, dg_content in data_groups_dict.items():
                # Extract data group number from key (e.g., "DG1" -> 1)
                if dg_key.upper().startswith("DG"):
                    try:
                        dg_number = int(dg_key[2:])
                    except ValueError:
                        self.logger.warning(f"Invalid data group key format: {dg_key}")
                        continue
                else:
                    # Try to parse as integer
                    try:
                        dg_number = int(dg_key)
                    except ValueError:
                        self.logger.warning(f"Cannot parse data group number: {dg_key}")
                        continue

                # Extract content as bytes
                content_bytes = self.extract_data_group_content(dg_content)
                prepared[dg_number] = content_bytes

                self.logger.debug(f"Prepared DG{dg_number}: {len(content_bytes)} bytes")

        except Exception as e:
            msg = "Failed to prepare data groups for verification"
            raise DataGroupHashingError(msg, str(e)) from e
        else:
            return prepared


# Convenience functions for integration
def verify_passport_data_groups(
    sod_data: str | bytes, data_groups: dict[str, Any]
) -> tuple[bool, list[str], dict[str, Any]]:
    """
    Verify passport data groups using SOD.

    Convenience function for passport verification integration.
    """
    try:
        computer = DataGroupHashComputer()
        prepared_dgs = computer.prepare_data_groups_for_verification(data_groups)
        return computer.verify_data_group_integrity_with_sod(sod_data, prepared_dgs)
    except DataGroupHashingError as e:
        return False, [str(e)], {}


def compute_data_group_hash_simple(content: bytes, algorithm: str = "sha256") -> str:
    """
    Simple hash computation for individual data groups.

    Returns hex-encoded hash string.
    """
    try:
        computer = DataGroupHashComputer()
        hash_bytes = computer.compute_data_group_hash(content, algorithm)
        return hash_bytes.hex()
    except DataGroupHashingError:
        return ""
