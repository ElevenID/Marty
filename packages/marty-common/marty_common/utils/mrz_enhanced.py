"""
Enhanced MRZ utilities with backward compatibility and hardened parser integration.

This module extends the existing MRZ utilities to support the new hardened parser
while maintaining full backward compatibility with existing code. It provides:
- Drop-in replacements for existing MRZ functions
- Enhanced error handling and validation
- Optional hardened parsing mode
- Seamless migration path for existing integrations

Migration guide:
1. Replace imports: from marty_common.utils.mrz_utils import ...
   with: from marty_common.utils.mrz_enhanced import ...
2. Optionally enable hardened mode: parser = MRZParser(use_hardened=True)
3. Access enhanced validation: result = parser.parse_mrz_with_validation(mrz)
"""

from __future__ import annotations

import logging
import warnings
from typing import Any, Dict, Optional, Union

from marty_common.models.mrz_validation import MRZValidationResult
from marty_common.models.passport import Gender, MRZData
from marty_common.utils.mrz_hardened import (
    HardenedMRZException,
    HardenedMRZParser,
    parse_mrz_simple,
    parse_mrz_with_validation,
)
from marty_common.utils.mrz_utils import MRZException as LegacyMRZException
from marty_common.utils.mrz_utils import MRZFormatter as LegacyMRZFormatter
from marty_common.utils.mrz_utils import MRZParser as LegacyMRZParser

logger = logging.getLogger(__name__)


# Re-export for backward compatibility
MRZException = LegacyMRZException


