"""Compatibility models for native eMRTD data-group integrity reporting.

All comparison, classification, and security-risk decisions are made by the
canonical ``marty_verification`` Rust extension.  This module only preserves
the established Python model and JSON surfaces.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from time import perf_counter
from typing import Any

from marty_common.native_backends import load_native_backend

from .sod_parser import HashAlgorithm


def _native():
    return load_native_backend("marty_verification", ("compare_passport_hashes_json",))


@dataclass
class DataGroupHashResult:
    """Result of data-group hash computation."""

    data_group: int
    hash_value: bytes
    algorithm: HashAlgorithm
    success: bool = True
    error_message: str | None = None


class DataGroupType(Enum):
    DG1_MRZ = 1
    DG2_FACE = 2
    DG3_FINGERPRINT = 3
    DG4_IRIS = 4
    DG5_PORTRAIT = 5
    DG6_RESERVED = 6
    DG7_SIGNATURE = 7
    DG8_DATA_FEATURES = 8
    DG9_STRUCTURE_FEATURES = 9
    DG10_SUBSTANCE_FEATURES = 10
    DG11_ADDITIONAL_PERSONAL = 11
    DG12_ADDITIONAL_DOCUMENT = 12
    DG13_OPTIONAL_DETAILS = 13
    DG14_SECURITY_INFOS = 14
    DG15_ACTIVE_AUTH = 15

    @property
    def description(self) -> str:
        return {
            DataGroupType.DG1_MRZ: "Machine Readable Zone (MRZ) data",
            DataGroupType.DG2_FACE: "Encoded face biometric data",
            DataGroupType.DG3_FINGERPRINT: "Encoded fingerprint biometric data",
            DataGroupType.DG4_IRIS: "Encoded iris biometric data",
            DataGroupType.DG5_PORTRAIT: "Displayed portrait image",
            DataGroupType.DG6_RESERVED: "Reserved for future use",
            DataGroupType.DG7_SIGNATURE: "Displayed signature or mark",
            DataGroupType.DG8_DATA_FEATURES: "Data features",
            DataGroupType.DG9_STRUCTURE_FEATURES: "Structure features",
            DataGroupType.DG10_SUBSTANCE_FEATURES: "Substance features",
            DataGroupType.DG11_ADDITIONAL_PERSONAL: "Additional personal details",
            DataGroupType.DG12_ADDITIONAL_DOCUMENT: "Additional document details",
            DataGroupType.DG13_OPTIONAL_DETAILS: "Optional details",
            DataGroupType.DG14_SECURITY_INFOS: "Security infos",
            DataGroupType.DG15_ACTIVE_AUTH: "Active authentication public key info",
        }[self]

    @property
    def is_biometric(self) -> bool:
        return self in {
            DataGroupType.DG2_FACE,
            DataGroupType.DG3_FINGERPRINT,
            DataGroupType.DG4_IRIS,
        }

    @property
    def is_mandatory(self) -> bool:
        return self in {DataGroupType.DG1_MRZ, DataGroupType.DG2_FACE}


class ComparisonResult(Enum):
    MATCH = "match"
    MISMATCH = "mismatch"
    MISSING_EXPECTED = "missing_expected"
    MISSING_COMPUTED = "missing_computed"
    ALGORITHM_ERROR = "algorithm_error"


class SeverityLevel(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class HashComparisonEntry:
    data_group: DataGroupType
    result: ComparisonResult
    severity: SeverityLevel
    expected_hash: bytes | None = None
    computed_hash: bytes | None = None
    algorithm: HashAlgorithm | None = None
    message: str | None = None

    @property
    def expected_hex(self) -> str | None:
        return self.expected_hash.hex().upper() if self.expected_hash else None

    @property
    def computed_hex(self) -> str | None:
        return self.computed_hash.hex().upper() if self.computed_hash else None

    @property
    def is_valid(self) -> bool:
        return self.result == ComparisonResult.MATCH

    @property
    def is_critical_error(self) -> bool:
        return self.severity == SeverityLevel.CRITICAL or (
            self.result == ComparisonResult.MISMATCH and self.data_group.is_mandatory
        )


@dataclass
class IntegrityVerificationReport:
    timestamp: datetime
    total_data_groups: int
    successful_verifications: int
    failed_verifications: int
    critical_errors: int
    warnings: int
    algorithm_used: HashAlgorithm
    comparison_entries: list[HashComparisonEntry]
    overall_status: str
    execution_time_ms: float

    @property
    def success_rate(self) -> float:
        if self.total_data_groups == 0:
            return 0.0
        return (self.successful_verifications / self.total_data_groups) * 100.0

    @property
    def has_critical_errors(self) -> bool:
        return self.critical_errors > 0

    @property
    def is_passport_valid(self) -> bool:
        return (
            not self.has_critical_errors
            and self.successful_verifications >= self.mandatory_data_groups_count
            and self.success_rate >= 80.0
        )

    @property
    def mandatory_data_groups_count(self) -> int:
        return sum(1 for entry in self.comparison_entries if entry.data_group.is_mandatory)

    def get_critical_errors(self) -> list[HashComparisonEntry]:
        return [entry for entry in self.comparison_entries if entry.is_critical_error]

    def get_mismatches(self) -> list[HashComparisonEntry]:
        return [
            entry for entry in self.comparison_entries if entry.result == ComparisonResult.MISMATCH
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "summary": {
                "total_data_groups": self.total_data_groups,
                "successful_verifications": self.successful_verifications,
                "failed_verifications": self.failed_verifications,
                "success_rate_percent": round(self.success_rate, 2),
                "critical_errors": self.critical_errors,
                "warnings": self.warnings,
                "overall_status": self.overall_status,
                "is_passport_valid": self.is_passport_valid,
                "execution_time_ms": self.execution_time_ms,
            },
            "algorithm": self.algorithm_used.value,
            "mandatory_data_groups": self.mandatory_data_groups_count,
            "verification_details": [
                {
                    "data_group": entry.data_group.name,
                    "description": entry.data_group.description,
                    "result": entry.result.value,
                    "severity": entry.severity.value,
                    "is_mandatory": entry.data_group.is_mandatory,
                    "is_biometric": entry.data_group.is_biometric,
                    "expected_hash": entry.expected_hex,
                    "computed_hash": entry.computed_hex,
                    "message": entry.message,
                    "is_valid": entry.is_valid,
                }
                for entry in self.comparison_entries
            ],
        }


class HashComparisonEngine:
    """Native-backed hash comparison and verification engine."""

    def compare_hashes(
        self,
        computed_hashes: list[DataGroupHashResult],
        expected_hashes: dict[int, bytes],
        algorithm: HashAlgorithm,
    ) -> IntegrityVerificationReport:
        started_at = datetime.now(UTC)
        started = perf_counter()
        request = {
            "algorithm": algorithm.value,
            "expected_hashes": {str(key): value.hex() for key, value in expected_hashes.items()},
            "computed_hashes": [
                {
                    "data_group": item.data_group,
                    "hash": item.hash_value.hex(),
                    "algorithm": item.algorithm.value,
                    "success": item.success,
                    "error_message": item.error_message,
                }
                for item in computed_hashes
            ],
        }
        native = json.loads(_native().compare_passport_hashes_json(json.dumps(request)))
        entries = [
            HashComparisonEntry(
                data_group=DataGroupType(item["data_group"]),
                result=ComparisonResult(item["result"]),
                severity=SeverityLevel(item["severity"]),
                expected_hash=(
                    bytes.fromhex(item["expected_hash"]) if item["expected_hash"] else None
                ),
                computed_hash=(
                    bytes.fromhex(item["computed_hash"]) if item["computed_hash"] else None
                ),
                algorithm=HashAlgorithm(item["algorithm"]),
                message=item["message"],
            )
            for item in native["comparison_entries"]
        ]
        report = IntegrityVerificationReport(
            timestamp=started_at,
            total_data_groups=native["total_data_groups"],
            successful_verifications=native["successful_verifications"],
            failed_verifications=native["failed_verifications"],
            critical_errors=native["critical_errors"],
            warnings=native["warnings"],
            algorithm_used=HashAlgorithm(native["algorithm"]),
            comparison_entries=entries,
            overall_status=native["overall_status"],
            execution_time_ms=(perf_counter() - started) * 1000,
        )
        report._native_mismatch_analysis = native["mismatch_analysis"]  # type: ignore[attr-defined]
        return report

    def generate_detailed_mismatch_report(
        self, report: IntegrityVerificationReport
    ) -> dict[str, Any]:
        analysis = getattr(report, "_native_mismatch_analysis", None)
        if analysis is None:
            raise ValueError("Report was not produced by the native comparison engine")
        return analysis


def compare_passport_hashes(
    computed_hashes: list[DataGroupHashResult],
    expected_hashes: dict[int, bytes],
    algorithm: HashAlgorithm = HashAlgorithm.SHA256,
) -> IntegrityVerificationReport:
    return HashComparisonEngine().compare_hashes(computed_hashes, expected_hashes, algorithm)


def generate_verification_report_json(
    report: IntegrityVerificationReport, include_mismatch_analysis: bool = True
) -> str:
    report_dict = report.to_dict()
    if include_mismatch_analysis and not report.is_passport_valid:
        report_dict["mismatch_analysis"] = HashComparisonEngine().generate_detailed_mismatch_report(
            report
        )
    return json.dumps(report_dict, indent=2, ensure_ascii=False)


__all__ = [
    "ComparisonResult",
    "DataGroupHashResult",
    "DataGroupType",
    "HashComparisonEngine",
    "HashComparisonEntry",
    "IntegrityVerificationReport",
    "SeverityLevel",
    "compare_passport_hashes",
    "generate_verification_report_json",
]
