"""
Standardized Machine Readable Zone (MRZ) utilities according to ICAO Doc 9303.

This module provides comprehensive MRZ composition and validation utilities
that are consistent across all document types (passports, visas, ID cards).

Key features:
- Doc 9303 compliant check digit calculation (weights [7,3,1], character mapping)
- Standardized name formatting with ASCII transliteration and truncation
- Date validation with leap year support and document-specific policies
- Field truncation and padding with proper filler character handling
- Unified API for all MRZ document types

Character mapping:
- 0-9 → 0-9
- A-Z → 10-35
- < → 0
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from enum import Enum
from typing import ClassVar


class MRZDocumentType(str, Enum):
    """MRZ document types according to Doc 9303."""

    PASSPORT = "P"  # TD3 passport
    VISA_TYPE_A = "V"  # Type A visa (2-line)
    VISA_TYPE_B = "VB"  # Type B visa (3-line)
    ID_CARD_TD1 = "I"  # TD1 ID card
    ID_CARD_TD2 = "ID"  # TD2 ID card
    OTHER = "O"  # Other travel documents


class MRZFieldLength:
    """Standard MRZ field lengths according to Doc 9303."""

    # TD3 (Passport) field lengths
    TD3_LINE_LENGTH = 44
    TD3_NAME_FIELD = 39
    TD3_DOCUMENT_NUMBER = 9
    TD3_PERSONAL_NUMBER = 14

    # Visa Type A field lengths
    VISA_A_LINE_LENGTH = 44
    VISA_A_NAME_FIELD = 31
    VISA_A_DOCUMENT_NUMBER = 9

    # Visa Type B field lengths
    VISA_B_LINE_LENGTH = 36
    VISA_B_NAME_FIELD = 31  # Variable based on other fields
    VISA_B_DOCUMENT_NUMBER = 9

    # TD1 field lengths
    TD1_LINE_LENGTH = 30
    TD1_DOCUMENT_NUMBER = 9
    TD1_NAME_FIELD = 30

    # TD2 field lengths
    TD2_LINE_LENGTH = 36
    TD2_DOCUMENT_NUMBER = 9
    TD2_NAME_FIELD = 36


class MRZStandardizedUtils:
    """Standardized MRZ utilities implementing Doc 9303 specifications."""

    # Character mapping for check digit calculation
    CHARACTER_VALUES: ClassVar[dict[str, int]] = {
        "0": 0,
        "1": 1,
        "2": 2,
        "3": 3,
        "4": 4,
        "5": 5,
        "6": 6,
        "7": 7,
        "8": 8,
        "9": 9,
        "A": 10,
        "B": 11,
        "C": 12,
        "D": 13,
        "E": 14,
        "F": 15,
        "G": 16,
        "H": 17,
        "I": 18,
        "J": 19,
        "K": 20,
        "L": 21,
        "M": 22,
        "N": 23,
        "O": 24,
        "P": 25,
        "Q": 26,
        "R": 27,
        "S": 28,
        "T": 29,
        "U": 30,
        "V": 31,
        "W": 32,
        "X": 33,
        "Y": 34,
        "Z": 35,
        "<": 0,
    }

    # Check digit weights according to Doc 9303
    CHECK_DIGIT_WEIGHTS: ClassVar[list[int]] = [7, 3, 1]

    # Filler character
    FILLER_CHAR = "<"

    # ASCII transliteration mapping for common characters
    TRANSLITERATION_MAP: ClassVar[dict[str, str]] = {
        "À": "A",
        "Á": "A",
        "Â": "A",
        "Ã": "A",
        "Ä": "AE",
        "Å": "AA",
        "Æ": "AE",
        "Ç": "C",
        "È": "E",
        "É": "E",
        "Ê": "E",
        "Ë": "E",
        "Ì": "I",
        "Í": "I",
        "Î": "I",
        "Ï": "I",
        "Ñ": "N",
        "Ò": "O",
        "Ó": "O",
        "Ô": "O",
        "Õ": "O",
        "Ö": "OE",
        "Ø": "OE",
        "Ù": "U",
        "Ú": "U",
        "Û": "U",
        "Ü": "UE",
        "Ý": "Y",
        "Þ": "TH",
        "ß": "SS",
        "à": "A",
        "á": "A",
        "â": "A",
        "ã": "A",
        "ä": "AE",
        "å": "AA",
        "æ": "AE",
        "ç": "C",
        "è": "E",
        "é": "E",
        "ê": "E",
        "ë": "E",
        "ì": "I",
        "í": "I",
        "î": "I",
        "ï": "I",
        "ñ": "N",
        "ò": "O",
        "ó": "O",
        "ô": "O",
        "õ": "O",
        "ö": "OE",
        "ø": "OE",
        "ù": "U",
        "ú": "U",
        "û": "U",
        "ü": "UE",
        "ý": "Y",
        "þ": "TH",
        "ÿ": "Y",
    }

    # Disallowed punctuation characters (stripped from names)
    DISALLOWED_PUNCTUATION: ClassVar[set[str]] = set(".,;:!?'\"()[]{}/-+*&%$#@^~`|\\=_")

    @classmethod
    def compute_check_digit(cls, data: str) -> str:
        """
        Compute check digit according to Doc 9303 specifications.

        Uses character mapping (0-9 → 0-9, A-Z → 10-35, < → 0) and weights [7,3,1].

        Args:
            data: Input string to compute check digit for

        Returns:
            Single character check digit (0-9)
        """
        if not data:
            return "0"

        total = 0
        for i, char in enumerate(data.upper()):
            char_value = cls.CHARACTER_VALUES.get(char, 0)
            weight = cls.CHECK_DIGIT_WEIGHTS[i % 3]
            total += char_value * weight

        return str(total % 10)

    @classmethod
    def validate_check_digit(cls, data: str, check_digit: str) -> bool:
        """
        Validate a check digit against the computed value.

        Args:
            data: Input data
            check_digit: Check digit to validate

        Returns:
            True if valid, False otherwise
        """
        computed = cls.compute_check_digit(data)
        return computed == check_digit

    @classmethod
    def ascii_transliterate(cls, text: str) -> str:
        """
        Convert text to ASCII using Doc 9303 transliteration rules.

        Args:
            text: Input text with potential Unicode characters

        Returns:
            ASCII-only text with proper transliterations
        """
        if not text:
            return ""

        result = ""
        for char in text:
            # Check custom transliteration map first
            if char in cls.TRANSLITERATION_MAP:
                result += cls.TRANSLITERATION_MAP[char]
            else:
                # Try Unicode normalization and decomposition
                normalized = unicodedata.normalize("NFD", char)
                ascii_char = ""
                for c in normalized:
                    if ord(c) < 128:  # ASCII range
                        ascii_char += c

                if ascii_char:
                    result += ascii_char
                elif char.isalpha():
                    # Fallback for other alphabetic characters
                    result += "X"
                # Skip non-alphabetic characters that can't be transliterated

        return result.upper()

    @classmethod
    def format_name_for_mrz(cls, surname: str, given_names: str, max_length: int) -> str:
        """
        Format names for MRZ according to Doc 9303 specifications.

        Format: PRIMARY<<SECONDARY<ADDITIONAL...
        - Uppercase ASCII transliteration
        - Strip disallowed punctuation
        - Deterministic truncation when needed

        Args:
            surname: Primary surname
            given_names: Given names (space-separated)
            max_length: Maximum field length

        Returns:
            Formatted name field with proper separators and padding
        """
        if not surname:
            surname = ""
        if not given_names:
            given_names = ""

        # Clean and transliterate names
        clean_surname = cls._clean_name_component(surname)
        clean_given = cls._clean_name_component(given_names)

        # Split given names
        given_parts = [part for part in clean_given.split() if part]

        # Start with surname
        name_field = clean_surname + "<<" if clean_surname else "<<"

        # Add given names with single < separator
        if given_parts:
            name_field += "<".join(given_parts)

        # Apply deterministic truncation if needed
        if len(name_field) > max_length:
            name_field = cls._truncate_name_field(clean_surname, given_parts, max_length)

        # Pad to full length
        return name_field.ljust(max_length, cls.FILLER_CHAR)

    @classmethod
    def _clean_name_component(cls, name: str) -> str:
        """Clean a name component by removing punctuation and transliterating."""
        if not name:
            return ""

        # Remove disallowed punctuation
        clean_name = ""
        for char in name:
            if char not in cls.DISALLOWED_PUNCTUATION:
                clean_name += char

        # Transliterate to ASCII
        ascii_name = cls.ascii_transliterate(clean_name)

        # Remove extra spaces and convert to uppercase
        return re.sub(r"\s+", " ", ascii_name.strip()).upper()

    @classmethod
    def _truncate_name_field(cls, surname: str, given_parts: list[str], max_length: int) -> str:
        """
        Apply deterministic truncation to name field.

        Truncation priority:
        1. Truncate additional given names from right to left
        2. Truncate primary given name
        3. Truncate surname as last resort
        """
        if not surname:
            # No surname case
            if given_parts:
                available = max_length - 2  # Reserve << space
                given_text = "<".join(given_parts)
                if len(given_text) <= available:
                    return "<<" + given_text

                # Truncate given names
                truncated_given = cls._truncate_given_names(given_parts, available)
                return "<<" + truncated_given
            return "<<".ljust(max_length, cls.FILLER_CHAR)

        # Calculate space needed for surname + separator
        surname_with_sep = surname + "<<"

        if len(surname_with_sep) >= max_length:
            # Surname itself is too long, truncate it
            max_surname_len = max_length - 2
            return surname[:max_surname_len] + "<<"

        # Calculate available space for given names
        available_for_given = max_length - len(surname_with_sep)

        if not given_parts:
            return surname_with_sep.ljust(max_length, cls.FILLER_CHAR)

        # Truncate given names to fit
        given_text = cls._truncate_given_names(given_parts, available_for_given)
        return surname_with_sep + given_text

    @classmethod
    def _truncate_given_names(cls, given_parts: list[str], max_length: int) -> str:
        """Truncate given names to fit within max_length."""
        if not given_parts or max_length <= 0:
            return ""

        # Try to fit all given names
        full_given = "<".join(given_parts)
        if len(full_given) <= max_length:
            return full_given

        # Truncate from right to left
        for i in range(len(given_parts) - 1, 0, -1):
            truncated_parts = given_parts[:i]
            truncated_given = "<".join(truncated_parts)
            if len(truncated_given) <= max_length:
                return truncated_given

        # Last resort: truncate the first given name
        if given_parts:
            first_given = given_parts[0]
            if len(first_given) <= max_length:
                return first_given

            return first_given[:max_length]

        return ""

    @classmethod
    def format_date_for_mrz(cls, date_obj: date) -> str:
        """
        Format date for MRZ in YYMMDD format.

        Args:
            date_obj: Date object to format

        Returns:
            6-character date string in YYMMDD format
        """
        if not date_obj:
            return "000000"

        return date_obj.strftime("%y%m%d")

    @classmethod
    def validate_date_format(cls, date_str: str) -> bool:
        """
        Validate date string is in proper YYMMDD format.

        Args:
            date_str: Date string to validate

        Returns:
            True if valid format, False otherwise
        """
        if not date_str or len(date_str) != 6:
            return False

        if not date_str.isdigit():
            return False

        try:
            year = int(date_str[:2])
            month = int(date_str[2:4])
            day = int(date_str[4:6])

            # Basic range checks
            if month < 1 or month > 12:
                return False
            if day < 1 or day > 31:
                return False

            # Try to create actual date for leap year validation
            # Assume 21st century for years 00-39, 20th century for 40-99
            full_year = 2000 + year if year <= 39 else 1900 + year
            date(full_year, month, day)

        except (ValueError, TypeError):
            return False

        return True

    @classmethod
    def validate_date_policy(
        cls, date_str: str, document_type: MRZDocumentType, is_expiry: bool = False
    ) -> tuple[bool, str]:
        """
        Validate date according to document-specific policies.

        Args:
            date_str: Date string in YYMMDD format
            document_type: Type of document
            is_expiry: True if this is an expiry date

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not cls.validate_date_format(date_str):
            return False, "Invalid date format"

        try:
            year = int(date_str[:2])
            month = int(date_str[2:4])
            day = int(date_str[4:6])

            # Convert to full year
            full_year = 2000 + year if year <= 39 else 1900 + year
            date_obj = date(full_year, month, day)
            today = date.today()

            if is_expiry:
                return cls._validate_expiry_date(date_obj, today, document_type)

            return cls._validate_birth_date(date_obj, today)

        except (ValueError, TypeError) as e:
            return False, f"Date validation error: {e!s}"

    @classmethod
    def _validate_expiry_date(
        cls, date_obj: date, today: date, document_type: MRZDocumentType
    ) -> tuple[bool, str]:
        """Validate expiry date according to document policies."""
        # Check if already expired (with grace period)
        if date_obj < today:
            return False, "Document has expired"

        # Expiry date policies
        if document_type in [MRZDocumentType.PASSPORT]:
            # Passports can have expiry dates up to 10 years in future
            max_future = date(today.year + 10, today.month, today.day)
            if date_obj > max_future:
                return False, "Expiry date too far in future"
        elif document_type in [MRZDocumentType.VISA_TYPE_A, MRZDocumentType.VISA_TYPE_B]:
            # Visas can have expiry dates up to 5 years in future
            max_future = date(today.year + 5, today.month, today.day)
            if date_obj > max_future:
                return False, "Visa expiry date too far in future"

        return True, ""

    @classmethod
    def _validate_birth_date(cls, date_obj: date, today: date) -> tuple[bool, str]:
        """Validate birth date according to general policies."""
        min_birth = date(today.year - 120, today.month, today.day)
        if date_obj < min_birth:
            return False, "Birth date too far in past"
        if date_obj > today:
            return False, "Birth date cannot be in future"

        return True, ""

    @classmethod
    def pad_field(cls, value: str, length: int, filler: str | None = None) -> str:
        """
        Pad field to exact length with proper filler character.

        Args:
            value: Value to pad
            length: Target length
            filler: Filler character (defaults to '<')

        Returns:
            Padded string of exact length
        """
        if filler is None:
            filler = cls.FILLER_CHAR

        if not value:
            return filler * length

        # Truncate if too long
        if len(value) > length:
            value = value[:length]

        # Pad if too short
        return value.ljust(length, filler)

    @classmethod
    def clean_field_for_mrz(cls, value: str, allowed_chars: str | None = None) -> str:
        """
        Clean field value for MRZ by removing invalid characters.

        Args:
            value: Input value
            allowed_chars: Allowed characters (defaults to A-Z, 0-9, <)

        Returns:
            Cleaned string with only allowed characters
        """
        if not value:
            return ""

        if allowed_chars is None:
            allowed_chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<"

        cleaned = ""
        for char in value.upper():
            if char in allowed_chars:
                cleaned += char

        return cleaned

    @classmethod
    def validate_mrz_line_length(cls, line: str, expected_length: int) -> bool:
        """
        Validate MRZ line has correct length.

        Args:
            line: MRZ line to validate
            expected_length: Expected line length

        Returns:
            True if length is correct
        """
        return len(line) == expected_length if line else False

    @classmethod
    def validate_mrz_characters(cls, line: str) -> bool:
        """
        Validate MRZ line contains only allowed characters.

        Args:
            line: MRZ line to validate

        Returns:
            True if all characters are valid
        """
        if not line:
            return False

        allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<")
        return all(char in allowed for char in line.upper())


