"""Backward-compatible entry points for native ICAO MRZ processing."""

from __future__ import annotations

from typing import Any

from marty_common.models.mrz_validation import MRZValidationResult
from marty_common.models.passport import MRZData
from marty_common.utils.mrz_hardened import parse_mrz_with_validation
from marty_common.utils.mrz_utils import (
    MRZException,
    MRZFormatter,
)
from marty_common.utils.mrz_utils import (
    MRZParser as NativeMRZParser,
)


class MRZParser:
    """Compatibility class whose parsing paths all delegate to Rust."""

    def __init__(self, use_hardened: bool = False, strict_mode: bool = False) -> None:
        self.use_hardened = use_hardened
        self.strict_mode = strict_mode

    calculate_check_digit = staticmethod(NativeMRZParser.calculate_check_digit)
    validate_check_digit = staticmethod(NativeMRZParser.validate_check_digit)
    clean_name = staticmethod(NativeMRZParser.clean_name)

    def parse_mrz(self, mrz: str) -> MRZData:
        return NativeMRZParser._parse(mrz)

    def parse_td1_mrz(self, mrz: str) -> MRZData:
        return NativeMRZParser._parse(mrz, "TD1")

    def parse_td2_mrz(self, mrz: str) -> MRZData:
        return NativeMRZParser._parse(mrz, "TD2")

    def parse_td3_mrz(self, mrz: str) -> MRZData:
        return NativeMRZParser._parse(mrz, "TD3")

    def parse_mrz_with_validation(self, mrz: str) -> MRZValidationResult:
        return parse_mrz_with_validation(mrz, strict_mode=self.strict_mode)


def parse_mrz(mrz: str, use_hardened: bool = False) -> MRZData:
    return MRZParser(use_hardened=use_hardened).parse_mrz(mrz)


def parse_td1_mrz(mrz: str, use_hardened: bool = False) -> MRZData:
    return MRZParser(use_hardened=use_hardened).parse_td1_mrz(mrz)


def parse_td2_mrz(mrz: str, use_hardened: bool = False) -> MRZData:
    return MRZParser(use_hardened=use_hardened).parse_td2_mrz(mrz)


def parse_td3_mrz(mrz: str, use_hardened: bool = False) -> MRZData:
    return MRZParser(use_hardened=use_hardened).parse_td3_mrz(mrz)


def validate_mrz(mrz: str, strict_mode: bool = False) -> MRZValidationResult:
    return parse_mrz_with_validation(mrz, strict_mode=strict_mode)


def calculate_check_digit(input_string: str) -> str:
    return NativeMRZParser.calculate_check_digit(input_string)


def validate_check_digit(input_string: str, check_digit: str) -> bool:
    return NativeMRZParser.validate_check_digit(input_string, check_digit)


class MRZMigrationHelper:
    """Compatibility report helper comparing the same authoritative parser."""

    @staticmethod
    def test_compatibility(mrz_samples: list[str]) -> dict[str, Any]:
        successes = 0
        differences: list[dict[str, Any]] = []
        for index, sample in enumerate(mrz_samples):
            try:
                parse_mrz(sample)
                successes += 1
            except MRZException as exc:
                differences.append({"sample_index": index, "error": str(exc)})
        return {
            "total_samples": len(mrz_samples),
            "legacy_success": successes,
            "hardened_success": successes,
            "both_success": successes,
            "differences": differences,
            "hardened_only_success": [],
            "legacy_only_success": [],
        }

    @staticmethod
    def generate_migration_report(compatibility_results: dict[str, Any]) -> str:
        total = compatibility_results["total_samples"]
        success = compatibility_results["both_success"]
        return f"Native MRZ compatibility: {success}/{total} samples accepted"


__all__ = [
    "MRZException",
    "MRZFormatter",
    "MRZMigrationHelper",
    "MRZParser",
    "calculate_check_digit",
    "parse_mrz",
    "parse_td1_mrz",
    "parse_td2_mrz",
    "parse_td3_mrz",
    "validate_check_digit",
    "validate_mrz",
]
