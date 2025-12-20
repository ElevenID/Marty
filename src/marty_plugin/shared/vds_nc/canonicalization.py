"""
VDS-NC Canonicalization Implementation per ICAO Doc 9303 Part 13.

This module implements the canonical dataset generation with:
- Deterministic key ordering (UTF-8 lexicographic sort)
- UTF-8 encoding with no insignificant whitespace
- Strict field validation and schema compliance
- Canonicalization drift detection
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, ClassVar

from .types import CanonicalizeError, DocumentType


@dataclass
class CanonicalField:
    """Definition of a canonical field for VDS-NC."""

    key: str
    required: bool
    data_type: type
    max_length: int | None = None
    format_pattern: str | None = None
    description: str = ""


class VDSNCCanonicalizer:
    """
    VDS-NC canonicalization engine following Doc 9303 Part 13.

    Provides deterministic canonicalization with:
    - Sorted keys (UTF-8 lexicographic order)
    - No insignificant whitespace
    - UTF-8 encoding
    - Strict field validation
    """

    # Canonical field definitions for each document type
    CANONICAL_FIELDS: ClassVar[dict[DocumentType, list[CanonicalField]]] = {
        DocumentType.CMC: [
            CanonicalField("docType", True, str, 3, description="Document type (CMC)"),
            CanonicalField("issuingCountry", True, str, 3, description="3-letter country code"),
            CanonicalField("documentNumber", True, str, 9, description="Document number"),
            CanonicalField("surname", True, str, 39, description="Primary surname"),
            CanonicalField("givenNames", True, str, 39, description="Given names"),
            CanonicalField("dateOfBirth", True, str, 8, r"^\d{8}$", "Date of birth (YYYYMMDD)"),
            CanonicalField("nationality", True, str, 3, description="3-letter nationality code"),
            CanonicalField("gender", True, str, 1, r"^[MFX]$", "Gender (M/F/X)"),
            CanonicalField("dateOfIssue", True, str, 8, r"^\d{8}$", "Issue date (YYYYMMDD)"),
            CanonicalField("dateOfExpiry", True, str, 8, r"^\d{8}$", "Expiry date (YYYYMMDD)"),
            CanonicalField("issuingAuthority", False, str, 50, description="Issuing authority"),
            CanonicalField("placeOfIssue", False, str, 50, description="Place of issue"),
        ],
        DocumentType.MRV: [
            CanonicalField("docType", True, str, 1, description="Document type (V)"),
            CanonicalField("issuingCountry", True, str, 3, description="3-letter country code"),
            CanonicalField("documentNumber", True, str, 9, description="Visa number"),
            CanonicalField("surname", True, str, 39, description="Primary surname"),
            CanonicalField("givenNames", True, str, 39, description="Given names"),
            CanonicalField("dateOfBirth", True, str, 8, r"^\d{8}$", "Date of birth (YYYYMMDD)"),
            CanonicalField("nationality", True, str, 3, description="3-letter nationality code"),
            CanonicalField("gender", True, str, 1, r"^[MFX]$", "Gender (M/F/X)"),
            CanonicalField("visaCategory", True, str, 10, description="Visa category"),
            CanonicalField("dateOfIssue", True, str, 8, r"^\d{8}$", "Issue date (YYYYMMDD)"),
            CanonicalField("dateOfExpiry", True, str, 8, r"^\d{8}$", "Expiry date (YYYYMMDD)"),
            CanonicalField("validFrom", False, str, 8, r"^\d{8}$", "Valid from date (YYYYMMDD)"),
            CanonicalField("validUntil", False, str, 8, r"^\d{8}$", "Valid until date (YYYYMMDD)"),
            CanonicalField("numberOfEntries", False, str, 10, description="Number of entries"),
            CanonicalField("durationOfStay", False, int, description="Duration of stay (days)"),
            CanonicalField("placeOfIssue", False, str, 50, description="Place of issue"),
        ],
        DocumentType.E_VISA: [
            CanonicalField("docType", True, str, 10, description="Document type (EVISA)"),
            CanonicalField("issuingCountry", True, str, 3, description="3-letter country code"),
            CanonicalField("documentNumber", True, str, 20, description="E-visa number"),
            CanonicalField("surname", True, str, 39, description="Primary surname"),
            CanonicalField("givenNames", True, str, 39, description="Given names"),
            CanonicalField("dateOfBirth", True, str, 8, r"^\d{8}$", "Date of birth (YYYYMMDD)"),
            CanonicalField("nationality", True, str, 3, description="3-letter nationality code"),
            CanonicalField("gender", True, str, 1, r"^[MFX]$", "Gender (M/F/X)"),
            CanonicalField("visaCategory", True, str, 10, description="Visa category"),
            CanonicalField("dateOfIssue", True, str, 8, r"^\d{8}$", "Issue date (YYYYMMDD)"),
            CanonicalField("dateOfExpiry", True, str, 8, r"^\d{8}$", "Expiry date (YYYYMMDD)"),
            CanonicalField("validFrom", False, str, 8, r"^\d{8}$", "Valid from date (YYYYMMDD)"),
            CanonicalField("validUntil", False, str, 8, r"^\d{8}$", "Valid until date (YYYYMMDD)"),
            CanonicalField("numberOfEntries", False, str, 10, description="Number of entries"),
            CanonicalField("purposeOfTravel", False, str, 50, description="Purpose of travel"),
            CanonicalField("passportNumber", True, str, 20, description="Passport number"),
            CanonicalField("passportCountry", True, str, 3, description="Passport issuing country"),
            CanonicalField(
                "onlineReference", False, str, 50, description="Online verification reference"
            ),
        ],
    }

    @staticmethod
    def canonicalize(data: dict[str, Any], doc_type: DocumentType) -> str:
        """
        Create canonical representation of document data.

        Args:
            data: Document data dictionary
            doc_type: Type of document for field validation

        Returns:
            Canonical JSON string with sorted keys, no whitespace

        Raises:
            CanonicalizeError: If validation fails
        """
        canonical_fields = VDSNCCanonicalizer.CANONICAL_FIELDS.get(doc_type)
        if not canonical_fields:
            msg = f"Unsupported document type: {doc_type}"
            raise CanonicalizeError(msg)

        # Validate and normalize fields
        canonical_data = {}

        for field in canonical_fields:
            value = data.get(field.key)

            # Check required fields
            if field.required and value is None:
                msg = f"Required field '{field.key}' is missing"
                raise CanonicalizeError(msg)

            if value is not None:
                # Type validation and conversion
                canonical_data[field.key] = VDSNCCanonicalizer._validate_and_convert_field(
                    field, value
                )

        # Check for extra fields not in schema
        extra_fields = set(data.keys()) - {f.key for f in canonical_fields}
        if extra_fields:
            msg = f"Extra fields not allowed in canonical form: {extra_fields}"
            raise CanonicalizeError(msg)

        # Create canonical JSON with sorted keys, no spaces
        return json.dumps(canonical_data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @staticmethod
    def _validate_and_convert_field(field: CanonicalField, value: Any) -> Any:
        """Validate and convert a single field value."""
        # Type validation
        if not isinstance(value, field.data_type):
            try:
                if field.data_type is str:
                    value = str(value)
                elif field.data_type is int:
                    value = int(value)
                else:
                    msg = f"Cannot convert {type(value)} to {field.data_type}"
                    raise CanonicalizeError(msg)
            except (ValueError, TypeError) as e:
                msg = f"Field '{field.key}' type validation failed: {e}"
                raise CanonicalizeError(msg) from e

        # String field validation
        if isinstance(value, str):
            value = VDSNCCanonicalizer._validate_string_field(field, value)

        return value

    @staticmethod
    def _validate_string_field(field: CanonicalField, value: str) -> str:
        """Validate and normalize string fields."""
        # Remove insignificant whitespace and normalize
        value = value.strip().upper()

        # Length validation
        if field.max_length and len(value) > field.max_length:
            msg = f"Field '{field.key}' exceeds maximum length {field.max_length}"
            raise CanonicalizeError(msg)

        # Pattern validation
        if field.format_pattern and not re.match(field.format_pattern, value):
            msg = f"Field '{field.key}' format invalid: {value}"
            raise CanonicalizeError(msg)

        return value

    @staticmethod
    def validate_canonicalization_drift(
        original_canonical: str, new_data: dict[str, Any], doc_type: DocumentType
    ) -> list[str]:
        """
        Detect canonicalization drift between original and new data.

        Args:
            original_canonical: Original canonical form
            new_data: New data to validate
            doc_type: Document type

        Returns:
            List of drift errors (empty if no drift)
        """
        try:
            new_canonical = VDSNCCanonicalizer.canonicalize(new_data, doc_type)
            if original_canonical != new_canonical:
                return ["Canonicalization drift detected: original != new"]
        except CanonicalizeError as e:
            return [f"Canonicalization validation failed: {e}"]

        return []
