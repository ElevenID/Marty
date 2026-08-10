"""
Enhanced MRZ Validation Layer

This module provides comprehensive MRZ structure validation and check digit
verification for all supported document types in the unified verification protocol.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from marty_plugin.shared.logging_config import get_logger

from marty_common.utils.mrz_utils import MRZParser
from marty_common.verification.document_detection import DocumentClass

logger = get_logger(__name__)


class MRZValidationLevel(Enum):
    """MRZ validation thoroughness levels."""

    BASIC = "basic"  # Structure only
    STANDARD = "standard"  # + check digits
    COMPREHENSIVE = "comprehensive"  # + cross-field validation
    STRICT = "strict"  # + ICAO compliance checks


@dataclass
class MRZValidationResult:
    """Result of MRZ validation check."""

    check_name: str
    passed: bool
    details: str = ""
    error_code: str | None = None
    metadata: dict[str, Any] = None

    def __post_init__(self) -> None:
        """Set defaults after initialization."""
        if self.metadata is None:
            self.metadata = {}
        self.timestamp = datetime.now(UTC)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "check_name": self.check_name,
            "passed": self.passed,
            "details": self.details,
            "error_code": self.error_code,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }


class MRZValidator:
    """Enhanced MRZ validation with comprehensive checks."""

    def __init__(self) -> None:
        """Initialize MRZ validator."""
        self.parser = MRZParser()

    def validate_mrz(
        self,
        mrz_data: str,
        document_class: DocumentClass,
        validation_level: MRZValidationLevel = MRZValidationLevel.STANDARD,
    ) -> list[MRZValidationResult]:
        """
        Validate MRZ data comprehensively.

        Args:
            mrz_data: Raw MRZ string
            document_class: Detected document class
            validation_level: Thoroughness of validation

        Returns:
            List of validation results
        """
        results = []

        # Phase 1: Basic structure validation
        structure_results = self._validate_structure(mrz_data, document_class)
        results.extend(structure_results)

        # Stop if structure validation fails
        if not all(r.passed for r in structure_results):
            return results

        # Phase 2: Check digit validation (if requested)
        if validation_level in [
            MRZValidationLevel.STANDARD,
            MRZValidationLevel.COMPREHENSIVE,
            MRZValidationLevel.STRICT,
        ]:
            check_digit_results = self._validate_check_digits(mrz_data, document_class)
            results.extend(check_digit_results)

        # Phase 3: Cross-field validation (if requested)
        if validation_level in [MRZValidationLevel.COMPREHENSIVE, MRZValidationLevel.STRICT]:
            cross_field_results = self._validate_cross_fields(mrz_data, document_class)
            results.extend(cross_field_results)

        # Phase 4: ICAO compliance checks (if requested)
        if validation_level == MRZValidationLevel.STRICT:
            compliance_results = self._validate_icao_compliance(mrz_data, document_class)
            results.extend(compliance_results)

        return results

    def _validate_structure(self, mrz_data: str, document_class: DocumentClass) -> list[MRZValidationResult]:
        """Validate basic MRZ structure."""
        results = []

        # Normalize lines
        lines = [line.strip() for line in mrz_data.strip().split("\n") if line.strip()]

        if not lines:
            results.append(MRZValidationResult("MRZ Structure", False, "No MRZ lines found", "NO_LINES"))
            return results

        # Validate based on document class
        if document_class == DocumentClass.PASSPORT:
            results.extend(self._validate_td3_structure(lines))
        elif document_class == DocumentClass.CMC:
            results.extend(self._validate_td1_structure(lines))
        elif document_class in [DocumentClass.VISA, DocumentClass.ID_CARD, DocumentClass.TD2_MISC]:
            results.extend(self._validate_td2_structure(lines))
        elif document_class in [DocumentClass.TRAVEL_DOCUMENT, DocumentClass.RESIDENCE]:
            results.extend(self._validate_flexible_structure(lines))
        else:
            results.append(
                MRZValidationResult(
                    "MRZ Structure",
                    False,
                    f"Unknown document class: {document_class}",
                    "UNKNOWN_CLASS",
                )
            )

        return results

    def _validate_td3_structure(self, lines: list[str]) -> list[MRZValidationResult]:
        """Validate TD-3 (passport) MRZ structure."""
        results = []

        # Check line count
        if len(lines) != 2:
            results.append(
                MRZValidationResult(
                    "TD-3 Line Count",
                    False,
                    f"Expected 2 lines, found {len(lines)}",
                    "WRONG_LINE_COUNT",
                    {"expected": 2, "actual": len(lines)},
                )
            )
            return results

        results.append(MRZValidationResult("TD-3 Line Count", True, "Correct number of lines (2)"))

        # Check line lengths
        for i, line in enumerate(lines, 1):
            if len(line) != 44:
                results.append(
                    MRZValidationResult(
                        f"TD-3 Line {i} Length",
                        False,
                        f"Expected 44 characters, found {len(line)}",
                        "WRONG_LINE_LENGTH",
                        {"line": i, "expected": 44, "actual": len(line)},
                    )
                )
            else:
                results.append(MRZValidationResult(f"TD-3 Line {i} Length", True, f"Line {i} has correct length (44)"))

        # Validate character set
        for i, line in enumerate(lines, 1):
            char_result = self._validate_character_set(line, f"TD-3 Line {i}")
            results.append(char_result)

        return results

    def _validate_td1_structure(self, lines: list[str]) -> list[MRZValidationResult]:
        """Validate TD-1 (CMC) MRZ structure."""
        results = []

        # Check line count
        if len(lines) != 3:
            results.append(
                MRZValidationResult(
                    "TD-1 Line Count",
                    False,
                    f"Expected 3 lines, found {len(lines)}",
                    "WRONG_LINE_COUNT",
                    {"expected": 3, "actual": len(lines)},
                )
            )
            return results

        results.append(MRZValidationResult("TD-1 Line Count", True, "Correct number of lines (3)"))

        # Check line lengths
        for i, line in enumerate(lines, 1):
            if len(line) != 30:
                results.append(
                    MRZValidationResult(
                        f"TD-1 Line {i} Length",
                        False,
                        f"Expected 30 characters, found {len(line)}",
                        "WRONG_LINE_LENGTH",
                        {"line": i, "expected": 30, "actual": len(line)},
                    )
                )
            else:
                results.append(MRZValidationResult(f"TD-1 Line {i} Length", True, f"Line {i} has correct length (30)"))

        # Validate character set
        for i, line in enumerate(lines, 1):
            char_result = self._validate_character_set(line, f"TD-1 Line {i}")
            results.append(char_result)

        return results

    def _validate_td2_structure(self, lines: list[str]) -> list[MRZValidationResult]:
        """Validate TD-2 (visa/ID) MRZ structure."""
        results = []

        # Check line count
        if len(lines) != 2:
            results.append(
                MRZValidationResult(
                    "TD-2 Line Count",
                    False,
                    f"Expected 2 lines, found {len(lines)}",
                    "WRONG_LINE_COUNT",
                    {"expected": 2, "actual": len(lines)},
                )
            )
            return results

        results.append(MRZValidationResult("TD-2 Line Count", True, "Correct number of lines (2)"))

        # Check line lengths
        for i, line in enumerate(lines, 1):
            if len(line) != 36:
                results.append(
                    MRZValidationResult(
                        f"TD-2 Line {i} Length",
                        False,
                        f"Expected 36 characters, found {len(line)}",
                        "WRONG_LINE_LENGTH",
                        {"line": i, "expected": 36, "actual": len(line)},
                    )
                )
            else:
                results.append(MRZValidationResult(f"TD-2 Line {i} Length", True, f"Line {i} has correct length (36)"))

        # Validate character set
        for i, line in enumerate(lines, 1):
            char_result = self._validate_character_set(line, f"TD-2 Line {i}")
            results.append(char_result)

        return results

    def _validate_flexible_structure(self, lines: list[str]) -> list[MRZValidationResult]:
        """Validate flexible structure for travel documents."""
        results = []

        # More lenient validation for various formats
        if len(lines) < 2:
            results.append(
                MRZValidationResult(
                    "Flexible Structure",
                    False,
                    f"At least 2 lines required, found {len(lines)}",
                    "INSUFFICIENT_LINES",
                    {"minimum": 2, "actual": len(lines)},
                )
            )
            return results

        results.append(MRZValidationResult("Flexible Structure", True, f"Sufficient lines found ({len(lines)})"))

        # Check minimum line length
        for i, line in enumerate(lines, 1):
            if len(line) < 30:
                results.append(
                    MRZValidationResult(
                        f"Flexible Line {i} Length",
                        False,
                        f"Minimum 30 characters required, found {len(line)}",
                        "LINE_TOO_SHORT",
                        {"line": i, "minimum": 30, "actual": len(line)},
                    )
                )
            else:
                results.append(MRZValidationResult(f"Flexible Line {i} Length", True, f"Line {i} meets minimum length"))

        return results

    def _validate_character_set(self, line: str, context: str) -> MRZValidationResult:
        """Validate MRZ character set (A-Z, 0-9, <)."""
        valid_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<")

        invalid_chars = [char for char in line if char not in valid_chars]

        if invalid_chars:
            return MRZValidationResult(
                f"{context} Characters",
                False,
                f"Invalid characters found: {set(invalid_chars)}",
                "INVALID_CHARACTERS",
                {"invalid_chars": list(set(invalid_chars)), "total_invalid": len(invalid_chars)},
            )

        return MRZValidationResult(f"{context} Characters", True, "All characters valid")

    def _validate_check_digits(self, mrz_data: str, document_class: DocumentClass) -> list[MRZValidationResult]:
        """Validate check digits for the document type."""
        results = []

        try:
            if document_class == DocumentClass.PASSPORT:
                results.extend(self._validate_td3_check_digits(mrz_data))
            elif document_class == DocumentClass.CMC:
                results.extend(self._validate_td1_check_digits(mrz_data))
            elif document_class in [
                DocumentClass.VISA,
                DocumentClass.ID_CARD,
                DocumentClass.TD2_MISC,
            ]:
                results.extend(self._validate_td2_check_digits(mrz_data))
            else:
                results.append(
                    MRZValidationResult(
                        "Check Digits",
                        True,
                        "Check digit validation not implemented for this document type",
                    )
                )

        except Exception as e:
            results.append(
                MRZValidationResult("Check Digits", False, f"Check digit validation error: {e}", "CHECK_DIGIT_ERROR")
            )

        return results

    def _validate_td3_check_digits(self, mrz_data: str) -> list[MRZValidationResult]:
        """Validate TD-3 check digits."""
        results = []

        try:
            # Use existing MRZ parser if available
            from marty_common.utils.mrz_utils import parse_td3_mrz

            parsed = parse_td3_mrz(mrz_data)

            if parsed and parsed.get("check_digits_valid", False):
                results.append(MRZValidationResult("TD-3 Check Digits", True, "All check digits valid"))
            else:
                results.append(
                    MRZValidationResult(
                        "TD-3 Check Digits",
                        False,
                        "Check digit validation failed",
                        "CHECK_DIGIT_INVALID",
                    )
                )

        except ImportError:
            results.append(
                MRZValidationResult(
                    "TD-3 Check Digits",
                    False,
                    "Native MRZ parser is unavailable",
                    "NATIVE_BACKEND_UNAVAILABLE",
                )
            )

        return results

    def _validate_td1_check_digits(self, mrz_data: str) -> list[MRZValidationResult]:
        """Validate TD-1 check digits."""
        results = []

        try:
            # Use existing MRZ parser if available
            from marty_common.utils.mrz_utils import parse_td1_mrz

            parsed = parse_td1_mrz(mrz_data)

            if parsed and parsed.get("check_digits_valid", False):
                results.append(MRZValidationResult("TD-1 Check Digits", True, "All check digits valid"))
            else:
                results.append(
                    MRZValidationResult(
                        "TD-1 Check Digits",
                        False,
                        "Check digit validation failed",
                        "CHECK_DIGIT_INVALID",
                    )
                )

        except ImportError:
            results.append(
                MRZValidationResult(
                    "TD-1 Check Digits",
                    False,
                    "Native MRZ parser is unavailable",
                    "NATIVE_BACKEND_UNAVAILABLE",
                )
            )

        return results

    def _validate_td2_check_digits(self, mrz_data: str) -> list[MRZValidationResult]:
        """Validate TD-2 check digits."""
        results = []

        try:
            # Use existing MRZ parser if available
            from marty_common.utils.mrz_utils import parse_td2_mrz

            parsed = parse_td2_mrz(mrz_data)

            if parsed and parsed.get("check_digits_valid", False):
                results.append(MRZValidationResult("TD-2 Check Digits", True, "All check digits valid"))
            else:
                results.append(
                    MRZValidationResult(
                        "TD-2 Check Digits",
                        False,
                        "Check digit validation failed",
                        "CHECK_DIGIT_INVALID",
                    )
                )

        except ImportError:
            results.append(
                MRZValidationResult(
                    "TD-2 Check Digits",
                    False,
                    "Native MRZ parser is unavailable",
                    "NATIVE_BACKEND_UNAVAILABLE",
                )
            )

        return results

    def _validate_cross_fields(self, mrz_data: str, document_class: DocumentClass) -> list[MRZValidationResult]:
        """Require the native parser to return all mandatory identity fields."""
        del document_class
        try:
            parsed = self.parser.parse_mrz(mrz_data)
            required = (
                "document_number",
                "date_of_birth",
                "date_of_expiry",
                "issuing_country",
                "nationality",
            )
            missing = [name for name in required if not getattr(parsed, name, None)]
        except Exception as exc:
            return [
                MRZValidationResult(
                    "Cross-Field Validation",
                    False,
                    f"Native MRZ validation failed: {exc}",
                    "NATIVE_MRZ_INVALID",
                )
            ]
        return [
            MRZValidationResult(
                "Cross-Field Validation",
                not missing,
                (
                    "Native MRZ parser returned all mandatory fields"
                    if not missing
                    else f"Missing mandatory fields: {', '.join(missing)}"
                ),
                None if not missing else "MISSING_REQUIRED_FIELD",
            )
        ]

    def _validate_icao_compliance(self, mrz_data: str, document_class: DocumentClass) -> list[MRZValidationResult]:
        """Use the authoritative native parser for ICAO format compliance."""
        del document_class
        try:
            self.parser.parse_mrz(mrz_data)
        except Exception as exc:
            return [
                MRZValidationResult(
                    "ICAO Compliance",
                    False,
                    f"Native ICAO parsing failed: {exc}",
                    "ICAO_FORMAT_INVALID",
                )
            ]
        return [
            MRZValidationResult(
                "ICAO Compliance",
                True,
                "Native ICAO parser accepted the MRZ",
            )
        ]


# Convenience functions
def validate_mrz_basic(mrz_data: str, document_class: DocumentClass) -> list[MRZValidationResult]:
    """Basic MRZ validation (structure only)."""
    validator = MRZValidator()
    return validator.validate_mrz(mrz_data, document_class, MRZValidationLevel.BASIC)


def validate_mrz_standard(mrz_data: str, document_class: DocumentClass) -> list[MRZValidationResult]:
    """Standard MRZ validation (structure + check digits)."""
    validator = MRZValidator()
    return validator.validate_mrz(mrz_data, document_class, MRZValidationLevel.STANDARD)


def is_mrz_valid(mrz_data: str, document_class: DocumentClass) -> bool:
    """Quick MRZ validity check."""
    results = validate_mrz_standard(mrz_data, document_class)
    return all(r.passed for r in results)
