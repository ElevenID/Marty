"""
MRZ (Machine Readable Zone) generation for visa documents.

This module implements MRZ generation for ICAO Part 7 visa types:
- Type A visas: 2-line MRZ (44 characters each)
- Type B visas: 3-line MRZ (36 characters each)

Follows ICAO Doc 9303 Part 7 specifications for visa MRZ format
and check digit computation algorithms (via Rust marty_rs).
"""

import re
from datetime import date

from marty_common.crypto_bridge import compute_check_digit as _rust_compute_check_digit
from marty_plugin.shared.models.visa import MRZData, Visa, VisaType


class MRZGenerator:
    """Generator for visa MRZ lines with check digit computation."""

    # Character mapping for MRZ
    MRZ_CHARACTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<"

    # Check digit weights - kept for documentation
    CHECK_DIGIT_WEIGHTS = [7, 3, 1]

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
    def format_name_for_mrz(cls, surname: str, given_names: str, max_length: int) -> str:
        """
        Format name for MRZ with proper truncation.

        Args:
            surname: Primary surname
            given_names: Given names
            max_length: Maximum field length

        Returns:
            Formatted name string
        """
        # Sanitize names
        surname = cls.sanitize_for_mrz(surname, 39)
        given_names = cls.sanitize_for_mrz(given_names, 39)

        # Remove trailing < from names
        surname = surname.rstrip("<")
        given_names = given_names.rstrip("<")

        # Split given names
        given_parts = [part for part in given_names.split("<") if part]

        # Start with surname
        name_field = surname

        # Add separator
        if given_parts:
            name_field += "<<"

        # Add given names with < separators
        max_length - len(name_field)

        for i, given_name in enumerate(given_parts):
            if i > 0:
                separator = "<"
                if len(name_field) + len(separator) + len(given_name) <= max_length:
                    name_field += separator
                else:
                    break

            if len(name_field) + len(given_name) <= max_length:
                name_field += given_name
            else:
                # Truncate the given name to fit
                available_space = max_length - len(name_field)
                if available_space > 0:
                    name_field += given_name[:available_space]
                break

        # Pad to required length
        return name_field.ljust(max_length, "<")

    @classmethod
    def generate_type_a_mrz(cls, visa: Visa) -> tuple[str, str, MRZData]:
        """
        Generate Type A (2-line) MRZ for visa.

        Type A format:
        Line 1: V<UTOPIATYSHXL123456<9111123<<<<<<<
        Line 2: 7408122F1204159UTO<<<<<<<<<<<<<<<<<6

        Args:
            visa: Visa object

        Returns:
            Tuple of (line1, line2, mrz_data)
        """
        personal = visa.personal_data
        document = visa.document_data

        # Line 1: Document type, issuing state, document number, check digit, optional data
        line1_parts = []

        # Document type (V for visa)
        line1_parts.append("V")

        # Issuing state (3 chars)
        issuing_state = cls.sanitize_for_mrz(document.issuing_state, 3)
        line1_parts.append(issuing_state)

        # Document number (up to 9 chars)
        doc_number = cls.sanitize_for_mrz(document.document_number, 9)
        line1_parts.append(doc_number)

        # Check digit for document number
        doc_check = cls.compute_check_digit(doc_number.rstrip("<"))
        line1_parts.append(doc_check)

        # Optional data (nationality, visa category, etc.) - remaining space
        used_length = sum(len(part) for part in line1_parts)
        remaining = 44 - used_length

        # Include nationality and visa category in optional data
        optional_data = f"{personal.nationality}{document.visa_category.value}"
        optional_data = cls.sanitize_for_mrz(optional_data, remaining)
        line1_parts.append(optional_data)

        line1 = "".join(line1_parts)

        # Line 2: Date of birth, check digit, sex, expiry date, check digit, nationality, optional data, composite check
        line2_parts = []

        # Date of birth (6 chars)
        dob = cls.format_date_for_mrz(personal.date_of_birth)
        line2_parts.append(dob)

        # Check digit for date of birth
        dob_check = cls.compute_check_digit(dob)
        line2_parts.append(dob_check)

        # Sex (1 char)
        line2_parts.append(personal.gender.value)

        # Date of expiry (6 chars)
        expiry = cls.format_date_for_mrz(document.date_of_expiry)
        line2_parts.append(expiry)

        # Check digit for expiry date
        expiry_check = cls.compute_check_digit(expiry)
        line2_parts.append(expiry_check)

        # Nationality (3 chars)
        nationality = cls.sanitize_for_mrz(personal.nationality, 3)
        line2_parts.append(nationality)

        # Optional data - remaining space except for composite check digit
        used_length = sum(len(part) for part in line2_parts) + 1  # +1 for composite check
        remaining = 44 - used_length

        # Additional optional data (can include additional visa info)
        additional_optional = cls.sanitize_for_mrz("", remaining)
        line2_parts.append(additional_optional)

        # Composite check digit (calculated from specific fields)
        composite_data = (
            doc_number.rstrip("<") + doc_check + dob + dob_check + expiry + expiry_check
        )
        composite_check = cls.compute_check_digit(composite_data)
        line2_parts.append(composite_check)

        line2 = "".join(line2_parts)

        # Create MRZ data object
        mrz_data = MRZData(
            type_a_line1=line1,
            type_a_line2=line2,
            check_digit_document=doc_check,
            check_digit_dob=dob_check,
            check_digit_expiry=expiry_check,
            check_digit_composite=composite_check,
        )

        return line1, line2, mrz_data

    @classmethod
    def generate_type_b_mrz(cls, visa: Visa) -> tuple[str, str, str, MRZData]:
        """
        Generate Type B (3-line) MRZ for visa.

        Type B format:
        Line 1: V<UTOPIA<<<<<<<<<<<<<<<<<<<<<<<<<<
        Line 2: L123456<0UTO7408122F1204159<<<<<
        Line 3: <<<<<<<<<<<<<<<<<ERIKSSON<<ANNA<5

        Args:
            visa: Visa object

        Returns:
            Tuple of (line1, line2, line3, mrz_data)
        """
        personal = visa.personal_data
        document = visa.document_data

        # Line 1: Document type, issuing state, optional data
        line1_parts = []

        # Document type (V for visa)
        line1_parts.append("V")

        # Issuing state (3 chars)
        issuing_state = cls.sanitize_for_mrz(document.issuing_state, 3)
        line1_parts.append(issuing_state)

        # Optional data for remaining space
        used_length = sum(len(part) for part in line1_parts)
        remaining = 36 - used_length

        # Can include additional issuing authority info
        optional_data = cls.sanitize_for_mrz("", remaining)
        line1_parts.append(optional_data)

        line1 = "".join(line1_parts)

        # Line 2: Document number, check digit, nationality, date of birth, check digit, sex, expiry, check digit, optional
        line2_parts = []

        # Document number (up to 9 chars)
        doc_number = cls.sanitize_for_mrz(document.document_number, 9)
        line2_parts.append(doc_number)

        # Check digit for document number
        doc_check = cls.compute_check_digit(doc_number.rstrip("<"))
        line2_parts.append(doc_check)

        # Nationality (3 chars)
        nationality = cls.sanitize_for_mrz(personal.nationality, 3)
        line2_parts.append(nationality)

        # Date of birth (6 chars)
        dob = cls.format_date_for_mrz(personal.date_of_birth)
        line2_parts.append(dob)

        # Check digit for date of birth
        dob_check = cls.compute_check_digit(dob)
        line2_parts.append(dob_check)

        # Sex (1 char)
        line2_parts.append(personal.gender.value)

        # Date of expiry (6 chars)
        expiry = cls.format_date_for_mrz(document.date_of_expiry)
        line2_parts.append(expiry)

        # Check digit for expiry date
        expiry_check = cls.compute_check_digit(expiry)
        line2_parts.append(expiry_check)

        # Optional data - remaining space
        used_length = sum(len(part) for part in line2_parts)
        remaining = 36 - used_length

        additional_optional = cls.sanitize_for_mrz("", remaining)
        line2_parts.append(additional_optional)

        line2 = "".join(line2_parts)

        # Line 3: Optional data, name, composite check digit
        line3_parts = []

        # Optional data area (can include visa category, etc.)
        visa_category = cls.sanitize_for_mrz(document.visa_category.value, 15)
        line3_parts.append(visa_category)

        # Name field (surname, given names)
        used_length = len(visa_category) + 1  # +1 for composite check
        name_length = 36 - used_length

        name_field = cls.format_name_for_mrz(personal.surname, personal.given_names, name_length)
        line3_parts.append(name_field)

        # Composite check digit
        composite_data = (
            doc_number.rstrip("<") + doc_check + dob + dob_check + expiry + expiry_check
        )
        composite_check = cls.compute_check_digit(composite_data)
        line3_parts.append(composite_check)

        line3 = "".join(line3_parts)

        # Create MRZ data object
        mrz_data = MRZData(
            type_b_line1=line1,
            type_b_line2=line2,
            type_b_line3=line3,
            check_digit_document=doc_check,
            check_digit_dob=dob_check,
            check_digit_expiry=expiry_check,
            check_digit_composite=composite_check,
        )

        return line1, line2, line3, mrz_data

    @classmethod
    def generate_mrz_for_visa(cls, visa: Visa) -> MRZData:
        """
        Generate appropriate MRZ for visa based on type.

        Args:
            visa: Visa object

        Returns:
            MRZData object with generated MRZ lines
        """
        if visa.document_data.visa_type == VisaType.MRV_TYPE_A:
            _, _, mrz_data = cls.generate_type_a_mrz(visa)
            return mrz_data
        if visa.document_data.visa_type == VisaType.MRV_TYPE_B:
            _, _, _, mrz_data = cls.generate_type_b_mrz(visa)
            return mrz_data
        msg = f"MRZ generation not supported for visa type: {visa.document_data.visa_type}"
        raise ValueError(msg)


