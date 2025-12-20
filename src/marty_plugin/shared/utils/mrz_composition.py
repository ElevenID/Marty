"""
Standardized MRZ composition classes for different document types.

This module provides comprehensive MRZ composition utilities for various
document types according to ICAO Doc 9303 specifications:

- TD3 (Passport) MRZ generation
- Visa Type A (2-line) MRZ generation
- Visa Type B (3-line) MRZ generation
- TD1/TD2 ID card MRZ generation

All classes use the standardized utilities for consistent behavior across
document types and ensure compliance with Doc 9303 protocols.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date

from .mrz_standardized import MRZDocumentType, MRZFieldLength, MRZStandardizedUtils


@dataclass
class MRZPersonalData:
    """Personal data for MRZ generation."""

    surname: str
    given_names: str
    nationality: str
    date_of_birth: date
    gender: str  # M, F, or X


@dataclass
class MRZDocumentData:
    """Document data for MRZ generation."""

    document_type: str
    issuing_country: str
    document_number: str
    date_of_expiry: date
    personal_number: str | None = None
    optional_data: str | None = None


@dataclass
class MRZCompositionResult:
    """Result of MRZ composition with all generated lines and check digits."""

    line1: str
    line2: str
    line3: str | None = None

    # Individual check digits
    document_check: str = ""
    birth_check: str = ""
    expiry_check: str = ""
    personal_check: str = ""
    optional_check: str = ""
    composite_check: str = ""

    # Validation status
    is_valid: bool = True
    validation_errors: list[str] = None

    def __post_init__(self):
        if self.validation_errors is None:
            self.validation_errors = []


class BaseMRZComposer(ABC):
    """Abstract base class for MRZ composition."""

    def __init__(self) -> None:
        self.utils = MRZStandardizedUtils()

    @abstractmethod
    def compose_mrz(
        self, personal_data: MRZPersonalData, document_data: MRZDocumentData
    ) -> MRZCompositionResult:
        """Compose MRZ lines for the specific document type."""

    @abstractmethod
    def get_document_type(self) -> MRZDocumentType:
        """Get the document type this composer handles."""

    def _format_date(self, date_obj: date) -> str:
        """Format date for MRZ."""
        return self.utils.format_date_for_mrz(date_obj)

    def _compute_check_digit(self, data: str) -> str:
        """Compute check digit for data."""
        return self.utils.compute_check_digit(data)

    def _validate_dates(
        self, personal_data: MRZPersonalData, document_data: MRZDocumentData
    ) -> list[str]:
        """Validate dates according to document policies."""
        errors = []

        # Validate birth date
        birth_str = self._format_date(personal_data.date_of_birth)
        birth_valid, birth_error = self.utils.validate_date_policy(
            birth_str, self.get_document_type(), is_expiry=False
        )
        if not birth_valid:
            errors.append(f"Birth date error: {birth_error}")

        # Validate expiry date
        expiry_str = self._format_date(document_data.date_of_expiry)
        expiry_valid, expiry_error = self.utils.validate_date_policy(
            expiry_str, self.get_document_type(), is_expiry=True
        )
        if not expiry_valid:
            errors.append(f"Expiry date error: {expiry_error}")

        return errors


class TD3PassportMRZComposer(BaseMRZComposer):
    """MRZ composer for TD3 passports according to Doc 9303 Part 4."""

    def get_document_type(self) -> MRZDocumentType:
        return MRZDocumentType.PASSPORT

    def compose_mrz(
        self, personal_data: MRZPersonalData, document_data: MRZDocumentData
    ) -> MRZCompositionResult:
        """
        Compose TD3 passport MRZ (2 lines, 44 characters each).

        Line 1: P<ISSUINGCOUNTRY<LASTNAME<<FIRSTNAME<MIDDLENAME<<<<<<<
        Line 2: DOCUMENTNUMBER<CDATEOFBIRTH<CSEX<DATEOFEXPIRY<CPERSONALNUMBER<<<<<<<<<<<<COMPOSITEC
        """
        errors = self._validate_dates(personal_data, document_data)

        # Line 1: Document type + issuing country + name
        line1_parts = []

        # Document type
        line1_parts.append(document_data.document_type or "P")

        # Issuing country (3 characters)
        issuing_country = self.utils.clean_field_for_mrz(document_data.issuing_country or "")
        line1_parts.append(self.utils.pad_field(issuing_country, 3))

        # Name field (39 characters)
        name_field = self.utils.format_name_for_mrz(
            personal_data.surname, personal_data.given_names, MRZFieldLength.TD3_NAME_FIELD
        )
        line1_parts.append(name_field)

        line1 = "".join(line1_parts)

        # Line 2: Document number + check + nationality + birth + check + gender + expiry + check + personal + check + composite
        line2_parts = []

        # Document number (9 characters) + check digit
        doc_number = self.utils.clean_field_for_mrz(document_data.document_number or "")
        doc_number_padded = self.utils.pad_field(doc_number, MRZFieldLength.TD3_DOCUMENT_NUMBER)
        doc_check = self._compute_check_digit(doc_number_padded)
        line2_parts.extend([doc_number_padded, doc_check])

        # Nationality (3 characters)
        nationality = self.utils.clean_field_for_mrz(personal_data.nationality)
        line2_parts.append(self.utils.pad_field(nationality, 3))

        # Date of birth (6 characters) + check digit
        birth_date = self._format_date(personal_data.date_of_birth)
        birth_check = self._compute_check_digit(birth_date)
        line2_parts.extend([birth_date, birth_check])

        # Gender (1 character)
        gender = personal_data.gender.upper() if personal_data.gender else "X"
        line2_parts.append(gender)

        # Date of expiry (6 characters) + check digit
        expiry_date = self._format_date(document_data.date_of_expiry)
        expiry_check = self._compute_check_digit(expiry_date)
        line2_parts.extend([expiry_date, expiry_check])

        # Personal number (14 characters) + check digit
        personal_number = self.utils.clean_field_for_mrz(document_data.personal_number or "")
        personal_number_padded = self.utils.pad_field(
            personal_number, MRZFieldLength.TD3_PERSONAL_NUMBER
        )
        personal_check = self._compute_check_digit(personal_number_padded)
        line2_parts.extend([personal_number_padded, personal_check])

        # Composite check digit
        composite_data = (
            doc_number_padded
            + doc_check
            + birth_date
            + birth_check
            + expiry_date
            + expiry_check
            + personal_number_padded
            + personal_check
        )
        composite_check = self._compute_check_digit(composite_data)
        line2_parts.append(composite_check)

        line2 = "".join(line2_parts)

        # Validate line lengths
        if len(line1) != MRZFieldLength.TD3_LINE_LENGTH:
            errors.append(
                f"Line 1 length incorrect: {len(line1)} != {MRZFieldLength.TD3_LINE_LENGTH}"
            )
        if len(line2) != MRZFieldLength.TD3_LINE_LENGTH:
            errors.append(
                f"Line 2 length incorrect: {len(line2)} != {MRZFieldLength.TD3_LINE_LENGTH}"
            )

        return MRZCompositionResult(
            line1=line1,
            line2=line2,
            document_check=doc_check,
            birth_check=birth_check,
            expiry_check=expiry_check,
            personal_check=personal_check,
            composite_check=composite_check,
            is_valid=len(errors) == 0,
            validation_errors=errors,
        )


class VisaTypeAMRZComposer(BaseMRZComposer):
    """MRZ composer for Type A visas according to Doc 9303 Part 7."""

    def get_document_type(self) -> MRZDocumentType:
        return MRZDocumentType.VISA_TYPE_A

    def compose_mrz(
        self, personal_data: MRZPersonalData, document_data: MRZDocumentData
    ) -> MRZCompositionResult:
        """
        Compose Type A visa MRZ (2 lines, 44 characters each).

        Line 1: V<ISSUINGCOUNTRY<LASTNAME<<FIRSTNAME<MIDDLENAME<<<<<<<
        Line 2: DOCUMENTNUMBER<CDATEOFBIRTH<CSEX<DATEOFEXPIRY<COPTIONALDATA<<COMPOSITEC
        """
        errors = self._validate_dates(personal_data, document_data)

        # Line 1: Document type + issuing country + name
        line1_parts = []

        # Document type
        line1_parts.append("V")

        # Issuing country (3 characters)
        issuing_country = self.utils.clean_field_for_mrz(document_data.issuing_country or "")
        line1_parts.append(self.utils.pad_field(issuing_country, 3))

        # Name field (39 characters)
        name_field = self.utils.format_name_for_mrz(
            personal_data.surname,
            personal_data.given_names,
            39,  # Same as TD3
        )
        line1_parts.append(name_field)

        line1 = "".join(line1_parts)

        # Line 2: Document number + check + nationality + birth + check + gender + expiry + check + optional + composite
        line2_parts = []

        # Document number (9 characters) + check digit
        doc_number = self.utils.clean_field_for_mrz(document_data.document_number or "")
        doc_number_padded = self.utils.pad_field(doc_number, 9)
        doc_check = self._compute_check_digit(doc_number_padded)
        line2_parts.extend([doc_number_padded, doc_check])

        # Nationality (3 characters)
        nationality = self.utils.clean_field_for_mrz(personal_data.nationality)
        line2_parts.append(self.utils.pad_field(nationality, 3))

        # Date of birth (6 characters) + check digit
        birth_date = self._format_date(personal_data.date_of_birth)
        birth_check = self._compute_check_digit(birth_date)
        line2_parts.extend([birth_date, birth_check])

        # Gender (1 character)
        gender = personal_data.gender.upper() if personal_data.gender else "X"
        line2_parts.append(gender)

        # Date of expiry (6 characters) + check digit
        expiry_date = self._format_date(document_data.date_of_expiry)
        expiry_check = self._compute_check_digit(expiry_date)
        line2_parts.extend([expiry_date, expiry_check])

        # Optional data (16 characters) + composite check
        optional_data = self.utils.clean_field_for_mrz(document_data.optional_data or "")
        optional_data_padded = self.utils.pad_field(optional_data, 15)  # 15 + 1 composite = 16

        # Composite check digit
        composite_data = (
            doc_number.rstrip("<")
            + doc_check
            + birth_date
            + birth_check
            + expiry_date
            + expiry_check
        )
        composite_check = self._compute_check_digit(composite_data)

        line2_parts.extend([optional_data_padded, composite_check])

        line2 = "".join(line2_parts)

        # Validate line lengths
        if len(line1) != MRZFieldLength.VISA_A_LINE_LENGTH:
            errors.append(
                f"Line 1 length incorrect: {len(line1)} != {MRZFieldLength.VISA_A_LINE_LENGTH}"
            )
        if len(line2) != MRZFieldLength.VISA_A_LINE_LENGTH:
            errors.append(
                f"Line 2 length incorrect: {len(line2)} != {MRZFieldLength.VISA_A_LINE_LENGTH}"
            )

        return MRZCompositionResult(
            line1=line1,
            line2=line2,
            document_check=doc_check,
            birth_check=birth_check,
            expiry_check=expiry_check,
            composite_check=composite_check,
            is_valid=len(errors) == 0,
            validation_errors=errors,
        )


class VisaTypeBMRZComposer(BaseMRZComposer):
    """MRZ composer for Type B visas according to Doc 9303 Part 7."""

    def get_document_type(self) -> MRZDocumentType:
        return MRZDocumentType.VISA_TYPE_B

    def compose_mrz(
        self, personal_data: MRZPersonalData, document_data: MRZDocumentData
    ) -> MRZCompositionResult:
        """
        Compose Type B visa MRZ (3 lines, 36 characters each).

        Line 1: V<ISSUINGCOUNTRY<DOCUMENTNUMBER<<<<<<<<<<
        Line 2: DATEOFBIRTH<CDATEOFEXPIRY<CSEX<NATIONALITY<OPTIONALDATA<<
        Line 3: LASTNAME<<FIRSTNAME<MIDDLENAME<VISACATEGORY<COMPOSITEC
        """
        errors = self._validate_dates(personal_data, document_data)

        # Line 1: Document type + issuing country + document number
        line1_parts = []

        # Document type + issuing country
        line1_parts.append("V<")
        issuing_country = self.utils.clean_field_for_mrz(document_data.issuing_country or "")
        line1_parts.append(self.utils.pad_field(issuing_country, 3))
        line1_parts.append("<")

        # Document number (remaining space)
        doc_number = self.utils.clean_field_for_mrz(document_data.document_number or "")
        remaining_space = 36 - len("".join(line1_parts))
        doc_number_padded = self.utils.pad_field(doc_number, remaining_space)
        line1_parts.append(doc_number_padded)

        line1 = "".join(line1_parts)

        # Line 2: Birth + check + expiry + check + gender + nationality + optional
        line2_parts = []

        # Date of birth (6 characters) + check digit
        birth_date = self._format_date(personal_data.date_of_birth)
        birth_check = self._compute_check_digit(birth_date)
        line2_parts.extend([birth_date, birth_check])

        # Date of expiry (6 characters) + check digit
        expiry_date = self._format_date(document_data.date_of_expiry)
        expiry_check = self._compute_check_digit(expiry_date)
        line2_parts.extend([expiry_date, expiry_check])

        # Gender (1 character)
        gender = personal_data.gender.upper() if personal_data.gender else "X"
        line2_parts.append(gender)

        # Nationality (3 characters)
        nationality = self.utils.clean_field_for_mrz(personal_data.nationality)
        line2_parts.append(self.utils.pad_field(nationality, 3))

        # Optional data (remaining space)
        used_space = len("".join(line2_parts))
        remaining_space = 36 - used_space
        optional_data = self.utils.clean_field_for_mrz(document_data.optional_data or "")
        optional_data_padded = self.utils.pad_field(optional_data, remaining_space)
        line2_parts.append(optional_data_padded)

        line2 = "".join(line2_parts)

        # Line 3: Name + visa category + composite check
        line3_parts = []

        # Calculate available space for name (36 - visa_category_length - 1 for composite)
        # Assume 2 characters for visa category for now
        visa_category_length = 2
        name_space = 36 - visa_category_length - 1

        # Name field
        name_field = self.utils.format_name_for_mrz(
            personal_data.surname, personal_data.given_names, name_space
        )
        line3_parts.append(name_field)

        # Visa category (placeholder)
        visa_category = self.utils.pad_field("", visa_category_length)
        line3_parts.append(visa_category)

        # Composite check digit
        doc_check = self._compute_check_digit(doc_number.ljust(9, "<"))
        composite_data = (
            doc_number.rstrip("<")
            + doc_check
            + birth_date
            + birth_check
            + expiry_date
            + expiry_check
        )
        composite_check = self._compute_check_digit(composite_data)
        line3_parts.append(composite_check)

        line3 = "".join(line3_parts)

        # Validate line lengths
        if len(line1) != MRZFieldLength.VISA_B_LINE_LENGTH:
            errors.append(
                f"Line 1 length incorrect: {len(line1)} != {MRZFieldLength.VISA_B_LINE_LENGTH}"
            )
        if len(line2) != MRZFieldLength.VISA_B_LINE_LENGTH:
            errors.append(
                f"Line 2 length incorrect: {len(line2)} != {MRZFieldLength.VISA_B_LINE_LENGTH}"
            )
        if len(line3) != MRZFieldLength.VISA_B_LINE_LENGTH:
            errors.append(
                f"Line 3 length incorrect: {len(line3)} != {MRZFieldLength.VISA_B_LINE_LENGTH}"
            )

        return MRZCompositionResult(
            line1=line1,
            line2=line2,
            line3=line3,
            document_check=doc_check,
            birth_check=birth_check,
            expiry_check=expiry_check,
            composite_check=composite_check,
            is_valid=len(errors) == 0,
            validation_errors=errors,
        )


class MRZComposerFactory:
    """Factory for creating appropriate MRZ composers."""

    _composers = {
        MRZDocumentType.PASSPORT: TD3PassportMRZComposer,
        MRZDocumentType.VISA_TYPE_A: VisaTypeAMRZComposer,
        MRZDocumentType.VISA_TYPE_B: VisaTypeBMRZComposer,
    }

    @classmethod
    def create_composer(cls, document_type: MRZDocumentType) -> BaseMRZComposer:
        """Create the appropriate MRZ composer for the document type."""
        composer_class = cls._composers.get(document_type)
        if not composer_class:
            msg = f"No MRZ composer available for document type: {document_type}"
            raise ValueError(msg)

        return composer_class()

    @classmethod
    def get_supported_types(cls) -> list[MRZDocumentType]:
        """Get list of supported document types."""
        return list(cls._composers.keys())


def compose_mrz(
    document_type: MRZDocumentType, personal_data: MRZPersonalData, document_data: MRZDocumentData
) -> MRZCompositionResult:
    """
    Convenience function to compose MRZ for any supported document type.

    Args:
        document_type: Type of document to create MRZ for
        personal_data: Personal information
        document_data: Document information

    Returns:
        MRZ composition result with generated lines and validation status
    """
    composer = MRZComposerFactory.create_composer(document_type)
    return composer.compose_mrz(personal_data, document_data)
