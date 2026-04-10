"""
Enhanced MRZ validation models for structured error reporting and validation results.

This module provides comprehensive data models for:
- Detailed error reporting with line/column positions
- Validation results with confidence scoring
- Document type inference with certainty metrics
- Structured suggestions for fixing MRZ data
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any, Optional, Union

from pydantic import BaseModel, Field


class MRZErrorCode(str, Enum):
    """Standardized error codes for MRZ validation issues."""

    # Format errors
    INVALID_LINE_COUNT = "INVALID_LINE_COUNT"
    INVALID_LINE_LENGTH = "INVALID_LINE_LENGTH"
    INVALID_CHARACTER = "INVALID_CHARACTER"
    MISSING_SEPARATOR = "MISSING_SEPARATOR"

    # Document type errors
    INVALID_DOCUMENT_TYPE = "INVALID_DOCUMENT_TYPE"
    UNSUPPORTED_DOCUMENT_TYPE = "UNSUPPORTED_DOCUMENT_TYPE"
    DOCUMENT_TYPE_MISMATCH = "DOCUMENT_TYPE_MISMATCH"

    # Check digit errors
    CHECKSUM_MISMATCH = "CHECKSUM_MISMATCH"
    COMPOSITE_CHECKSUM_MISMATCH = "COMPOSITE_CHECKSUM_MISMATCH"
    INVALID_CHECK_DIGIT_FORMAT = "INVALID_CHECK_DIGIT_FORMAT"

    # Date errors
    INVALID_DATE_FORMAT = "INVALID_DATE_FORMAT"
    INVALID_DATE_VALUE = "INVALID_DATE_VALUE"
    DATE_OUT_OF_RANGE = "DATE_OUT_OF_RANGE"
    EXPIRY_BEFORE_BIRTH = "EXPIRY_BEFORE_BIRTH"

    # Field errors
    INVALID_COUNTRY_CODE = "INVALID_COUNTRY_CODE"
    INVALID_GENDER_CODE = "INVALID_GENDER_CODE"
    INVALID_NATIONALITY = "INVALID_NATIONALITY"
    INVALID_DOCUMENT_NUMBER = "INVALID_DOCUMENT_NUMBER"

    # Name field errors
    INVALID_NAME_FORMAT = "INVALID_NAME_FORMAT"
    NAME_TOO_LONG = "NAME_TOO_LONG"
    MISSING_NAME_SEPARATOR = "MISSING_NAME_SEPARATOR"

    # Structure errors
    MALFORMED_MRZ_STRUCTURE = "MALFORMED_MRZ_STRUCTURE"
    INCONSISTENT_DATA = "INCONSISTENT_DATA"


class MRZDocumentType(str, Enum):
    """MRZ document types with their specifications."""

    TD1 = "TD1"  # 3 lines, 30 chars each (ID cards, including CMC)
    TD2 = "TD2"  # 2 lines, 36 chars each (ID cards, visas)
    TD3 = "TD3"  # 2 lines, 44 chars each (passports)

    @property
    def line_count(self) -> int:
        """Number of lines in this document type."""
        return {"TD1": 3, "TD2": 2, "TD3": 2}[self.value]

    @property
    def line_length(self) -> int:
        """Number of characters per line in this document type."""
        return {"TD1": 30, "TD2": 36, "TD3": 44}[self.value]

    @property
    def total_length(self) -> int:
        """Total number of characters in this document type."""
        return self.line_count * self.line_length


class MRZPosition(BaseModel):
    """Position information for MRZ fields and errors."""

    line: int = Field(..., description="Line number (0-based)")
    column: int = Field(..., description="Column number (0-based)")
    length: int = Field(default=1, description="Length of the field/error")

    def __str__(self) -> str:
        return f"Line {self.line + 1}, Column {self.column + 1}"


class MRZValidationError(BaseModel):
    """Detailed error information for MRZ validation issues."""

    code: MRZErrorCode = Field(..., description="Standardized error code")
    message: str = Field(..., description="Human-readable error message")
    position: MRZPosition | None = Field(default=None, description="Position of the error")
    field_name: str | None = Field(default=None, description="Name of the affected field")
    expected_value: str | None = Field(default=None, description="Expected value or format")
    actual_value: str | None = Field(default=None, description="Actual value found")
    suggestion: str | None = Field(default=None, description="Suggested fix")
    severity: str = Field(default="error", description="Error severity: error, warning, info")

    @property
    def is_critical(self) -> bool:
        """Whether this error prevents successful parsing."""
        critical_codes = {
            MRZErrorCode.INVALID_LINE_COUNT,
            MRZErrorCode.INVALID_LINE_LENGTH,
            MRZErrorCode.MALFORMED_MRZ_STRUCTURE,
            MRZErrorCode.UNSUPPORTED_DOCUMENT_TYPE,
        }
        return self.code in critical_codes


class MRZFieldValidation(BaseModel):
    """Validation result for a specific MRZ field."""

    field_name: str = Field(..., description="Name of the validated field")
    value: str | None = Field(default=None, description="Extracted value")
    position: MRZPosition | None = Field(default=None, description="Position in MRZ")
    is_valid: bool = Field(..., description="Whether the field is valid")
    errors: list[MRZValidationError] = Field(
        default_factory=list, description="Field-specific errors"
    )
    warnings: list[MRZValidationError] = Field(
        default_factory=list, description="Field-specific warnings"
    )
    confidence: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Confidence in extraction (0-1)"
    )
    checksum_valid: bool | None = Field(
        default=None, description="Check digit validation result"
    )

    @property
    def has_errors(self) -> bool:
        """Whether this field has any errors."""
        return len(self.errors) > 0

    @property
    def has_warnings(self) -> bool:
        """Whether this field has any warnings."""
        return len(self.warnings) > 0


class MRZDocumentTypeInference(BaseModel):
    """Result of document type inference with confidence scoring."""

    inferred_type: MRZDocumentType | None = Field(
        default=None, description="Inferred document type"
    )
    confidence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Confidence in inference (0-1)"
    )
    candidates: list[tuple[MRZDocumentType, float]] = Field(
        default_factory=list, description="All possible types with confidence scores"
    )
    reasons: list[str] = Field(default_factory=list, description="Reasons for the inference")

    @property
    def is_confident(self) -> bool:
        """Whether the inference is confident enough for parsing."""
        return self.confidence >= 0.8

    @property
    def is_ambiguous(self) -> bool:
        """Whether multiple types have similar confidence scores."""
        if len(self.candidates) < 2:
            return False
        top_two = sorted(self.candidates, key=lambda x: x[1], reverse=True)[:2]
        return abs(top_two[0][1] - top_two[1][1]) < 0.2


class MRZValidationResult(BaseModel):
    """Comprehensive validation result for MRZ parsing."""

    # Basic parsing info
    is_valid: bool = Field(..., description="Overall validation result")
    document_type: MRZDocumentType | None = Field(
        default=None, description="Detected document type"
    )
    type_inference: MRZDocumentTypeInference | None = Field(
        default=None, description="Document type inference results"
    )

    # Parsed data (if successful)
    parsed_data: dict[str, Any] | None = Field(
        default=None, description="Successfully parsed data"
    )

    # Validation details
    field_validations: dict[str, MRZFieldValidation] = Field(
        default_factory=dict, description="Field-by-field validation results"
    )

    # Error reporting
    errors: list[MRZValidationError] = Field(
        default_factory=list, description="All validation errors"
    )
    warnings: list[MRZValidationError] = Field(
        default_factory=list, description="All validation warnings"
    )

    # Metrics
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Overall confidence (0-1)")
    parsing_time_ms: float | None = Field(
        default=None, description="Time taken to parse (milliseconds)"
    )

    # Raw input
    raw_mrz: str = Field(..., description="Original MRZ input")
    normalized_mrz: str | None = Field(default=None, description="Normalized MRZ format")

    @property
    def error_count(self) -> int:
        """Total number of errors."""
        return len(self.errors)

    @property
    def warning_count(self) -> int:
        """Total number of warnings."""
        return len(self.warnings)

    @property
    def critical_error_count(self) -> int:
        """Number of critical errors that prevent parsing."""
        return sum(1 for error in self.errors if error.is_critical)

    @property
    def field_error_count(self) -> int:
        """Total number of field-level errors."""
        return sum(len(field.errors) for field in self.field_validations.values())

    @property
    def successful_fields(self) -> list[str]:
        """List of successfully validated field names."""
        return [name for name, field in self.field_validations.items() if field.is_valid]

    @property
    def failed_fields(self) -> list[str]:
        """List of field names that failed validation."""
        return [name for name, field in self.field_validations.items() if not field.is_valid]

    def get_field_errors(self, field_name: str) -> list[MRZValidationError]:
        """Get all errors for a specific field."""
        if field_name not in self.field_validations:
            return []
        return self.field_validations[field_name].errors

    def get_suggestions(self) -> list[str]:
        """Get all suggestions for fixing errors."""
        suggestions = []
        for error in self.errors:
            if error.suggestion:
                suggestions.append(error.suggestion)
        for field in self.field_validations.values():
            for error in field.errors:
                if error.suggestion:
                    suggestions.append(error.suggestion)
        return list(set(suggestions))  # Remove duplicates


class MRZNormalizedDate(BaseModel):
    """Normalized date information with century inference."""

    original_value: str = Field(..., description="Original YYMMDD string")
    year: int = Field(..., description="Full year with century")
    month: int = Field(..., ge=1, le=12, description="Month (1-12)")
    day: int = Field(..., ge=1, le=31, description="Day of month")
    date_object: date = Field(..., description="Python date object")
    century_inferred: bool = Field(..., description="Whether century was inferred")
    inference_reason: str | None = Field(
        default=None, description="Reason for century inference"
    )

    @property
    def is_future(self) -> bool:
        """Whether this date is in the future."""
        return self.date_object > date.today()

    @property
    def age_years(self) -> int | None:
        """Age in years if this is a birth date."""
        today = date.today()
        if self.date_object > today:
            return None
        age = today.year - self.date_object.year
        if today.month < self.date_object.month or (
            today.month == self.date_object.month and today.day < self.date_object.day
        ):
            age -= 1
        return age


class MRZCharacterValidation(BaseModel):
    """Validation result for individual characters in MRZ."""

    character: str = Field(..., description="The character")
    position: MRZPosition = Field(..., description="Position in MRZ")
    is_valid: bool = Field(..., description="Whether character is valid for MRZ")
    is_filler: bool = Field(default=False, description="Whether this is a filler character '<'")
    expected_type: str | None = Field(default=None, description="Expected character type")
    suggestion: str | None = Field(default=None, description="Suggested replacement")

    @property
    def is_alphanumeric(self) -> bool:
        """Whether the character is alphanumeric."""
        return self.character.isalnum()

    @property
    def is_letter(self) -> bool:
        """Whether the character is a letter."""
        return self.character.isalpha()

    @property
    def is_digit(self) -> bool:
        """Whether the character is a digit."""
        return self.character.isdigit()


class MRZParsingStats(BaseModel):
    """Statistics about MRZ parsing performance and accuracy."""

    total_characters: int = Field(..., description="Total characters processed")
    valid_characters: int = Field(..., description="Number of valid characters")
    filler_characters: int = Field(..., description="Number of filler characters")
    error_characters: int = Field(..., description="Number of invalid characters")

    checksum_validations: int = Field(
        default=0, description="Number of checksum validations performed"
    )
    checksum_failures: int = Field(default=0, description="Number of checksum validation failures")

    date_validations: int = Field(default=0, description="Number of date validations performed")
    date_failures: int = Field(default=0, description="Number of date validation failures")

    @property
    def character_accuracy(self) -> float:
        """Percentage of valid characters."""
        if self.total_characters == 0:
            return 0.0
        return (self.valid_characters / self.total_characters) * 100

    @property
    def checksum_accuracy(self) -> float:
        """Percentage of successful checksum validations."""
        if self.checksum_validations == 0:
            return 0.0
        return (
            (self.checksum_validations - self.checksum_failures) / self.checksum_validations
        ) * 100

    @property
    def date_accuracy(self) -> float:
        """Percentage of successful date validations."""
        if self.date_validations == 0:
            return 0.0
        return ((self.date_validations - self.date_failures) / self.date_validations) * 100