class MRZParser:
    """
    Enhanced MRZ parser with backward compatibility and optional hardened mode.

    This class provides the same interface as the legacy MRZParser but can optionally
    use the hardened parser for improved validation and error reporting.
    """

    def __init__(self, use_hardened: bool = False, strict_mode: bool = False):
        """
        Initialize MRZ parser.

        Args:
            use_hardened: Whether to use the hardened parser (default: False for compatibility)
            strict_mode: Whether to use strict ICAO compliance (only applies to hardened mode)
        """
        self.use_hardened = use_hardened
        self.strict_mode = strict_mode

        if use_hardened:
            self.hardened_parser = HardenedMRZParser(strict_mode=strict_mode)
        else:
            self.legacy_parser = LegacyMRZParser()

    @staticmethod
    def calculate_check_digit(input_string: str) -> str:
        """Calculate check digit (compatibility method)."""
        return LegacyMRZParser.calculate_check_digit(input_string)

    @staticmethod
    def validate_check_digit(input_string: str, check_digit: str) -> bool:
        """Validate check digit (compatibility method)."""
        return LegacyMRZParser.validate_check_digit(input_string, check_digit)

    @staticmethod
    def clean_name(name: str) -> str:
        """Clean name for MRZ (compatibility method)."""
        return LegacyMRZParser.clean_name(name)

    def parse_td3_mrz(self, mrz: str) -> MRZData:
        """
        Parse TD3 format MRZ with optional hardened validation.

        Args:
            mrz: MRZ string to parse

        Returns:
            MRZData object

        Raises:
            MRZException: If parsing fails
        """
        if self.use_hardened:
            try:
                result = self.hardened_parser.parse_mrz(mrz)
                if result.is_valid and result.parsed_data:
                    # Convert to MRZData for compatibility
                    return self._convert_to_mrz_data(result.parsed_data)
                else:
                    # Collect error messages
                    error_messages = [error.message for error in result.errors]
                    raise MRZException(
                        f"Hardened parser validation failed: {'; '.join(error_messages)}"
                    )
            except HardenedMRZException as e:
                raise MRZException(str(e)) from e
        else:
            return self.legacy_parser.parse_td3_mrz(mrz)

    def parse_td2_mrz(self, mrz: str) -> MRZData:
        """
        Parse TD2 format MRZ with optional hardened validation.

        Args:
            mrz: MRZ string to parse

        Returns:
            MRZData object

        Raises:
            MRZException: If parsing fails
        """
        if self.use_hardened:
            try:
                result = self.hardened_parser.parse_mrz(mrz)
                if result.is_valid and result.parsed_data:
                    return self._convert_to_mrz_data(result.parsed_data)
                else:
                    error_messages = [error.message for error in result.errors]
                    raise MRZException(
                        f"Hardened parser validation failed: {'; '.join(error_messages)}"
                    )
            except HardenedMRZException as e:
                raise MRZException(str(e)) from e
        else:
            return self.legacy_parser.parse_td2_mrz(mrz)

    def parse_td1_mrz(self, mrz: str) -> MRZData:
        """
        Parse TD1 format MRZ with optional hardened validation.

        Args:
            mrz: MRZ string to parse

        Returns:
            MRZData object

        Raises:
            MRZException: If parsing fails
        """
        if self.use_hardened:
            try:
                result = self.hardened_parser.parse_mrz(mrz)
                if result.is_valid and result.parsed_data:
                    return self._convert_to_mrz_data(result.parsed_data)
                else:
                    error_messages = [error.message for error in result.errors]
                    raise MRZException(
                        f"Hardened parser validation failed: {'; '.join(error_messages)}"
                    )
            except HardenedMRZException as e:
                raise MRZException(str(e)) from e
        else:
            return self.legacy_parser.parse_td1_mrz(mrz)

    def parse_mrz(self, mrz: str) -> MRZData:
        """
        Parse MRZ with automatic format detection.

        Args:
            mrz: MRZ string to parse

        Returns:
            MRZData object

        Raises:
            MRZException: If parsing fails
        """
        if self.use_hardened:
            try:
                result = self.hardened_parser.parse_mrz(mrz)
                if result.is_valid and result.parsed_data:
                    return self._convert_to_mrz_data(result.parsed_data)
                else:
                    error_messages = [error.message for error in result.errors]
                    raise MRZException(
                        f"Hardened parser validation failed: {'; '.join(error_messages)}"
                    )
            except HardenedMRZException as e:
                raise MRZException(str(e)) from e
        else:
            return self.legacy_parser.parse_mrz(mrz)

    def parse_mrz_with_validation(self, mrz: str) -> MRZValidationResult:
        """
        Parse MRZ with comprehensive validation (enhanced feature).

        Args:
            mrz: MRZ string to parse

        Returns:
            MRZValidationResult with detailed validation information
        """
        if not self.use_hardened:
            warnings.warn(
                "parse_mrz_with_validation requires hardened mode. "
                "Create parser with use_hardened=True for full validation features.",
                UserWarning,
            )
            # Fallback: convert legacy parsing to validation result
            try:
                mrz_data = self.legacy_parser.parse_mrz(mrz)
                return self._legacy_to_validation_result(mrz, mrz_data, success=True)
            except Exception as e:
                return self._legacy_to_validation_result(mrz, None, success=False, error=str(e))

        return self.hardened_parser.parse_mrz(mrz)

    def _convert_to_mrz_data(self, parsed_data: dict[str, Any]) -> MRZData:
        """Convert hardened parser output to MRZData."""
        return MRZData(
            document_type=parsed_data.get("document_type", ""),
            issuing_country=parsed_data.get("issuing_country", ""),
            document_number=parsed_data.get("document_number", ""),
            surname=parsed_data.get("surname", ""),
            given_names=parsed_data.get("given_names", ""),
            nationality=parsed_data.get("nationality", ""),
            date_of_birth=parsed_data.get("date_of_birth", ""),
            gender=parsed_data.get("gender", Gender.UNSPECIFIED),
            date_of_expiry=parsed_data.get("date_of_expiry", ""),
            personal_number=parsed_data.get("personal_number"),
        )

    def _legacy_to_validation_result(
        self, mrz: str, mrz_data: MRZData | None, success: bool, error: str | None = None
    ) -> MRZValidationResult:
        """Convert legacy parsing result to validation result."""
        from marty_common.models.mrz_validation import MRZErrorCode, MRZValidationError

        result = MRZValidationResult(
            is_valid=success, raw_mrz=mrz, errors=[], warnings=[], field_validations={}
        )

        if success and mrz_data:
            result.parsed_data = (
                mrz_data.to_dict() if hasattr(mrz_data, "to_dict") else mrz_data.__dict__
            )
            result.confidence = 0.8  # Moderate confidence for legacy parsing
        elif error:
            result.errors.append(
                MRZValidationError(
                    code=MRZErrorCode.MALFORMED_MRZ_STRUCTURE,
                    message=f"Legacy parser error: {error}",
                    suggestion="Try using hardened parser mode for better error details",
                )
            )
            result.confidence = 0.0

        return result