class MRZCompositeValidator:
    """Validator for composite check digits across different document types."""

    @classmethod
    def validate_td3_composite(
        cls,
        document_number: str,
        doc_check: str,
        birth_date: str,
        birth_check: str,
        expiry_date: str,
        expiry_check: str,
        personal_number: str,
        personal_check: str,
        composite_check: str,
    ) -> bool:
        """Validate TD3 passport composite check digit."""
        # Pad personal number field to 14 characters
        personal_padded = personal_number.ljust(14, "<")

        composite_data = (
            document_number
            + doc_check
            + birth_date
            + birth_check
            + expiry_date
            + expiry_check
            + personal_padded
            + personal_check
        )

        return MRZStandardizedUtils.validate_check_digit(composite_data, composite_check)

    @classmethod
    def validate_visa_composite(
        cls,
        document_number: str,
        doc_check: str,
        birth_date: str,
        birth_check: str,
        expiry_date: str,
        expiry_check: str,
        composite_check: str,
    ) -> bool:
        """Validate visa composite check digit (simpler than TD3)."""
        composite_data = (
            document_number.rstrip("<")
            + doc_check
            + birth_date
            + birth_check
            + expiry_date
            + expiry_check
        )

        return MRZStandardizedUtils.validate_check_digit(composite_data, composite_check)
