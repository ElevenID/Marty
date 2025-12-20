"""
Integration module for standardized MRZ behavior with existing visa models.

This module provides utilities to integrate the new standardized MRZ system
with the existing visa models while maintaining backward compatibility.
"""

from __future__ import annotations

from marty_plugin.shared.models.visa import MRZData, Visa, VisaType

from .mrz_composition import MRZCompositionResult, MRZDocumentData, MRZPersonalData, compose_mrz
from .mrz_standardized import MRZDocumentType, MRZStandardizedUtils


class VisaMRZIntegration:
    """Integration utilities for visa MRZ generation using standardized system."""

    @staticmethod
    def convert_visa_to_mrz_data(visa: Visa) -> tuple[MRZPersonalData, MRZDocumentData]:
        """
        Convert visa model data to standardized MRZ data structures.

        Args:
            visa: Visa model instance

        Returns:
            Tuple of (personal_data, document_data) for MRZ generation
        """
        personal = visa.personal_data
        document = visa.document_data

        # Convert personal data
        mrz_personal = MRZPersonalData(
            surname=personal.surname,
            given_names=personal.given_names,
            nationality=personal.nationality,
            date_of_birth=personal.date_of_birth,
            gender=personal.gender.value if personal.gender else "X",
        )

        # Convert document data
        mrz_document = MRZDocumentData(
            document_type="V",  # All visas use "V"
            issuing_country=document.issuing_state,
            document_number=document.document_number,
            date_of_expiry=document.date_of_expiry,
            personal_number=getattr(document, "personal_number", None),
            optional_data=getattr(document, "optional_data", None),
        )

        return mrz_personal, mrz_document

    @staticmethod
    def determine_mrz_document_type(visa_type: VisaType) -> MRZDocumentType:
        """
        Determine the appropriate MRZ document type from visa type.

        Args:
            visa_type: Visa type from the visa model

        Returns:
            Corresponding MRZ document type
        """
        if visa_type == VisaType.MRV_TYPE_A:
            return MRZDocumentType.VISA_TYPE_A
        if visa_type == VisaType.MRV_TYPE_B:
            return MRZDocumentType.VISA_TYPE_B
        # Default to Type A for e-visas and other types
        return MRZDocumentType.VISA_TYPE_A

    @staticmethod
    def generate_standardized_mrz(visa: Visa) -> MRZCompositionResult:
        """
        Generate standardized MRZ for a visa using the new system.

        Args:
            visa: Visa model instance

        Returns:
            MRZ composition result with generated lines and validation status
        """
        # Convert visa data to MRZ format
        mrz_personal, mrz_document = VisaMRZIntegration.convert_visa_to_mrz_data(visa)

        # Determine document type
        document_type = VisaMRZIntegration.determine_mrz_document_type(visa.document_data.visa_type)

        # Generate MRZ
        return compose_mrz(document_type, mrz_personal, mrz_document)

    @staticmethod
    def update_visa_mrz_data(visa: Visa, mrz_result: MRZCompositionResult) -> None:
        """
        Update the visa's MRZ data with the standardized generation result.

        Args:
            visa: Visa model instance to update
            mrz_result: Result from standardized MRZ generation
        """
        if visa.mrz_data is None:
            visa.mrz_data = MRZData()

        # Update based on visa type
        if visa.document_data.visa_type == VisaType.MRV_TYPE_A:
            # Type A: 2 lines
            visa.mrz_data.type_a_line1 = mrz_result.line1
            visa.mrz_data.type_a_line2 = mrz_result.line2
            # Clear Type B fields
            visa.mrz_data.type_b_line1 = None
            visa.mrz_data.type_b_line2 = None
            visa.mrz_data.type_b_line3 = None
        elif visa.document_data.visa_type == VisaType.MRV_TYPE_B:
            # Type B: 3 lines
            visa.mrz_data.type_b_line1 = mrz_result.line1
            visa.mrz_data.type_b_line2 = mrz_result.line2
            visa.mrz_data.type_b_line3 = mrz_result.line3
            # Clear Type A fields
            visa.mrz_data.type_a_line1 = None
            visa.mrz_data.type_a_line2 = None
        else:
            # Default to Type A for other visa types
            visa.mrz_data.type_a_line1 = mrz_result.line1
            visa.mrz_data.type_a_line2 = mrz_result.line2

        # Update check digits
        visa.mrz_data.check_digit_document = mrz_result.document_check
        visa.mrz_data.check_digit_dob = mrz_result.birth_check
        visa.mrz_data.check_digit_expiry = mrz_result.expiry_check
        visa.mrz_data.check_digit_composite = mrz_result.composite_check

        # Update timestamp
        visa.update_timestamp()

    @staticmethod
    def validate_existing_mrz(visa: Visa) -> tuple[bool, list[str]]:
        """
        Validate existing MRZ data in a visa using standardized validation.

        Args:
            visa: Visa model instance with existing MRZ data

        Returns:
            Tuple of (is_valid, error_messages)
        """
        if not visa.mrz_data:
            return False, ["No MRZ data present"]

        errors = []
        utils = MRZStandardizedUtils()

        # Determine which MRZ lines to validate
        if visa.document_data.visa_type == VisaType.MRV_TYPE_A:
            lines = [visa.mrz_data.type_a_line1, visa.mrz_data.type_a_line2]
            expected_length = 44
        elif visa.document_data.visa_type == VisaType.MRV_TYPE_B:
            lines = [
                visa.mrz_data.type_b_line1,
                visa.mrz_data.type_b_line2,
                visa.mrz_data.type_b_line3,
            ]
            expected_length = 36
        else:
            # Default to Type A
            lines = [visa.mrz_data.type_a_line1, visa.mrz_data.type_a_line2]
            expected_length = 44

        # Validate line presence and length
        for i, line in enumerate(lines, 1):
            if not line:
                errors.append(f"MRZ line {i} is missing")
                continue

            if not utils.validate_mrz_line_length(line, expected_length):
                errors.append(
                    f"MRZ line {i} has incorrect length: {len(line)} != {expected_length}"
                )

            if not utils.validate_mrz_characters(line):
                errors.append(f"MRZ line {i} contains invalid characters")

        # Validate check digits if available
        if visa.mrz_data.check_digit_document:
            # Extract document number from MRZ and validate
            doc_number = VisaMRZIntegration._extract_document_number_from_mrz(visa)
            if doc_number and not utils.validate_check_digit(
                doc_number, visa.mrz_data.check_digit_document
            ):
                errors.append("Document number check digit is invalid")

        if visa.mrz_data.check_digit_dob:
            # Extract birth date from MRZ and validate
            birth_date = VisaMRZIntegration._extract_birth_date_from_mrz(visa)
            if birth_date and not utils.validate_check_digit(
                birth_date, visa.mrz_data.check_digit_dob
            ):
                errors.append("Birth date check digit is invalid")

        if visa.mrz_data.check_digit_expiry:
            # Extract expiry date from MRZ and validate
            expiry_date = VisaMRZIntegration._extract_expiry_date_from_mrz(visa)
            if expiry_date and not utils.validate_check_digit(
                expiry_date, visa.mrz_data.check_digit_expiry
            ):
                errors.append("Expiry date check digit is invalid")

        return len(errors) == 0, errors

    @staticmethod
    def _extract_document_number_from_mrz(visa: Visa) -> str | None:
        """Extract document number from MRZ lines for validation."""
        if not visa.mrz_data:
            return None

        if visa.document_data.visa_type == VisaType.MRV_TYPE_A and visa.mrz_data.type_a_line2:
            # Type A: document number is at positions 0-8 in line 2
            return visa.mrz_data.type_a_line2[:9].ljust(9, "<")
        if visa.document_data.visa_type == VisaType.MRV_TYPE_B and visa.mrz_data.type_b_line1:
            # Type B: document number is in line 1 after V<III<
            line1 = visa.mrz_data.type_b_line1
            if len(line1) >= 5:
                return line1[5:].ljust(9, "<")[:9]

        return None

    @staticmethod
    def _extract_birth_date_from_mrz(visa: Visa) -> str | None:
        """Extract birth date from MRZ lines for validation."""
        if not visa.mrz_data:
            return None

        if visa.document_data.visa_type == VisaType.MRV_TYPE_A and visa.mrz_data.type_a_line2:
            # Type A: birth date is at positions 13-18 in line 2
            line2 = visa.mrz_data.type_a_line2
            if len(line2) >= 19:
                return line2[13:19]
        elif visa.document_data.visa_type == VisaType.MRV_TYPE_B and visa.mrz_data.type_b_line2:
            # Type B: birth date is at positions 0-5 in line 2
            line2 = visa.mrz_data.type_b_line2
            if len(line2) >= 6:
                return line2[:6]

        return None

    @staticmethod
    def _extract_expiry_date_from_mrz(visa: Visa) -> str | None:
        """Extract expiry date from MRZ lines for validation."""
        if not visa.mrz_data:
            return None

        if visa.document_data.visa_type == VisaType.MRV_TYPE_A and visa.mrz_data.type_a_line2:
            # Type A: expiry date is at positions 21-26 in line 2
            line2 = visa.mrz_data.type_a_line2
            if len(line2) >= 27:
                return line2[21:27]
        elif visa.document_data.visa_type == VisaType.MRV_TYPE_B and visa.mrz_data.type_b_line2:
            # Type B: expiry date is at positions 7-12 in line 2
            line2 = visa.mrz_data.type_b_line2
            if len(line2) >= 13:
                return line2[7:13]

        return None

    @staticmethod
    def regenerate_visa_mrz(visa: Visa) -> bool:
        """
        Regenerate MRZ data for a visa using the standardized system.

        Args:
            visa: Visa model instance

        Returns:
            True if MRZ was successfully regenerated, False otherwise
        """
        try:
            # Generate new MRZ
            mrz_result = VisaMRZIntegration.generate_standardized_mrz(visa)

            if not mrz_result.is_valid:
                # Log validation errors but still update if possible
                print(f"MRZ generation had validation errors: {mrz_result.validation_errors}")

            # Update visa with new MRZ data
            VisaMRZIntegration.update_visa_mrz_data(visa, mrz_result)
        except Exception as e:
            print(f"Failed to regenerate MRZ for visa {visa.visa_id}: {e}")
            return False