class MRZFormatter:
    """Enhanced MRZ formatter with backward compatibility."""

    def __init__(self, use_enhanced: bool = False):
        """
        Initialize MRZ formatter.

        Args:
            use_enhanced: Whether to use enhanced formatting features
        """
        self.use_enhanced = use_enhanced
        self.legacy_formatter = LegacyMRZFormatter()

    @staticmethod
    def format_name(name: str, max_length: int) -> str:
        """Format name for MRZ (compatibility method)."""
        return LegacyMRZFormatter.format_name(name, max_length)

    @staticmethod
    def format_document_number(number: str, total_length: int = 9) -> str:
        """Format document number for MRZ (compatibility method)."""
        return LegacyMRZFormatter.format_document_number(number, total_length)

    def generate_td3_mrz(self, data: MRZData) -> str:
        """Generate TD3 format MRZ string."""
        return self.legacy_formatter.generate_td3_mrz(data)

    def generate_td1_mrz(self, data: MRZData) -> str:
        """Generate TD1 format MRZ string."""
        return self.legacy_formatter.generate_td1_mrz(data)


# Convenience functions for backward compatibility
def parse_mrz(mrz: str, use_hardened: bool = False) -> MRZData:
    """
    Parse MRZ with automatic format detection.

    Args:
        mrz: MRZ string to parse
        use_hardened: Whether to use hardened parser

    Returns:
        MRZData object

    Raises:
        MRZException: If parsing fails
    """
    parser = MRZParser(use_hardened=use_hardened)
    return parser.parse_mrz(mrz)


def parse_td3_mrz(mrz: str, use_hardened: bool = False) -> MRZData:
    """
    Parse TD3 format MRZ.

    Args:
        mrz: MRZ string to parse
        use_hardened: Whether to use hardened parser

    Returns:
        MRZData object

    Raises:
        MRZException: If parsing fails
    """
    parser = MRZParser(use_hardened=use_hardened)
    return parser.parse_td3_mrz(mrz)


def parse_td2_mrz(mrz: str, use_hardened: bool = False) -> MRZData:
    """
    Parse TD2 format MRZ.

    Args:
        mrz: MRZ string to parse
        use_hardened: Whether to use hardened parser

    Returns:
        MRZData object

    Raises:
        MRZException: If parsing fails
    """
    parser = MRZParser(use_hardened=use_hardened)
    return parser.parse_td2_mrz(mrz)


def parse_td1_mrz(mrz: str, use_hardened: bool = False) -> MRZData:
    """
    Parse TD1 format MRZ.

    Args:
        mrz: MRZ string to parse
        use_hardened: Whether to use hardened parser

    Returns:
        MRZData object

    Raises:
        MRZException: If parsing fails
    """
    parser = MRZParser(use_hardened=use_hardened)
    return parser.parse_td1_mrz(mrz)


def validate_mrz(mrz: str, strict_mode: bool = False) -> MRZValidationResult:
    """
    Validate MRZ with comprehensive error reporting.

    Args:
        mrz: MRZ string to validate
        strict_mode: Whether to use strict ICAO compliance

    Returns:
        MRZValidationResult with detailed validation information
    """
    return parse_mrz_with_validation(mrz, strict_mode=strict_mode)


def calculate_check_digit(input_string: str) -> str:
    """Calculate check digit (compatibility function)."""
    return LegacyMRZParser.calculate_check_digit(input_string)


def validate_check_digit(input_string: str, check_digit: str) -> bool:
    """Validate check digit (compatibility function)."""
    return LegacyMRZParser.validate_check_digit(input_string, check_digit)


