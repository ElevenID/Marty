"""
TD-2 MRZ (Machine Readable Zone) generation utilities.

This module implements TD-2 MRZ generation per ICAO Part 6:
- TD-2 two-line format (36 characters each line)
- Field width enforcement and filler characters
- Check digit computation using ICAO algorithm (via Rust marty_rs)
- Visual and data alignment rules per Part 6
- Name truncation with primary identifier precedence

TD-2 format:
Line 1: Document type (2) + Issuing state (3) + Document number (9) + Check digit (1) +
       Optional data (15) + Check digit (1) + Birth date (6) + Check digit (1) + Sex (1) +
       Expiry date (6) + Check digit (1) + Nationality (3) + Optional data (11) + Check digit (1)
Line 2: Name field (36)
"""

from __future__ import annotations

import re
from datetime import date

from marty_backend_common.crypto_bridge import compute_check_digit as _rust_compute_check_digit
from marty_plugin.shared.models.td2 import PersonalData, TD2Document, TD2DocumentData, TD2MRZData


class TD2MRZGenerator:
    """Generator for TD-2 MRZ lines with check digit computation."""

    # Character mapping for MRZ
    MRZ_CHARACTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<"

    # Check digit weights (ICAO standard) - kept for documentation
    CHECK_DIGIT_WEIGHTS = [7, 3, 1]

    # TD-2 specific constants
    TD2_LINE_LENGTH = 36
    TD2_LINES = 2

    @classmethod
    def sanitize_for_mrz(cls, text: str, max_length: int, filler: str = "<") -> str:
        """
        Sanitize text for MRZ format.

        Args:
            text: Input text
            max_length: Maximum length
            filler: Filler character

        Returns:
            Sanitized MRZ text
        """
        if not text:
            return filler * max_length

        # Convert to uppercase and remove invalid characters
        text = text.upper()
        text = re.sub(r"[^A-Z0-9<]", "<", text)

        # Replace multiple consecutive < with single <
        text = re.sub(r"<+", "<", text)

        # Truncate or pad to required length
        return text[:max_length] if len(text) > max_length else text.ljust(max_length, filler)

    @classmethod
    def compute_check_digit(cls, data: str) -> str:
        """
        Compute check digit for MRZ field using ICAO algorithm.

        Uses Rust implementation via marty_rs for correctness and performance.

        Args:
            data: Input data string

        Returns:
            Single character check digit
        """
        if not data:
            return "0"
        return _rust_compute_check_digit(data)

    @classmethod
    def format_date_for_mrz(cls, date_obj: date) -> str:
        """
        Format date for MRZ (YYMMDD format).

        Args:
            date_obj: Date object

        Returns:
            6-character date string
        """
        return date_obj.strftime("%y%m%d")

    @classmethod
    def format_name_for_td2(
        cls, primary_identifier: str, secondary_identifier: str | None = None
    ) -> str:
        """
        Format name for TD-2 MRZ with primary identifier precedence per ICAO Part 6.

        Implementation follows ICAO Doc 9303 Part 6 requirements:
        - Primary identifier (surname) has absolute precedence
        - Primary identifier must be preserved in full if possible
        - Secondary identifier (given names) can be truncated if needed
        - Names are separated by double filler character "<<"
        - Multiple given names are separated by single filler "<"
        - Total field length is exactly 36 characters

        Args:
            primary_identifier: Primary identifier (surname)
            secondary_identifier: Secondary identifier (given names)

        Returns:
            Formatted name string (exactly 36 characters)
        """
        if not primary_identifier:
            # If no primary identifier, fill entire field with fillers
            return "<" * cls.TD2_LINE_LENGTH

        # Sanitize and prepare primary identifier
        primary = cls.sanitize_for_mrz(primary_identifier, cls.TD2_LINE_LENGTH - 2).rstrip("<")

        # If primary identifier alone exceeds available space, truncate it
        if len(primary) > cls.TD2_LINE_LENGTH - 2:  # Reserve 2 chars for minimal secondary
            primary = primary[: cls.TD2_LINE_LENGTH - 2]

        # Start building name field with primary identifier
        name_field = primary

        # Add secondary identifier if present and there's space
        if secondary_identifier and len(name_field) < cls.TD2_LINE_LENGTH - 2:
            # Add separator
            name_field += "<<"

            # Calculate remaining space for secondary identifier
            remaining_space = cls.TD2_LINE_LENGTH - len(name_field)

            if remaining_space > 0:
                # Process secondary identifier (given names)
                secondary = cls.sanitize_for_mrz(secondary_identifier, remaining_space).rstrip("<")

                # Handle multiple given names with proper truncation
                if secondary:
                    # Split into individual given names
                    given_names = [
                        name.strip() for name in secondary.replace("<", " ").split() if name.strip()
                    ]

                    # Add given names one by one until space runs out
                    added_names = []
                    current_length = len(name_field)

                    for i, given_name in enumerate(given_names):
                        # Calculate space needed for this name (plus separator if not first)
                        separator_length = 1 if i > 0 else 0  # "<" between given names
                        needed_space = len(given_name) + separator_length

                        if current_length + needed_space <= cls.TD2_LINE_LENGTH:
                            # Full name fits
                            if i > 0:
                                name_field += "<"
                            name_field += given_name
                            current_length += needed_space
                            added_names.append(given_name)
                        else:
                            # Try to fit truncated version of current name
                            available_space = (
                                cls.TD2_LINE_LENGTH - current_length - separator_length
                            )
                            if available_space > 0:
                                if i > 0:
                                    name_field += "<"
                                truncated_name = given_name[:available_space]
                                name_field += truncated_name
                                current_length = cls.TD2_LINE_LENGTH
                            break

        # Pad to exact field length with fillers
        return name_field.ljust(cls.TD2_LINE_LENGTH, "<")

    @classmethod
    def validate_td2_name_compliance(
        cls, primary_identifier: str, secondary_identifier: str | None = None
    ) -> dict:
        """
        Validate TD-2 name formatting compliance with ICAO Part 6.

        Args:
            primary_identifier: Primary identifier (surname)
            secondary_identifier: Secondary identifier (given names)

        Returns:
            Dictionary with validation results and warnings
        """
        result = {"compliant": True, "warnings": [], "truncations": []}

        formatted_name = cls.format_name_for_td2(primary_identifier, secondary_identifier)

        # Check if primary identifier was truncated
        primary_clean = cls.sanitize_for_mrz(primary_identifier, 50).rstrip("<")
        if "<<" in formatted_name:
            name_parts = formatted_name.split("<<", 1)
            formatted_primary = name_parts[0].rstrip("<")
            if len(formatted_primary) < len(primary_clean):
                result["warnings"].append("Primary identifier (surname) was truncated")
                result["truncations"].append(
                    {
                        "field": "primary_identifier",
                        "original": primary_identifier,
                        "truncated": formatted_primary,
                    }
                )

        # Check if secondary identifier was truncated
        if secondary_identifier and "<<" in formatted_name:
            name_parts = formatted_name.split("<<", 1)
            if len(name_parts) > 1:
                formatted_secondary = name_parts[1].rstrip("<").replace("<", " ")
                original_secondary = secondary_identifier.strip()
                if len(formatted_secondary.replace(" ", "")) < len(
                    original_secondary.replace(" ", "")
                ):
                    result["warnings"].append("Secondary identifier (given names) was truncated")
                    result["truncations"].append(
                        {
                            "field": "secondary_identifier",
                            "original": secondary_identifier,
                            "truncated": formatted_secondary,
                        }
                    )

        # Check for non-standard characters
        if primary_identifier and not all(
            c.isalpha() or c.isspace() or c in "-'" for c in primary_identifier
        ):
            result["warnings"].append("Primary identifier contains non-standard characters")

        if secondary_identifier and not all(
            c.isalpha() or c.isspace() or c in "-'" for c in secondary_identifier
        ):
            result["warnings"].append("Secondary identifier contains non-standard characters")

        return result

    @classmethod
    def generate_td2_mrz(cls, document: TD2Document) -> TD2MRZData:
        """
        Generate TD-2 MRZ lines.

        TD-2 MRZ format (2 lines, 36 chars each):
        Line 1: Document type (2) + Issuing state (3) + Document number (9) +
                Check digit (1) + Optional data (15) + Check digit (1) +
                Birth date (6) + Check digit (1) + Sex (1) + Expiry date (6) +
                Check digit (1) + Nationality (3) + Optional data (11) + Check digit (1)
        Line 2: Name field (36)

        Args:
            document: TD2Document instance

        Returns:
            TD2MRZData with generated MRZ lines
        """
        personal = document.personal_data
        doc_data = document.document_data

        # Line 1 construction
        # Document type (1-2 chars, padded to 2)
        doc_type = doc_data.document_type.value.ljust(2, "<")

        # Issuing state (3 chars)
        issuing_state = doc_data.issuing_state

        # Document number (up to 9 chars, padded with <)
        doc_number = cls.sanitize_for_mrz(doc_data.document_number, 9)

        # Check digit for document number
        doc_check = cls.compute_check_digit(doc_number)

        # Birth date (6 chars)
        birth_date = cls.format_date_for_mrz(personal.date_of_birth)

        # Check digit for birth date
        birth_check = cls.compute_check_digit(birth_date)

        # Sex (1 char)
        sex = personal.gender.value

        # Expiry date (6 chars)
        expiry_date = cls.format_date_for_mrz(doc_data.date_of_expiry)

        # Check digit for expiry date
        expiry_check = cls.compute_check_digit(expiry_date)

        # Nationality (3 chars)
        nationality = personal.nationality

        # Optional data (2 chars) - using filler for now
        optional_data = "<" * 2

        # Composite check digit (overall check for key fields)
        composite_data = (
            doc_number
            + doc_check
            + birth_date
            + birth_check
            + expiry_date
            + expiry_check
            + optional_data
        )
        composite_check = cls.compute_check_digit(composite_data)

        # Construct Line 1 (36 characters total)
        # Format: Type(2) + State(3) + DocNum(9) + DocCheck(1) + Birth(6) + BirthCheck(1) +
        # Sex(1) + Expiry(6) + ExpiryCheck(1) + Nationality(3) + Optional(2) + CompositeCheck(1)
        line1 = (
            doc_type
            + issuing_state
            + doc_number
            + doc_check
            + birth_date
            + birth_check
            + sex
            + expiry_date
            + expiry_check
            + nationality
            + optional_data
            + composite_check
        )

        # Verify line 1 length
        if len(line1) != cls.TD2_LINE_LENGTH:
            msg = f"TD-2 Line 1 length mismatch: {len(line1)} != {cls.TD2_LINE_LENGTH}"
            raise ValueError(msg)

        # Line 2: Name field
        line2 = cls.format_name_for_td2(personal.primary_identifier, personal.secondary_identifier)

        # Create MRZ data object
        return TD2MRZData(
            line1=line1,
            line2=line2,
            check_digit_document=doc_check,
            check_digit_dob=birth_check,
            check_digit_expiry=expiry_check,
            check_digit_composite=composite_check,
        )

    @classmethod
    def generate_from_data(
        cls, personal_data: PersonalData, document_data: TD2DocumentData
    ) -> TD2MRZData:
        """
        Generate TD-2 MRZ from separate data components.

        Args:
            personal_data: Personal information
            document_data: Document information

        Returns:
            TD2MRZData with generated MRZ lines
        """
        # Create temporary document for generation
        temp_document = TD2Document(personal_data=personal_data, document_data=document_data)

        return cls.generate_td2_mrz(temp_document)