def migrate_visa_to_standardized_mrz(
    visa: Visa, force_regenerate: bool = False
) -> tuple[bool, list[str]]:
    """
    Migrate a visa to use the standardized MRZ system.

    Args:
        visa: Visa model instance to migrate
        force_regenerate: If True, always regenerate MRZ even if existing data is valid

    Returns:
        Tuple of (success, messages)
    """
    messages = []

    # Check if existing MRZ is valid
    if not force_regenerate and visa.mrz_data:
        is_valid, errors = VisaMRZIntegration.validate_existing_mrz(visa)
        if is_valid:
            messages.append("Existing MRZ data is valid, no migration needed")
            return True, messages
        messages.extend([f"Existing MRZ validation error: {error}" for error in errors])

    # Regenerate MRZ using standardized system
    success = VisaMRZIntegration.regenerate_visa_mrz(visa)

    if success:
        messages.append("Successfully migrated to standardized MRZ system")

        # Validate the new MRZ
        is_valid, validation_errors = VisaMRZIntegration.validate_existing_mrz(visa)
        if is_valid:
            messages.append("New MRZ data passes validation")
        else:
            messages.extend([f"New MRZ validation warning: {error}" for error in validation_errors])
    else:
        messages.append("Failed to migrate to standardized MRZ system")

    return success, messages


