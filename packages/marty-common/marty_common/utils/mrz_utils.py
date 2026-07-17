"""
Machine Readable Zone (MRZ) parsing and generation utilities.

Implements MRZ processing according to ICAO Doc 9303 Part 3, Part 4, and Part 5.

Uses Rust bindings from marty_rs for check digit calculation and validation.
"""

import contextlib
import re
from datetime import datetime

from marty_common.crypto_bridge import (
    compute_check_digit as _rust_compute_check_digit,
    validate_check_digit as _rust_validate_check_digit,
)
from marty_common.models.passport import Gender, MRZData


class MRZException(Exception):
    """Exception raised for errors in the MRZ handling."""


class MRZParser:
    """Parser for Machine Readable Zone (MRZ) data according to ICAO Doc 9303."""

    @staticmethod
    def calculate_check_digit(input_string: str) -> str:
        """
        Calculate the check digit as per ICAO Doc 9303 specifications.

        Uses Rust implementation via marty_rs for correctness and performance.

        Args:
            input_string: String to calculate check digit for

        Returns:
            Single character check digit
        """
        return _rust_compute_check_digit(input_string)

    @staticmethod
    def validate_check_digit(input_string: str, check_digit: str) -> bool:
        """
        Validate a check digit against an input string.

        Uses Rust implementation via marty_rs for correctness and performance.

        Args:
            input_string: String to validate check digit for
            check_digit: The check digit to validate

        Returns:
            True if valid, False otherwise
        """
        return _rust_validate_check_digit(input_string, check_digit)

    @staticmethod
    def clean_name(name: str) -> str:
        """
        Clean a name by converting it to uppercase and replacing invalid characters with '<'.

        Args:
            name: Name to clean

        Returns:
            Cleaned name suitable for MRZ
        """
        # Remove diacritical marks and special characters
        # Only allow A-Z, spaces and hyphens
        # Replace spaces with '<'
        return re.sub(r"[^A-Z\-]", "<", name.upper().replace(" ", "<"))

    @staticmethod
    def _split_lines(mrz: str) -> list[str]:
        """Split MRZ payload into two TD3 lines."""

        raw = mrz.strip()

        if "\n" in raw:
            lines = raw.split("\n")
        elif len(raw) == 88:
            lines = [raw[:44], raw[44:]]
        else:
            lines = [raw]

        return lines

    @classmethod
    def _normalize_whitespace(cls, value: str) -> str:
        parts = [segment for segment in value.replace("<", " ").split() if segment]
        return " ".join(parts)

    @classmethod
    def _validate_date(cls, date_value: str, label: str) -> None:
        if not date_value.isdigit() or len(date_value) != 6:
            msg = f"{label} must consist of six digits"
            raise MRZException(msg)

        try:
            datetime.strptime(date_value, "%y%m%d")
        except ValueError as exc:
            msg = f"Invalid {label} value"
            raise MRZException(msg) from exc

    @classmethod
    def parse_td3_mrz(cls, mrz: str) -> MRZData:
        """
        Parse a TD3 format MRZ string (passport).

        Args:
            mrz: The MRZ string to parse (typically 2 lines of 44 characters)

        Returns:
            MRZData object containing the parsed data

        Raises:
            MRZException: If the MRZ format is invalid
        """
        lines = cls._split_lines(mrz)

        if len(lines) != 2:
            msg = "TD3 MRZ must have exactly 2 lines"
            raise MRZException(msg)

        if len(lines[0]) != 44 or len(lines[1]) != 44:
            msg = "TD3 MRZ lines must be exactly 44 characters long"
            raise MRZException(msg)

        # First line: P<ISSUING_COUNTRY<SURNAME<<GIVEN_NAMES
        line1 = lines[0]
        document_type = line1[0]
        if document_type != "P":
            msg = f"Expected document type 'P', found '{document_type}'"
            raise MRZException(msg)

        issuing_country = line1[2:5]

        name_part = line1[5:]
        name_parts = name_part.split("<<", 1)
        surname = cls._normalize_whitespace(name_parts[0])
        given_section = name_parts[1] if len(name_parts) > 1 else ""
        given_names = cls._normalize_whitespace(given_section)

        # Second line: DOCUMENT_NUMBER<CHECK_DIGIT<NATIONALITY<DOB<CHECK_DIGIT<GENDER<DOE<CHECK_DIGIT<PERSONAL_NUMBER<CHECK_DIGIT<COMPOSITE_CHECK_DIGIT
        line2 = lines[1]
        # For TD3, document number field is 9 chars and may contain fillers '<'.
        # Check digit is computed over the field INCLUDING fillers, so do not strip for check.
        document_number_field = line2[0:9]
        doc_check_digit = line2[9]
        if not cls.validate_check_digit(document_number_field, doc_check_digit):
            msg = (
                f"Invalid document number check digit: {document_number_field} -> {doc_check_digit}"
            )
            raise MRZException(msg)

        document_number = document_number_field.replace("<", "")

        nationality = line2[10:13]

        date_of_birth = line2[13:19]
        dob_check_digit = line2[19]

        cls._validate_date(date_of_birth, "date of birth")

        if not cls.validate_check_digit(date_of_birth, dob_check_digit):
            msg = f"Invalid date of birth check digit: {date_of_birth} -> {dob_check_digit}"
            raise MRZException(msg)

        gender_code = line2[20]
        if gender_code == "M":
            gender = Gender.MALE
        elif gender_code == "F":
            gender = Gender.FEMALE
        else:
            gender = Gender.UNSPECIFIED

        date_of_expiry = line2[21:27]
        doe_check_digit = line2[27]

        cls._validate_date(date_of_expiry, "date of expiry")

        if not cls.validate_check_digit(date_of_expiry, doe_check_digit):
            msg = f"Invalid date of expiry check digit: {date_of_expiry} -> {doe_check_digit}"
            raise MRZException(msg)

        personal_number_field = line2[28:42]
        personal_number_check_digit = line2[42]
        # Validate personal number using the field with fillers, but treat all '<' as zero value
        # An empty field (all '<') will validate against its computed digit (often '0').
        if not cls.validate_check_digit(personal_number_field, personal_number_check_digit):
            msg = f"Invalid personal number check digit: {personal_number_field} -> {personal_number_check_digit}"
            raise MRZException(msg)
        personal_number = personal_number_field.replace("<", "") or None

        # Validation of composite check digit
        composite_check_digit = line2[43]
        composite_string = (
            document_number_field
            + doc_check_digit
            + date_of_birth
            + dob_check_digit
            + date_of_expiry
            + doe_check_digit
            + personal_number_field
            + personal_number_check_digit
        )

        if not cls.validate_check_digit(composite_string, composite_check_digit):
            msg = "Invalid composite check digit"
            raise MRZException(msg)

        return MRZData(
            document_type=document_type,
            issuing_country=issuing_country,
            document_number=document_number,
            surname=surname,
            given_names=given_names,
            nationality=nationality,
            date_of_birth=date_of_birth,
            gender=gender,
            date_of_expiry=date_of_expiry,
            personal_number=personal_number,
        )

    @classmethod
    def parse_td2_mrz(cls, mrz: str) -> MRZData:
        """
        Parse a TD-2 format MRZ string per ICAO Doc 9303 Part 6.

        TD-2 format consists of 2 lines of 36 characters each:
        Line 1: Doc type (2) + Issuing state (3) + Doc number (9) + Check (1) +
                Birth date (6) + Check (1) + Sex (1) + Expiry date (6) + Check (1) +
                Nationality (3) + Optional data (2) + Composite check (1)
        Line 2: Name field (36) - Primary identifier << Secondary identifier

        Args:
            mrz: The MRZ string to parse (2 lines of 36 characters)

        Returns:
            MRZData object containing the parsed data

        Raises:
            MRZException: If the MRZ format is invalid
        """
        lines = cls._split_lines(mrz)

        if len(lines) != 2:
            msg = "TD-2 MRZ must have exactly 2 lines"
            raise MRZException(msg)

        if not all(len(line) == 36 for line in lines):
            msg = "TD-2 MRZ lines must be exactly 36 characters long"
            raise MRZException(msg)

        # Line 1: Document data
        line1 = lines[0]

        # Parse Line 1 components
        document_type = line1[0:2].rstrip("<")
        issuing_country = line1[2:5]
        document_number_field = line1[5:14]
        doc_check_digit = line1[14]
        birth_date = line1[15:21]
        birth_check_digit = line1[21]
        gender_code = line1[22]
        expiry_date = line1[23:29]
        expiry_check_digit = line1[29]
        nationality = line1[30:33]
        optional_data_field = line1[33:35]
        composite_check_digit = line1[35]

        # Validate document number check digit
        if not cls.validate_check_digit(document_number_field, doc_check_digit):
            msg = (
                f"Invalid document number check digit: {document_number_field} -> {doc_check_digit}"
            )
            raise MRZException(msg)

        document_number = document_number_field.replace("<", "")

        # Validate dates
        cls._validate_date(birth_date, "date of birth")
        cls._validate_date(expiry_date, "date of expiry")

        # Validate date check digits
        if not cls.validate_check_digit(birth_date, birth_check_digit):
            msg = f"Invalid birth date check digit: {birth_date} -> {birth_check_digit}"
            raise MRZException(msg)

        if not cls.validate_check_digit(expiry_date, expiry_check_digit):
            msg = f"Invalid expiry date check digit: {expiry_date} -> {expiry_check_digit}"
            raise MRZException(msg)

        # Parse gender
        if gender_code == "M":
            gender = Gender.MALE
        elif gender_code == "F":
            gender = Gender.FEMALE
        else:
            gender = Gender.UNSPECIFIED

        # Validate composite check digit
        composite_string = (
            document_number_field
            + doc_check_digit
            + birth_date
            + birth_check_digit
            + expiry_date
            + expiry_check_digit
            + optional_data_field
        )

        if not cls.validate_check_digit(composite_string, composite_check_digit):
            msg = "Invalid composite check digit"
            raise MRZException(msg)

        # Line 2: Name field (36 characters)
        line2 = lines[1]
        name_field = line2.rstrip("<")

        # Parse names per ICAO Part 6 - primary identifier precedence
        if "<<" in name_field:
            name_parts = name_field.split("<<", 1)
            surname = cls._normalize_whitespace(name_parts[0])
            given_names = cls._normalize_whitespace(name_parts[1]) if len(name_parts) > 1 else ""
        else:
            # If no separator, treat entire field as surname
            surname = cls._normalize_whitespace(name_field)
            given_names = ""

        # Extract optional data
        optional_data = optional_data_field.replace("<", "") or None

        return MRZData(
            document_type=document_type,
            issuing_country=issuing_country,
            document_number=document_number,
            surname=surname,
            given_names=given_names,
            nationality=nationality,
            date_of_birth=birth_date,
            gender=gender,
            date_of_expiry=expiry_date,
            personal_number=optional_data,
        )

    @classmethod
    def parse_mrz(cls, mrz: str) -> MRZData:
        """
        Parse any type of MRZ string. Supports TD3 (passport) and TD1 (ID card) formats.

        Args:
            mrz: The MRZ string to parse

        Returns:
            MRZData object containing the parsed data

        Raises:
            MRZException: If the MRZ format is invalid or unsupported
        """
        lines = cls._split_lines(mrz)

        # TD3 format: 2 lines of 44 characters (passport)
        if len(lines) == 2 and all(len(line) == 44 for line in lines):
            return cls.parse_td3_mrz("\n".join(lines))

        # TD2 format: 2 lines of 36 characters (ID card per ICAO Part 6)
        if len(lines) == 2 and all(len(line) == 36 for line in lines):
            return cls.parse_td2_mrz("\n".join(lines))

        # TD1 format: 3 lines of 30 characters (ID card, including CMC)
        if len(lines) == 3 and all(len(line) == 30 for line in lines):
            return cls.parse_td1_mrz("\n".join(lines))

        msg = f"Unsupported MRZ format: {len(lines)} lines with lengths {[len(line) for line in lines]}"
        raise MRZException(msg)

    @classmethod
    def parse_td1_mrz(cls, mrz: str) -> MRZData:
        """
        Parse a TD1 format MRZ string (ID card format, including CMC).

        TD1 format consists of 3 lines of 30 characters each:
        Line 1: IUTOERICS<<<<<<<<<<<<<<<<<
        Line 2: D231458907UTO6908061F9406235
        Line 3: <<<<<<<<<<<<<<<<ERIKSSON<<ANNA<

        Args:
            mrz: The MRZ string to parse (3 lines of 30 characters)

        Returns:
            MRZData object containing the parsed data

        Raises:
            MRZException: If the MRZ format is invalid
        """
        lines = cls._split_lines(mrz)

        if len(lines) != 3:
            msg = "TD1 MRZ must have exactly 3 lines"
            raise MRZException(msg)

        if not all(len(line) == 30 for line in lines):
            msg = "TD1 MRZ lines must be exactly 30 characters long"
            raise MRZException(msg)

        # Line 1: DOCUMENT_TYPE + ISSUING_COUNTRY + DOCUMENT_NUMBER + OPTIONAL_DATA
        line1 = lines[0]
        document_type = line1[0]
        issuing_country = line1[1:4]
        document_number_part1 = line1[4:14]  # First part of document number
        optional_data_line1 = line1[14:30]  # Optional data on line 1

        # Line 2: DOCUMENT_NUMBER_PART2 + CHECK_DIGIT + NATIONALITY + DOB + CHECK + GENDER + DOE + CHECK + OPTIONAL
        line2 = lines[1]
        document_number_part2 = line2[0:5]  # Continuation of document number
        doc_check_digit = line2[5]
        nationality = line2[6:9]
        date_of_birth = line2[9:15]
        dob_check_digit = line2[15]
        gender_char = line2[16]
        date_of_expiry = line2[17:23]
        doe_check_digit = line2[23]
        optional_data_line2 = line2[24:30]  # Optional data on line 2

        # Line 3: OPTIONAL_DATA + SURNAME + GIVEN_NAMES
        line3 = lines[2]
        optional_data_line3 = line3[0:14]  # Optional data on line 3
        surname_given = line3[14:30]  # Surname and given names

        # Construct full document number from parts
        full_doc_number = (document_number_part1 + document_number_part2).rstrip("<")

        # Validate document number check digit
        doc_number_for_check = (document_number_part1 + document_number_part2).ljust(15, "<")[:15]
        if not cls.validate_check_digit(doc_number_for_check, doc_check_digit):
            msg = (
                f"Invalid document number check digit: {doc_number_for_check} -> {doc_check_digit}"
            )
            raise MRZException(msg)

        # Validate dates
        cls._validate_date(date_of_birth, "date of birth")
        cls._validate_date(date_of_expiry, "date of expiry")

        # Validate date check digits
        if not cls.validate_check_digit(date_of_birth, dob_check_digit):
            msg = f"Invalid date of birth check digit: {date_of_birth} -> {dob_check_digit}"
            raise MRZException(msg)

        if not cls.validate_check_digit(date_of_expiry, doe_check_digit):
            msg = f"Invalid date of expiry check digit: {date_of_expiry} -> {doe_check_digit}"
            raise MRZException(msg)

        # Parse gender
        if gender_char == "M":
            gender = Gender.MALE
        elif gender_char == "F":
            gender = Gender.FEMALE
        else:
            gender = Gender.UNSPECIFIED

        # Parse names from line 3 (similar to TD3 format)
        name_part = surname_given.replace("<", " ").strip()
        # Look for double space separator between surname and given names
        if "  " in name_part:
            name_parts = name_part.split("  ", 1)
            surname = name_parts[0].strip()
            given_names = name_parts[1].strip() if len(name_parts) > 1 else ""
        else:
            # Fallback: assume all is surname if no clear separator
            surname = name_part.strip()
            given_names = ""

        # Clean up names
        surname = cls._normalize_whitespace(surname)
        given_names = cls._normalize_whitespace(given_names)

        # Collect optional data
        optional_data_parts = [
            optional_data_line1.rstrip("<"),
            optional_data_line2.rstrip("<"),
            optional_data_line3.rstrip("<"),
        ]
        optional_data = "".join(part for part in optional_data_parts if part)
        personal_number = optional_data if optional_data else None

        return MRZData(
            document_type=document_type,
            issuing_country=issuing_country,
            document_number=full_doc_number,
            surname=surname,
            given_names=given_names,
            nationality=nationality,
            date_of_birth=date_of_birth,
            gender=gender,
            date_of_expiry=date_of_expiry,
            personal_number=personal_number,
        )


