"""
Passport test data generator for Marty project.

Based on the concepts from the pypassport library, this module generates
realistic passport data for testing purposes, including properly structured
data groups and the necessary cryptographic signatures.

Uses Rust bindings from marty_rs for MRZ check digit calculation.

LICENSING NOTE:
--------------
This implementation is inspired by concepts from the pypassport project
(https://github.com/roeften/pypassport), which is licensed under LGPL-3.0.
To ensure licensing compliance:

1. This is a clean-room implementation without direct code copying
2. Any references to the original pypassport project are only for validation
   purposes and will be removed after validation is complete
3. The functionality has been adapted specifically for the Marty project's needs

References to pypassport are marked with PYPASSPORT_REFERENCE and will be
removed in a future update once validation is complete.
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path
from typing import Any

# Add project root to path
project_root = Path(__file__).resolve().parents[2]
sys.path.append(str(project_root))


# Import from Marty's codebase
from marty_backend_common.models.passport import DataGroupType
from src.marty_plugin.common.crypto_bridge import compute_check_digit as _rust_compute_check_digit


class PassportGenerator:
    """
    Generates test passport data for use in testing.

    This class creates realistic passport data including properly structured
    data groups and the necessary cryptographic signatures.
    """

    def __init__(self, output_dir: str | None = None):
        """
        Initialize the passport generator.

        Args:
            output_dir: Directory to save generated passport data.
                        If None, data will be returned but not saved.
        """
        self.output_dir = output_dir
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)

    def generate_mrz(
        self,
        document_type: str = "P",
        issuing_country: str = "USA",
        name: str = "SMITH",
        surname: str = "JOHN",
        nationality: str = "USA",
        sex: str = "M",
        passport_num: str = "123456789",
        birth_date: str = "850531",  # YYMMDD
        expiry_date: str = "250531",  # YYMMDD
        optional_data: str = "",
    ) -> str:
        """
        Generate a valid MRZ (Machine Readable Zone) string.

        Args:
            document_type: Type of document (P for passport)
            issuing_country: 3-letter country code
            name: Surname
            surname: Given names
            nationality: 3-letter country code
            sex: M or F
            passport_num: Passport number
            birth_date: Date of birth (YYMMDD)
            expiry_date: Expiry date (YYMMDD)
            optional_data: Optional data

        Returns:
            A valid MRZ string
        """
        # Ensure document type is valid
        if document_type not in ["P", "I", "A", "C"]:
            document_type = "P"  # Default to passport

        # Format name and surname fields to fit within character limits
        name = name[:39]
        surname = surname[:39]

        # Ensure country codes are valid
        issuing_country = issuing_country[:3].upper()
        nationality = nationality[:3].upper()

        # Ensure sex is valid
        if sex not in ["M", "F"]:
            sex = "M"  # Default to male

        # Format passport number
        passport_num = passport_num[:9].ljust(9, "<")

        # Calculate check digits
        check_digit_passport = self._calculate_check_digit(passport_num)
        check_digit_birth = self._calculate_check_digit(birth_date)
        check_digit_expiry = self._calculate_check_digit(expiry_date)

        # Format optional data
        optional_data = "<<<<<<<<<<<<<<" if not optional_data else optional_data[:14].ljust(14, "<")
        check_digit_optional = self._calculate_check_digit(optional_data)

        # First line of MRZ
        line1 = f"{document_type}<{issuing_country}{name}<<{surname}"
        line1 = line1.ljust(44, "<")

        # Second line of MRZ
        # ICAO 9303 Part 3 §4.9: composite check digit covers doc_num+check,
        # dob+check, expiry+check, optional+check. Nationality and sex are excluded.
        composite_check = f"{passport_num}{check_digit_passport}{birth_date}{check_digit_birth}{expiry_date}{check_digit_expiry}{optional_data}{check_digit_optional}"
        check_digit_all = self._calculate_check_digit(composite_check)

        line2 = f"{passport_num}{check_digit_passport}{nationality}{birth_date}{check_digit_birth}{sex}{expiry_date}{check_digit_expiry}{optional_data}{check_digit_optional}{check_digit_all}"

        return line1 + line2

    def _calculate_check_digit(self, data: str) -> str:
        """
        Calculate the check digit for MRZ data.

        Uses Rust implementation via marty_rs for correctness and performance.

        Args:
            data: The data to calculate the check digit for

        Returns:
            The check digit (0-9)
        """
        return _rust_compute_check_digit(data)

    def create_data_group_1(self, mrz_data: str) -> dict[str, Any]:
        """
        Create a DG1 data group containing the MRZ data.

        Args:
            mrz_data: The MRZ data string

        Returns:
            A dictionary representing DG1 data
        """
        return {
            "type": DataGroupType.DG1,
            "tag": "61",  # DG1 tag
            "data": mrz_data,
            "raw_bytes": self._format_dg1_bytes(mrz_data),
        }

    def _format_dg1_bytes(self, mrz_data: str) -> bytes:
        """
        Format MRZ data as DG1 bytes.

        Args:
            mrz_data: The MRZ data string

        Returns:
            DG1 bytes
        """
        mrz_bytes = mrz_data.encode("ascii")

        # DG1 structure: tag (61) + length + content tag (5F1F) + content length + mrz data
        tag = bytes.fromhex("61")
        content_tag = bytes.fromhex("5F1F")

        # Calculate lengths
        content_length = len(mrz_bytes)
        content_length_bytes = self._encode_length(content_length)
        total_length = len(content_tag) + len(content_length_bytes) + content_length
        total_length_bytes = self._encode_length(total_length)

        # Combine all parts
        return tag + total_length_bytes + content_tag + content_length_bytes + mrz_bytes

    def _encode_length(self, length: int) -> bytes:
        """
        Encode a length value in ASN.1 format.

        Args:
            length: The length to encode

        Returns:
            ASN.1 encoded length bytes
        """
        if length < 128:
            return bytes([length])

        # For longer lengths
        length_bytes = []
        temp = length
        while temp > 0:
            length_bytes.insert(0, temp & 0xFF)
            temp >>= 8

        length_bytes.insert(0, 0x80 | len(length_bytes))
        return bytes(length_bytes)

    def create_data_group_2(self, image_path: str) -> dict[str, Any]:
        """
        Create a DG2 data group containing facial image data.

        Args:
            image_path: Path to the facial image file

        Returns:
            A dictionary representing DG2 data
        """
        # Read the image file
        with open(image_path, "rb") as f:
            image_data = f.read()

        return {
            "type": DataGroupType.DG2,
            "tag": "75",  # DG2 tag
            "data": image_data,
            "raw_bytes": self._format_dg2_bytes(image_data),
        }

    def _format_dg2_bytes(self, image_data: bytes) -> bytes:
        """
        Format image data as DG2 bytes.

        This is a simplified implementation. A full implementation would follow
        the ISO/IEC 19794-5 standard for facial image data.

        Args:
            image_data: The facial image data

        Returns:
            DG2 bytes
        """
        # This is a minimal implementation - a real one would be more complex
        tag = bytes.fromhex("75")

        # Basic template structure (simplified)
        biometric_header = bytes.fromhex("7F61") + self._encode_length(len(image_data) + 8)
        biometric_info = bytes.fromhex("020101")  # One instance of facial data
        biometric_data = bytes.fromhex("7F60") + self._encode_length(len(image_data) + 4)
        biometric_data_header = bytes.fromhex("5F2E") + self._encode_length(len(image_data))

        # Combine all parts
        content = (
            biometric_header + biometric_info + biometric_data + biometric_data_header + image_data
        )
        return tag + self._encode_length(len(content)) + content

    def create_signature_data(
        self, dg1: dict[str, Any], dg2: dict[str, Any], cert_path: str, key_path: str
    ) -> dict[str, Any]:
        """
        Create Security Object (SOD) containing document signatures.

        Args:
            dg1: DG1 data group
            dg2: DG2 data group
            cert_path: Path to the document signer certificate
            key_path: Path to the document signer private key

        Returns:
            A dictionary representing SOD data
        """
        # Hash the data groups
        hashes = {
            1: hashlib.sha256(dg1["raw_bytes"]).digest(),
            2: hashlib.sha256(dg2["raw_bytes"]).digest(),
        }

        # Create a simplified SOD structure
        # In a real implementation, this would use OpenSSL to create a proper signature
        return {
            "type": "SOD",
            "tag": "77",  # SOD tag
            "algorithm": "sha256WithRSAEncryption",
            "hashes": hashes,
            "certificate": cert_path,
            "raw_bytes": b"\x77\x04\x00\x00\x00\x00",  # Placeholder bytes
        }

    def generate_passport(
        self,
        issuing_country: str = "USA",
        name: str = "SMITH",
        surname: str = "JOHN",
        nationality: str = "USA",
        sex: str = "M",
        passport_num: str = "123456789",
        birth_date: str = "850531",  # YYMMDD
        expiry_date: str = "250531",  # YYMMDD
        image_path: str | None = None,
        cert_path: str | None = None,
        key_path: str | None = None,
        output_file: str | None = None,
    ) -> dict[str, Any]:
        """
        Generate a complete passport data structure.

        Args:
            issuing_country: 3-letter country code
            name: Surname
            surname: Given names
            nationality: 3-letter country code
            sex: M or F
            passport_num: Passport number
            birth_date: Date of birth (YYMMDD)
            expiry_date: Expiry date (YYMMDD)
            image_path: Path to facial image
            cert_path: Path to document signer certificate
            key_path: Path to document signer private key
            output_file: File to save the passport data to

        Returns:
            A dictionary containing the complete passport data structure
        """
        # Generate MRZ data
        mrz_data = self.generate_mrz(
            document_type="P",
            issuing_country=issuing_country,
            name=name,
            surname=surname,
            nationality=nationality,
            sex=sex,
            passport_num=passport_num,
            birth_date=birth_date,
            expiry_date=expiry_date,
        )

        # Create data groups
        dg1 = self.create_data_group_1(mrz_data)

        dg2 = None
        if image_path and os.path.exists(image_path):
            dg2 = self.create_data_group_2(image_path)

        sod = None
        if (
            dg2
            and cert_path
            and key_path
            and os.path.exists(cert_path)
            and os.path.exists(key_path)
        ):
            sod = self.create_signature_data(dg1, dg2, cert_path, key_path)

        # Create passport structure
        passport = {
            "mrz": mrz_data,
            "data_groups": {
                "DG1": dg1,
                "DG2": dg2 if dg2 else None,
            },
            "security": sod,
        }

        # Save if output file is specified
        if output_file and self.output_dir:
            output_path = os.path.join(self.output_dir, output_file)
            self._save_passport(passport, output_path)

        return passport

    def _save_passport(self, passport: dict[str, Any], output_path: str):
        """
        Save passport data to a file.

        Args:
            passport: Passport data structure
            output_path: Path to save the file to
        """
        import json

        # Convert binary data to hex strings for JSON serialization
        serializable = {"mrz": passport["mrz"], "data_groups": {}}

        for dg_name, dg in passport["data_groups"].items():
            if dg:
                serializable["data_groups"][dg_name] = {
                    "type": dg["type"].name if hasattr(dg["type"], "name") else str(dg["type"]),
                    "tag": dg["tag"],
                    "data": dg["data"].hex() if isinstance(dg["data"], bytes) else dg["data"],
                    "raw_bytes": dg["raw_bytes"].hex(),
                }

        if passport["security"]:
            sod = passport["security"]
            serializable["security"] = {
                "type": sod["type"],
                "tag": sod["tag"],
                "algorithm": sod["algorithm"],
                "hashes": {k: v.hex() for k, v in sod["hashes"].items()},
                "certificate": sod["certificate"],
                "raw_bytes": sod["raw_bytes"].hex(),
            }

        with open(output_path, "w") as f:
            json.dump(serializable, f, indent=2)
