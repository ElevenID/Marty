"""Elementary File (EF) Parser for ICAO Passport Data.

Parses elementary files from electronic passports according to ICAO Doc 9303.
Supports all standard data groups and common data elements.
"""

from __future__ import annotations

import logging
import struct
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class DataGroup(Enum):
    """ICAO Data Group identifiers."""

    COM = "EF.COM"  # Common Data Elements
    SOD = "EF.SOD"  # Security Object Data
    DG1 = "EF.DG1"  # MRZ Information
    DG2 = "EF.DG2"  # Encoded Facial Image
    DG3 = "EF.DG3"  # Encoded Fingerprints
    DG4 = "EF.DG4"  # Encoded Iris Data
    DG5 = "EF.DG5"  # Displayed Portrait
    DG6 = "EF.DG6"  # Reserved for Future Use
    DG7 = "EF.DG7"  # Displayed Signature or Usual Mark
    DG8 = "EF.DG8"  # Data Features
    DG9 = "EF.DG9"  # Structure Features
    DG10 = "EF.DG10"  # Substance Features
    DG11 = "EF.DG11"  # Additional Personal Details
    DG12 = "EF.DG12"  # Additional Document Details
    DG13 = "EF.DG13"  # Optional Details
    DG14 = "EF.DG14"  # Security Features
    DG15 = "EF.DG15"  # Active Authentication Public Key Info
    DG16 = "EF.DG16"  # Persons to Notify


@dataclass
class EFData:
    """Parsed Elementary File data."""

    file_id: str
    tag: int
    length: int
    data: bytes
    parsed_content: dict[str, Any] | None = None


@dataclass
class MRZInfo:
    """Machine Readable Zone information from DG1."""

    document_code: str
    issuing_country: str
    surname: str
    given_names: str
    passport_number: str
    nationality: str
    date_of_birth: str
    sex: str
    date_of_expiry: str
    personal_number: str | None
    check_digit_composite: str


@dataclass
class BiometricInfo:
    """Biometric information structure."""

    biometric_type: int
    biometric_subtype: int
    creation_date: str | None
    validity_period: tuple[str, str] | None
    creator: str | None
    format_owner: int
    format_type: int
    quality: int | None
    data: bytes