class MRZFormatter:
    """Formatter for Machine Readable Zone (MRZ) data according to ICAO Doc 9303."""

    @staticmethod
    def format_name(name: str, max_length: int) -> str:
        """
        Format a name for MRZ by converting to uppercase and replacing spaces with '<'.

        Args:
            name: Name to format
            max_length: Maximum allowed length

        Returns:
            Formatted name
        """
        cleaned_name = MRZParser.clean_name(name)
        if len(cleaned_name) > max_length:
            return cleaned_name[:max_length]
        return cleaned_name

    @staticmethod
    def format_document_number(number: str, total_length: int = 9) -> str:
        """
        Format a document number for MRZ.

        Args:
            number: Document number to format
            total_length: Total length including filler characters

        Returns:
            Formatted document number
        """
        # Keep only alphanumeric characters and uppercase
        cleaned_number = re.sub(r"[^A-Z0-9]", "", number.upper())

        # Pad with '<' if shorter than total_length
        if len(cleaned_number) < total_length:
            return cleaned_number + "<" * (total_length - len(cleaned_number))

        # Truncate if longer
        return cleaned_number[:total_length]

    @staticmethod
    def generate_td3_mrz(data: MRZData) -> str:
        """
        Generate a TD3 format MRZ string (passport).

        Args:
            data: MRZData object containing the passport data

        Returns:
            Formatted MRZ string
        """
        # First line
        line1 = data.document_type
        line1 += "<"  # Filler
        line1 += data.issuing_country.upper()

        surname = MRZParser.clean_name(data.surname)
        given_names = MRZParser.clean_name(data.given_names)

        line1 += surname + "<<" + given_names
        line1 = line1[:44].ljust(44, "<")

        # Second line
        document_number_formatted = MRZFormatter.format_document_number(data.document_number)
        document_check_digit = MRZParser.calculate_check_digit(document_number_formatted)

        line2 = document_number_formatted + document_check_digit
        line2 += data.nationality.upper()

        dob_check_digit = MRZParser.calculate_check_digit(data.date_of_birth)
        line2 += data.date_of_birth + dob_check_digit

        line2 += data.gender.value

        doe_check_digit = MRZParser.calculate_check_digit(data.date_of_expiry)
        line2 += data.date_of_expiry + doe_check_digit

        # Personal number with check digit
        personal_number_raw = (data.personal_number or "").upper()
        personal_number_clean = re.sub(r"[^A-Z0-9<]", "", personal_number_raw)
        personal_number_formatted = personal_number_clean[:14].ljust(14, "<")
        personal_number_check_digit = MRZParser.calculate_check_digit(personal_number_formatted)

        line2 += personal_number_formatted + personal_number_check_digit

        # Calculate composite check digit
        composite_string = (
            document_number_formatted
            + document_check_digit
            + data.date_of_birth
            + dob_check_digit
            + data.date_of_expiry
            + doe_check_digit
            + personal_number_formatted
            + personal_number_check_digit
        )
        composite_check_digit = MRZParser.calculate_check_digit(composite_string)

        line2 += composite_check_digit

        return line1 + "\n" + line2

    @staticmethod
    def generate_td1_mrz(data) -> str:
        """
        Generate a TD1 format MRZ string (ID card format, including CMC).

        TD1 format consists of 3 lines of 30 characters each:
        Line 1: Document type + Issuing country + Document number + Optional data
        Line 2: Document number cont. + Check + Nationality + DOB + Check + Gender + DOE + Check + Optional
        Line 3: Optional data + Surname + Given names

        Args:
            data: MRZData or CMCTD1MRZData object containing the document data

        Returns:
            Formatted TD1 MRZ string (3 lines)
        """
        # Import here to avoid circular dependency
        with contextlib.suppress(ImportError):
            pass

        # Extract values with proper defaults
        document_type = getattr(data, "document_type", "I")
        issuing_country = getattr(data, "issuing_country", "").upper()[:3]
        document_number = getattr(data, "document_number", "")
        nationality = getattr(data, "nationality", "").upper()[:3]
        date_of_birth = getattr(data, "date_of_birth", "")
        gender = getattr(data, "gender", "")
        date_of_expiry = getattr(data, "date_of_expiry", "")
        optional_data = getattr(data, "optional_data", "") or ""

        # Format document number (max 14 characters across lines)
        doc_number_clean = re.sub(r"[^A-Z0-9]", "", document_number.upper())[:14]
        doc_number_line1 = doc_number_clean[:10].ljust(10, "<")
        doc_number_line2 = doc_number_clean[10:].ljust(5, "<")

        # Calculate check digit for full document number
        full_doc_for_check = (doc_number_line1 + doc_number_line2).ljust(15, "<")[:15]
        doc_check_digit = MRZParser.calculate_check_digit(full_doc_for_check)

        # Line 1: Document type + Issuing country + Document number part 1 + Optional data
        line1 = document_type + issuing_country + doc_number_line1
        optional_line1 = optional_data[:16].ljust(16, "<")  # Fill remaining space
        line1 += optional_line1
        line1 = line1[:30].ljust(30, "<")

        # Line 2: Document number part 2 + Check + Nationality + DOB + Check + Gender + DOE + Check + Optional
        dob_check = MRZParser.calculate_check_digit(date_of_birth)
        doe_check = MRZParser.calculate_check_digit(date_of_expiry)

        gender_char = (
            gender.value if hasattr(gender, "value") else str(gender)[:1] if gender else "X"
        )

        line2 = (
            doc_number_line2
            + doc_check_digit
            + nationality
            + date_of_birth
            + dob_check
            + gender_char
            + date_of_expiry
            + doe_check
        )

        # Fill remaining space on line 2 with optional data or fillers
        remaining_space = 30 - len(line2)
        optional_line2 = optional_data[16 : 16 + remaining_space].ljust(remaining_space, "<")
        line2 += optional_line2
        line2 = line2[:30]

        # Line 3: Optional data + Surname + Given names
        surname = MRZParser.clean_name(getattr(data, "surname", ""))
        given_names = MRZParser.clean_name(getattr(data, "given_names", ""))

        # Reserve 14 chars for optional data, 16 for names
        optional_line3 = optional_data[16 + remaining_space :].ljust(14, "<")[:14]
        line3 = optional_line3

        # Add surname and given names
        names_space = 30 - len(line3)  # Remaining space for names
        if surname and given_names:
            name_combo = surname + "<<" + given_names
        elif surname:
            name_combo = surname
        else:
            name_combo = given_names

        name_combo = name_combo[:names_space].ljust(names_space, "<")
        line3 += name_combo
        line3 = line3[:30]

        return line1 + "\n" + line2 + "\n" + line3