# Migration utilities
class MRZMigrationHelper:
    """Helper class for migrating to hardened MRZ parser."""

    @staticmethod
    def test_compatibility(mrz_samples: list[str]) -> dict[str, Any]:
        """
        Test compatibility between legacy and hardened parsers.

        Args:
            mrz_samples: List of MRZ strings to test

        Returns:
            Dictionary with compatibility test results
        """
        results = {
            "total_samples": len(mrz_samples),
            "legacy_success": 0,
            "hardened_success": 0,
            "both_success": 0,
            "differences": [],
            "hardened_only_success": [],
            "legacy_only_success": [],
        }

        legacy_parser = MRZParser(use_hardened=False)
        hardened_parser = MRZParser(use_hardened=True, strict_mode=False)

        for i, mrz in enumerate(mrz_samples):
            legacy_success = False
            hardened_success = False
            legacy_data = None
            hardened_data = None

            # Test legacy parser
            try:
                legacy_data = legacy_parser.parse_mrz(mrz)
                legacy_success = True
                results["legacy_success"] += 1
            except Exception as e:
                logger.debug(f"Legacy parser failed on sample {i}: {e}")

            # Test hardened parser
            try:
                hardened_data = hardened_parser.parse_mrz(mrz)
                hardened_success = True
                results["hardened_success"] += 1
            except Exception as e:
                logger.debug(f"Hardened parser failed on sample {i}: {e}")

            # Compare results
            if legacy_success and hardened_success:
                results["both_success"] += 1

                # Check for differences in parsed data
                if legacy_data and hardened_data:
                    differences = MRZMigrationHelper._compare_mrz_data(legacy_data, hardened_data)
                    if differences:
                        results["differences"].append(
                            {"sample_index": i, "mrz": mrz, "differences": differences}
                        )

            elif hardened_success and not legacy_success:
                results["hardened_only_success"].append({"sample_index": i, "mrz": mrz})

            elif legacy_success and not hardened_success:
                results["legacy_only_success"].append({"sample_index": i, "mrz": mrz})

        return results

    @staticmethod
    def _compare_mrz_data(legacy_data: MRZData, hardened_data: MRZData) -> list[str]:
        """Compare two MRZData objects and return differences."""
        differences = []

        fields_to_compare = [
            "document_type",
            "issuing_country",
            "document_number",
            "surname",
            "given_names",
            "nationality",
            "date_of_birth",
            "date_of_expiry",
            "gender",
        ]

        for field in fields_to_compare:
            legacy_value = getattr(legacy_data, field, None)
            hardened_value = getattr(hardened_data, field, None)

            if legacy_value != hardened_value:
                differences.append(
                    f"{field}: legacy='{legacy_value}' vs hardened='{hardened_value}'"
                )

        return differences

    @staticmethod
    def generate_migration_report(compatibility_results: dict[str, Any]) -> str:
        """Generate a migration compatibility report."""
        results = compatibility_results
        total = results["total_samples"]

        report_lines = [
            "MRZ Parser Migration Compatibility Report",
            "=" * 50,
            "",
            f"Total samples tested: {total}",
            f"Legacy parser success rate: {results['legacy_success']}/{total} ({results['legacy_success']/total*100:.1f}%)",
            f"Hardened parser success rate: {results['hardened_success']}/{total} ({results['hardened_success']/total*100:.1f}%)",
            f"Both parsers successful: {results['both_success']}/{total} ({results['both_success']/total*100:.1f}%)",
            "",
            f"Hardened-only successes: {len(results['hardened_only_success'])}",
            f"Legacy-only successes: {len(results['legacy_only_success'])}",
            f"Data differences found: {len(results['differences'])}",
            "",
        ]

        if results["differences"]:
            report_lines.extend(
                [
                    "Data Differences:",
                    "-" * 20,
                ]
            )
            for diff in results["differences"][:5]:  # Show first 5
                report_lines.append(f"Sample {diff['sample_index']}:")
                for difference in diff["differences"]:
                    report_lines.append(f"  {difference}")
                report_lines.append("")

        if results["hardened_only_success"]:
            report_lines.extend(
                [
                    "Samples where only hardened parser succeeded:",
                    "-" * 45,
                ]
            )
            for item in results["hardened_only_success"][:3]:  # Show first 3
                report_lines.append(f"Sample {item['sample_index']}: {item['mrz'][:50]}...")

        return "\n".join(report_lines)