class TD2MRZParser:
    """Parser for TD-2 MRZ lines with validation."""

    @classmethod
    def parse_td2_mrz(cls, line1: str, line2: str) -> dict:
        """
        Parse TD-2 MRZ lines and extract data.

        Args:
            line1: First line of TD-2 MRZ (36 chars)
            line2: Second line of TD-2 MRZ (36 chars)

        Returns:
            Dictionary with parsed data
        """
        if len(line1) != 36 or len(line2) != 36:
            msg = "TD-2 MRZ lines must be exactly 36 characters each"
            raise ValueError(msg)

        # Parse Line 1
        doc_type = line1[0:2].rstrip("<")
        issuing_state = line1[2:5]
        document_number = line1[5:14].rstrip("<")
        doc_check = line1[14]
        line1[15:30].rstrip("<")
        line1[30]
        birth_date = line1[31:37]
        # Note: There seems to be an error in the line1 parsing above, let me fix it

        # Correct parsing for Line 1 (36 chars total)
        doc_type = line1[0:2].rstrip("<")
        issuing_state = line1[2:5]
        document_number = line1[5:14].rstrip("<")
        doc_check = line1[14]
        # Continuing from position 15, but we need to fit everything in 36 chars
        # Let me recalculate based on the actual TD-2 format

        # TD-2 Line 1 breakdown:
        # Positions 1-2: Document type (2)
        # Positions 3-5: Issuing state (3)
        # Positions 6-14: Document number (9)
        # Position 15: Check digit doc number (1)
        # Positions 16-21: Birth date (6)
        # Position 22: Check digit birth date (1)
        # Position 23: Sex (1)
        # Positions 24-29: Expiry date (6)
        # Position 30: Check digit expiry (1)
        # Positions 31-33: Nationality (3)
        # Positions 34-35: Optional data (2)
        # Position 36: Composite check digit (1)

        doc_type = line1[0:2].rstrip("<")
        issuing_state = line1[2:5]
        document_number = line1[5:14].rstrip("<")
        doc_check = line1[14]
        birth_date = line1[15:21]
        birth_check = line1[21]
        sex = line1[22]
        expiry_date = line1[23:29]
        expiry_check = line1[29]
        nationality = line1[30:33]
        optional_data = line1[33:35].rstrip("<")
        composite_check = line1[35]

        # Parse Line 2 (name field)
        name_field = line2.rstrip("<")

        # Split name field
        if "<<" in name_field:
            parts = name_field.split("<<", 1)
            primary_identifier = parts[0]
            secondary_identifier = parts[1].replace("<", " ").strip() if len(parts) > 1 else None
        else:
            primary_identifier = name_field.replace("<", " ").strip()
            secondary_identifier = None

        # Parse dates
        try:
            birth_year = (
                2000 + int(birth_date[0:2])
                if int(birth_date[0:2]) < 30
                else 1900 + int(birth_date[0:2])
            )
            birth_month = int(birth_date[2:4])
            birth_day = int(birth_date[4:6])
            parsed_birth_date = date(birth_year, birth_month, birth_day)
        except (ValueError, IndexError):
            parsed_birth_date = None

        try:
            expiry_year = (
                2000 + int(expiry_date[0:2])
                if int(expiry_date[0:2]) < 30
                else 1900 + int(expiry_date[0:2])
            )
            expiry_month = int(expiry_date[2:4])
            expiry_day = int(expiry_date[4:6])
            parsed_expiry_date = date(expiry_year, expiry_month, expiry_day)
        except (ValueError, IndexError):
            parsed_expiry_date = None

        return {
            "document_type": doc_type,
            "issuing_state": issuing_state,
            "document_number": document_number,
            "check_digit_document": doc_check,
            "birth_date": parsed_birth_date,
            "check_digit_birth": birth_check,
            "sex": sex,
            "expiry_date": parsed_expiry_date,
            "check_digit_expiry": expiry_check,
            "nationality": nationality,
            "optional_data": optional_data,
            "check_digit_composite": composite_check,
            "primary_identifier": primary_identifier,
            "secondary_identifier": secondary_identifier,
            "raw_line1": line1,
            "raw_line2": line2,
        }

    @classmethod
    def validate_check_digits(cls, parsed_data: dict) -> dict:
        """
        Validate check digits in parsed TD-2 MRZ data.

        Args:
            parsed_data: Dictionary from parse_td2_mrz

        Returns:
            Dictionary with validation results
        """
        generator = TD2MRZGenerator()

        results = {
            "document_check_valid": False,
            "birth_check_valid": False,
            "expiry_check_valid": False,
            "composite_check_valid": False,
            "all_checks_valid": False,
        }

        # Validate document number check digit
        doc_num_padded = parsed_data["document_number"].ljust(9, "<")
        expected_doc_check = generator.compute_check_digit(doc_num_padded)
        results["document_check_valid"] = expected_doc_check == parsed_data["check_digit_document"]

        # Validate birth date check digit
        if parsed_data["birth_date"]:
            birth_date_str = generator.format_date_for_mrz(parsed_data["birth_date"])
            expected_birth_check = generator.compute_check_digit(birth_date_str)
            results["birth_check_valid"] = expected_birth_check == parsed_data["check_digit_birth"]

        # Validate expiry date check digit
        if parsed_data["expiry_date"]:
            expiry_date_str = generator.format_date_for_mrz(parsed_data["expiry_date"])
            expected_expiry_check = generator.compute_check_digit(expiry_date_str)
            results["expiry_check_valid"] = (
                expected_expiry_check == parsed_data["check_digit_expiry"]
            )

        # Validate composite check digit
        # Reconstruct the composite data string
        optional_data_padded = parsed_data["optional_data"].ljust(2, "<")
        composite_data = (
            doc_num_padded
            + parsed_data["check_digit_document"]
            + generator.format_date_for_mrz(parsed_data["birth_date"])
            + parsed_data["check_digit_birth"]
            + generator.format_date_for_mrz(parsed_data["expiry_date"])
            + parsed_data["check_digit_expiry"]
            + optional_data_padded
        )
        expected_composite_check = generator.compute_check_digit(composite_data)
        results["composite_check_valid"] = (
            expected_composite_check == parsed_data["check_digit_composite"]
        )

        # Overall validation
        results["all_checks_valid"] = all(
            [
                results["document_check_valid"],
                results["birth_check_valid"],
                results["expiry_check_valid"],
                results["composite_check_valid"],
            ]
        )

        return results