class MRZParser:
    """Parser for visa MRZ data with validation."""

    @classmethod
    def parse_type_a_mrz(cls, line1: str, line2: str) -> dict:
        """
        Parse Type A (2-line) MRZ.

        Args:
            line1: First MRZ line
            line2: Second MRZ line

        Returns:
            Dictionary with parsed data
        """
        if len(line1) != 44 or len(line2) != 44:
            msg = "Type A MRZ lines must be exactly 44 characters"
            raise ValueError(msg)

        # Parse line 1
        document_type = line1[0]
        issuing_state = line1[1:4]
        document_number = line1[4:13].rstrip("<")
        doc_check = line1[13]
        optional_data1 = line1[14:44]

        # Parse line 2
        dob = line2[0:6]
        dob_check = line2[6]
        gender = line2[7]
        expiry = line2[8:14]
        expiry_check = line2[14]
        nationality = line2[15:18]
        optional_data2 = line2[18:43]
        composite_check = line2[43]

        return {
            "document_type": document_type,
            "issuing_state": issuing_state,
            "document_number": document_number,
            "nationality": nationality,
            "date_of_birth": dob,
            "gender": gender,
            "date_of_expiry": expiry,
            "check_digits": {
                "document": doc_check,
                "dob": dob_check,
                "expiry": expiry_check,
                "composite": composite_check,
            },
            "optional_data": optional_data1 + optional_data2,
        }

    @classmethod
    def parse_type_b_mrz(cls, line1: str, line2: str, line3: str) -> dict:
        """
        Parse Type B (3-line) MRZ.

        Args:
            line1: First MRZ line
            line2: Second MRZ line
            line3: Third MRZ line

        Returns:
            Dictionary with parsed data
        """
        if len(line1) != 36 or len(line2) != 36 or len(line3) != 36:
            msg = "Type B MRZ lines must be exactly 36 characters"
            raise ValueError(msg)

        # Parse line 1
        document_type = line1[0]
        issuing_state = line1[1:4]
        optional_data1 = line1[4:36]

        # Parse line 2
        document_number = line2[0:9].rstrip("<")
        doc_check = line2[9]
        nationality = line2[10:13]
        dob = line2[13:19]
        dob_check = line2[19]
        gender = line2[20]
        expiry = line2[21:27]
        expiry_check = line2[27]
        optional_data2 = line2[28:36]

        # Parse line 3
        optional_data3 = line3[0:35]
        composite_check = line3[35]

        # Extract name from line 3 (usually at the end)
        name_part = optional_data3.rstrip("<")

        return {
            "document_type": document_type,
            "issuing_state": issuing_state,
            "document_number": document_number,
            "nationality": nationality,
            "date_of_birth": dob,
            "gender": gender,
            "date_of_expiry": expiry,
            "name_field": name_part,
            "check_digits": {
                "document": doc_check,
                "dob": dob_check,
                "expiry": expiry_check,
                "composite": composite_check,
            },
            "optional_data": optional_data1 + optional_data2 + optional_data3,
        }

    @classmethod
    def validate_check_digits(cls, parsed_data: dict) -> dict:
        """
        Validate check digits in parsed MRZ data.

        Args:
            parsed_data: Parsed MRZ data

        Returns:
            Dictionary with validation results
        """
        results = {}

        # Validate document number check digit
        expected_doc_check = MRZGenerator.compute_check_digit(parsed_data["document_number"])
        results["document_valid"] = expected_doc_check == parsed_data["check_digits"]["document"]

        # Validate date of birth check digit
        expected_dob_check = MRZGenerator.compute_check_digit(parsed_data["date_of_birth"])
        results["dob_valid"] = expected_dob_check == parsed_data["check_digits"]["dob"]

        # Validate expiry date check digit
        expected_expiry_check = MRZGenerator.compute_check_digit(parsed_data["date_of_expiry"])
        results["expiry_valid"] = expected_expiry_check == parsed_data["check_digits"]["expiry"]

        # Validate composite check digit
        composite_data = (
            parsed_data["document_number"]
            + parsed_data["check_digits"]["document"]
            + parsed_data["date_of_birth"]
            + parsed_data["check_digits"]["dob"]
            + parsed_data["date_of_expiry"]
            + parsed_data["check_digits"]["expiry"]
        )
        expected_composite_check = MRZGenerator.compute_check_digit(composite_data)
        results["composite_valid"] = (
            expected_composite_check == parsed_data["check_digits"]["composite"]
        )

        # Overall validity
        results["all_valid"] = all(
            [
                results["document_valid"],
                results["dob_valid"],
                results["expiry_valid"],
                results["composite_valid"],
            ]
        )

        return results