def standardize_all_visa_mrz_behavior() -> None:
    """
    Utility function to demonstrate how to standardize MRZ behavior across all visa types.

    This function shows how the new standardized system ensures consistent MRZ
    generation and validation across all visa document types according to Doc 9303.
    """
    print("MRZ Standardization Summary:")
    print("=" * 50)
    print()

    print("✓ Standardized check digit calculation:")
    print("  - Character mapping: 0-9 → 0-9, A-Z → 10-35, < → 0")
    print("  - Weights: [7, 3, 1] repeating")
    print("  - Modulo 10 result")
    print()

    print("✓ Standardized name formatting:")
    print("  - Format: PRIMARY<<SECONDARY<ADDITIONAL...")
    print("  - ASCII transliteration (À → A, Ä → AE, etc.)")
    print("  - Deterministic truncation when needed")
    print("  - Disallowed punctuation removal")
    print()

    print("✓ Standardized date validation:")
    print("  - Format: YYMMDD with leap year validation")
    print("  - Document-specific expiry policies")
    print("  - Future/past date validation")
    print()

    print("✓ Standardized field handling:")
    print("  - Proper field truncation and padding")
    print("  - Filler character '<' handling")
    print("  - Field length validation")
    print()

    print("✓ Document type support:")
    print("  - TD3 Passports (44x2 characters)")
    print("  - Visa Type A (44x2 characters)")
    print("  - Visa Type B (36x3 characters)")
    print("  - Unified API for all types")
    print()

    print("Integration complete! All MRZ behavior is now standardized according to Doc 9303.")