class TD2MRZFormatter:
    """Formatter for displaying TD-2 MRZ data."""

    @classmethod
    def format_for_display(cls, mrz_data: TD2MRZData) -> str:
        """
        Format TD-2 MRZ data for human-readable display.

        Args:
            mrz_data: TD2MRZData instance

        Returns:
            Formatted string for display
        """
        return f"TD-2 MRZ:\nLine 1: {mrz_data.line1}\nLine 2: {mrz_data.line2}"

    @classmethod
    def format_with_labels(cls, mrz_data: TD2MRZData) -> str:
        """
        Format TD-2 MRZ with field labels for debugging.

        Args:
            mrz_data: TD2MRZData instance

        Returns:
            Formatted string with field labels
        """
        line1 = mrz_data.line1
        line2 = mrz_data.line2

        # Parse line1 for labeling
        doc_type = line1[0:2]
        issuing_state = line1[2:5]
        document_number = line1[5:14]
        doc_check = line1[14]
        birth_date = line1[15:21]
        birth_check = line1[21]
        sex = line1[22]
        expiry_date = line1[23:29]
        expiry_check = line1[29]
        nationality = line1[30:33]
        optional_data = line1[33:35]
        composite_check = line1[35]

        result = "TD-2 MRZ (Labeled):\n"
        result += f"Line 1: {line1}\n"
        result += f"  Doc Type: {doc_type}\n"
        result += f"  Issuing State: {issuing_state}\n"
        result += f"  Document Number: {document_number} (Check: {doc_check})\n"
        result += f"  Birth Date: {birth_date} (Check: {birth_check})\n"
        result += f"  Sex: {sex}\n"
        result += f"  Expiry Date: {expiry_date} (Check: {expiry_check})\n"
        result += f"  Nationality: {nationality}\n"
        result += f"  Optional Data: {optional_data}\n"
        result += f"  Composite Check: {composite_check}\n"
        result += f"Line 2: {line2}\n"
        result += f"  Name Field: {line2.rstrip('<')}\n"

        return result