class MRZFormatter:
    """Formatter for displaying MRZ data."""

    @classmethod
    def format_for_display(cls, mrz_data: MRZData, visa_type: VisaType) -> str:
        """
        Format MRZ data for human-readable display.

        Args:
            mrz_data: MRZ data object
            visa_type: Type of visa

        Returns:
            Formatted MRZ string
        """
        if visa_type == VisaType.MRV_TYPE_A:
            return f"{mrz_data.type_a_line1}\n{mrz_data.type_a_line2}"
        if visa_type == VisaType.MRV_TYPE_B:
            return f"{mrz_data.type_b_line1}\n{mrz_data.type_b_line2}\n{mrz_data.type_b_line3}"
        return "MRZ not available for this visa type"

    @classmethod
    def format_for_ocr(cls, mrz_data: MRZData, visa_type: VisaType) -> str:
        """
        Format MRZ data for OCR systems (no line breaks).

        Args:
            mrz_data: MRZ data object
            visa_type: Type of visa

        Returns:
            OCR-formatted MRZ string
        """
        if visa_type == VisaType.MRV_TYPE_A:
            return f"{mrz_data.type_a_line1}{mrz_data.type_a_line2}"
        if visa_type == VisaType.MRV_TYPE_B:
            return f"{mrz_data.type_b_line1}{mrz_data.type_b_line2}{mrz_data.type_b_line3}"
        return ""