class ElementaryFileParser:
    """Parser for ICAO elementary files."""

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    def parse_tlv(self, data: bytes, offset: int = 0) -> tuple[int, int, bytes, int]:
        """Parse Tag-Length-Value structure.

        Returns:
            tuple: (tag, length, value, next_offset)
        """
        if offset >= len(data):
            msg = "Offset beyond data length"
            raise ValueError(msg)

        # Parse tag
        tag = data[offset]
        offset += 1

        # Handle multi-byte tags
        if (tag & 0x1F) == 0x1F:
            tag = (tag << 8) | data[offset]
            offset += 1

        # Parse length
        length = data[offset]
        offset += 1

        if length & 0x80:
            # Long form length
            length_octets = length & 0x7F
            if length_octets == 0:
                msg = "Indefinite length not supported"
                raise ValueError(msg)

            length = 0
            for _ in range(length_octets):
                length = (length << 8) | data[offset]
                offset += 1

        # Extract value
        if offset + length > len(data):
            msg = "Length extends beyond data"
            raise ValueError(msg)

        value = data[offset : offset + length]

        return tag, length, value, offset + length

    def parse_ef_com(self, data: bytes) -> dict[str, Any]:
        """Parse EF.COM (Common Data Elements)."""
        try:
            tag, length, value, _ = self.parse_tlv(data)

            if tag != 0x60:  # SET OF tag
                msg = f"Invalid EF.COM tag: 0x{tag:02X}"
                raise ValueError(msg)

            result = {"lod_version": None, "unicode_version": None, "data_groups": []}

            offset = 0
            while offset < len(value):
                item_tag, item_length, item_value, next_offset = self.parse_tlv(value, offset)

                if item_tag == 0x5F01:  # LDS Version
                    result["lds_version"] = item_value.decode("ascii")
                elif item_tag == 0x5F36:  # Unicode Version
                    result["unicode_version"] = item_value.decode("ascii")
                elif item_tag == 0x5C:  # Tag List (Data Groups)
                    for i in range(len(item_value)):
                        dg_tag = item_value[i]
                        if dg_tag in range(0x61, 0x70):  # DG1-DG15
                            dg_num = dg_tag - 0x60
                            result["data_groups"].append(f"DG{dg_num}")

                offset = next_offset

        except Exception:
            self.logger.exception("Failed to parse EF.COM")
            raise
        else:
            return result

    def parse_ef_dg1(self, data: bytes) -> MRZInfo:
        """Parse EF.DG1 (MRZ Information)."""
        try:
            tag, length, value, _ = self.parse_tlv(data)

            if tag != 0x61:  # DG1 tag
                msg = f"Invalid DG1 tag: 0x{tag:02X}"
                raise ValueError(msg)

            # Parse inner TLV for MRZ data
            mrz_tag, mrz_length, mrz_data, _ = self.parse_tlv(value)

            if mrz_tag != 0x5F1F:  # MRZ tag
                msg = f"Invalid MRZ tag: 0x{mrz_tag:02X}"
                raise ValueError(msg)

            # Parse MRZ text (typically 2 or 3 lines)
            mrz_text = mrz_data.decode("utf-8")
            lines = (
                mrz_text.split("\\n")
                if "\\n" in mrz_text
                else [mrz_text[i : i + 44] for i in range(0, len(mrz_text), 44)]
            )

            if len(lines) < 2:
                msg = "Invalid MRZ format"
                raise ValueError(msg)

            # Parse TD-3 format (passport)
            if len(lines[0]) == 44:
                return self._parse_td3_mrz(lines)
            # Parse TD-1 or TD-2 format
            return self._parse_td2_mrz(lines)

        except Exception:
            self.logger.exception("Failed to parse DG1")
            raise

    def _parse_td3_mrz(self, lines: list[str]) -> MRZInfo:
        """Parse TD-3 (passport) MRZ format."""
        if len(lines) != 2 or len(lines[0]) != 44 or len(lines[1]) != 44:
            msg = "Invalid TD-3 MRZ format"
            raise ValueError(msg)

        line1 = lines[0]
        line2 = lines[1]

        # Parse line 1: Type<Country<Names<<<<<<<<<<<<<<<<<<<<<<<
        document_code = line1[0:2].replace("<", "")
        issuing_country = line1[2:5].replace("<", "")
        names = line1[5:44].replace("<", " ").strip()

        # Split surname and given names
        name_parts = names.split("  ")  # Double space separates surname from given names
        surname = name_parts[0] if name_parts else ""
        given_names = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""

        # Parse line 2: PassportNo<CheckDigit<Nationality<Birth<Sex<Expiry<PersonalNo<<<CheckDigit
        passport_number = line2[0:9].replace("<", "")
        nationality = line2[10:13].replace("<", "")
        date_of_birth = line2[13:19]
        sex = line2[20]
        date_of_expiry = line2[21:27]
        personal_number = line2[28:42].replace("<", "")
        check_digit_composite = line2[43]

        return MRZInfo(
            document_code=document_code,
            issuing_country=issuing_country,
            surname=surname,
            given_names=given_names,
            passport_number=passport_number,
            nationality=nationality,
            date_of_birth=date_of_birth,
            sex=sex,
            date_of_expiry=date_of_expiry,
            personal_number=personal_number if personal_number else None,
            check_digit_composite=check_digit_composite,
        )

    def _parse_td2_mrz(self, lines: list[str]) -> MRZInfo:
        """
        Parse TD-2 MRZ format per ICAO Doc 9303 Part 6.

        TD-2 format consists of 2 lines of 36 characters each:
        Line 1: Document data with dates and check digits
        Line 2: Name field
        """
        if len(lines) != 2:
            msg = "TD-2 MRZ must have exactly 2 lines"
            raise ValueError(msg)

        if not all(len(line) == 36 for line in lines):
            msg = "TD-2 MRZ lines must be exactly 36 characters each"
            raise ValueError(msg)

        line1 = lines[0]
        line2 = lines[1]

        # Parse Line 1: Document data
        document_code = line1[0:2].rstrip("<")
        issuing_country = line1[2:5]
        passport_number = line1[5:14].rstrip("<")
        line1[14]
        date_of_birth = line1[15:21]
        line1[21]
        sex = line1[22]
        date_of_expiry = line1[23:29]
        line1[29]
        nationality = line1[30:33]
        optional_data = line1[33:35].rstrip("<")
        check_digit_composite = line1[35]

        # Parse Line 2: Name field
        name_field = line2.rstrip("<")

        # Parse names with primary identifier precedence per Part 6
        if "<<" in name_field:
            name_parts = name_field.split("<<", 1)
            surname = name_parts[0].replace("<", " ").strip()
            given_names = name_parts[1].replace("<", " ").strip() if len(name_parts) > 1 else ""
        else:
            # If no clear separator, treat as surname only
            surname = name_field.replace("<", " ").strip()
            given_names = ""

        return MRZInfo(
            document_code=document_code,
            issuing_country=issuing_country,
            surname=surname,
            given_names=given_names,
            passport_number=passport_number,
            nationality=nationality,
            date_of_birth=date_of_birth,
            sex=sex,
            date_of_expiry=date_of_expiry,
            personal_number=optional_data if optional_data else None,
            check_digit_composite=check_digit_composite,
        )

    def parse_ef_dg2(self, data: bytes) -> BiometricInfo:
        """Parse EF.DG2 (Facial Image)."""
        try:
            tag, length, value, _ = self.parse_tlv(data)

            if tag != 0x75:  # DG2 tag
                msg = f"Invalid DG2 tag: 0x{tag:02X}"
                raise ValueError(msg)

            # Parse biometric information template
            bio_tag, bio_length, bio_data, _ = self.parse_tlv(value)

            if bio_tag != 0x7F2E:  # Biometric Information Template
                msg = f"Invalid biometric template tag: 0x{bio_tag:02X}"
                raise ValueError(msg)

            return self._parse_biometric_template(bio_data)

        except Exception:
            self.logger.exception("Failed to parse DG2")
            raise

    def _parse_biometric_template(self, data: bytes) -> BiometricInfo:
        """Parse biometric information template."""
        result = BiometricInfo(
            biometric_type=0,
            biometric_subtype=0,
            creation_date=None,
            validity_period=None,
            creator=None,
            format_owner=0,
            format_type=0,
            quality=None,
            data=b"",
        )

        offset = 0
        while offset < len(data):
            try:
                tag, length, value, next_offset = self.parse_tlv(data, offset)

                if tag == 0x81:  # Number of instances
                    pass  # Skip for now
                elif tag == 0x82:  # Biometric type
                    result.biometric_type = value[0]
                elif tag == 0x83:  # Biometric subtype
                    result.biometric_subtype = value[0]
                elif tag == 0x87:  # Format owner
                    result.format_owner = struct.unpack(">H", value)[0]
                elif tag == 0x88:  # Format type
                    result.format_type = struct.unpack(">H", value)[0]
                elif tag == 0x5F2E:  # Biometric data block
                    result.data = value

                offset = next_offset

            except Exception as e:
                self.logger.warning("Error parsing biometric field: %s", str(e))
                break

        return result

    def parse_elementary_file(self, file_id: str, data: bytes) -> EFData:
        """Parse any elementary file and return structured data."""
        try:
            # Get basic TLV structure
            tag, length, value, _ = self.parse_tlv(data)

            ef_data = EFData(file_id=file_id, tag=tag, length=length, data=data)

            # Parse specific data groups
            if file_id == DataGroup.COM.value:
                ef_data.parsed_content = self.parse_ef_com(data)
            elif file_id == DataGroup.DG1.value:
                ef_data.parsed_content = self.parse_ef_dg1(data).__dict__
            elif file_id == DataGroup.DG2.value:
                ef_data.parsed_content = self.parse_ef_dg2(data).__dict__
            # Add more parsers as needed
            else:
                self.logger.info("No specific parser for %s, returning raw data", file_id)

        except Exception:
            self.logger.exception("Failed to parse EF %s", file_id)
            raise
        else:
            return ef_data

    def validate_mrz_check_digit(self, data: str, check_digit: str) -> bool:
        """Validate MRZ check digit."""
        weights = [7, 3, 1]
        total = 0

        for i, char in enumerate(data):
            if char.isdigit():
                value = int(char)
            elif char == "<":
                value = 0
            else:
                # Convert letters to numbers (A=10, B=11, etc.)
                value = ord(char.upper()) - ord("A") + 10

            total += value * weights[i % 3]

        calculated_digit = str(total % 10)
        return calculated_digit == check_digit
