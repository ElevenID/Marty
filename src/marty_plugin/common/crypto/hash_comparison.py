"""
Hash Comparison and Verification Engine.

This module provides comprehensive hash comparison capabilities for passport
verification, including detailed analysis of mismatches and security implications.
"""

from __future__ import annotations

import binascii
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

# Import from data_group_hasher
# Import HashAlgorithm from sod_parser
from .sod_parser import HashAlgorithm


# Define DataGroupHashResult since it doesn't exist in the module yet
@dataclass
class DataGroupHashResult:
    """Result of data group hash computation."""

    data_group: int
    hash_value: bytes
    algorithm: HashAlgorithm
    success: bool = True
    error_message: str | None = None


# Define DataGroupType enum since it's used for hash comparison validation
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
        """Get human-readable description of the data group."""
        descriptions = {
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
        }
        return descriptions.get(self, f"Unknown data group {self.value}")

    @property
    def is_biometric(self) -> bool:
        """Check if this data group contains biometric data."""
        return self in {
            DataGroupType.DG2_FACE,
            DataGroupType.DG3_FINGERPRINT,
            DataGroupType.DG4_IRIS,
        }

    @property
    def is_mandatory(self) -> bool:
        """Check if this data group is mandatory for passport verification."""
        return self in {DataGroupType.DG1_MRZ, DataGroupType.DG2_FACE}


logger = logging.getLogger(__name__)


class ComparisonResult(Enum):
    """Result types for hash comparison."""

    MATCH = "match"
    MISMATCH = "mismatch"
    MISSING_EXPECTED = "missing_expected"
    MISSING_COMPUTED = "missing_computed"
    ALGORITHM_ERROR = "algorithm_error"


class SeverityLevel(Enum):
    """Severity levels for comparison issues."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class HashComparisonEntry:
    """Individual hash comparison entry."""

    data_group: DataGroupType
    result: ComparisonResult
    severity: SeverityLevel
    expected_hash: bytes | None = None
    computed_hash: bytes | None = None
    algorithm: HashAlgorithm | None = None
    message: str | None = None

    @property
    def expected_hex(self) -> str | None:
        """Get expected hash as hex string."""
        return binascii.hexlify(self.expected_hash).decode().upper() if self.expected_hash else None

    @property
    def computed_hex(self) -> str | None:
        """Get computed hash as hex string."""
        return binascii.hexlify(self.computed_hash).decode().upper() if self.computed_hash else None

    @property
    def is_valid(self) -> bool:
        """Check if this comparison represents a valid state."""
        return self.result == ComparisonResult.MATCH

    @property
    def is_critical_error(self) -> bool:
        """Check if this is a critical security error."""
        return self.severity == SeverityLevel.CRITICAL or (
            self.result == ComparisonResult.MISMATCH and self.data_group.is_mandatory
        )


@dataclass
class IntegrityVerificationReport:
    """Comprehensive integrity verification report."""

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
        """Calculate success rate percentage."""
        if self.total_data_groups == 0:
            return 0.0
        return (self.successful_verifications / self.total_data_groups) * 100.0

    @property
    def has_critical_errors(self) -> bool:
        """Check if there are any critical errors."""
        return self.critical_errors > 0

    @property
    def is_passport_valid(self) -> bool:
        """Determine if passport is valid based on verification."""
        return (
            not self.has_critical_errors
            and self.successful_verifications >= self.mandatory_data_groups_count
            and self.success_rate >= 80.0  # Allow some tolerance for optional DGs
        )

    @property
    def mandatory_data_groups_count(self) -> int:
        """Count mandatory data groups in the verification."""
        return sum(1 for entry in self.comparison_entries if entry.data_group.is_mandatory)

    def get_critical_errors(self) -> list[HashComparisonEntry]:
        """Get list of critical error entries."""
        return [entry for entry in self.comparison_entries if entry.is_critical_error]

    def get_mismatches(self) -> list[HashComparisonEntry]:
        """Get list of hash mismatch entries."""
        return [
            entry for entry in self.comparison_entries if entry.result == ComparisonResult.MISMATCH
        ]

    def to_dict(self) -> dict[str, Any]:
        """Convert report to dictionary format."""
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
    """
    Advanced hash comparison and verification engine.

    This engine provides comprehensive comparison logic with detailed
    reporting, mismatch analysis, and security validation according
    to ICAO standards.
    """

    def __init__(self) -> None:
        """Initialize the comparison engine."""
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    def compare_hashes(
        self,
        computed_hashes: list[DataGroupHashResult],
        expected_hashes: dict[int, bytes],
        algorithm: HashAlgorithm,
    ) -> IntegrityVerificationReport:
        """
        Compare computed hashes against expected values from SOD.

        Args:
            computed_hashes: List of computed hash results
            expected_hashes: Dictionary of DG number -> expected hash bytes
            algorithm: Hash algorithm used

        Returns:
            Comprehensive verification report
        """
        start_time = datetime.now(timezone.utc)
        self._log_comparison_start(computed_hashes, expected_hashes, algorithm)

        # Create lookup for efficient access
        computed_lookup = {result.data_group: result for result in computed_hashes}

        # Process comparisons
        comparison_entries, stats = self._process_hash_comparisons(
            computed_lookup, expected_hashes, algorithm
        )

        # Determine overall status and create report
        overall_status = self._determine_overall_status(stats)
        execution_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

        report = self._create_verification_report(
            start_time, comparison_entries, stats, algorithm, overall_status, execution_time
        )

        self._log_comparison_results(overall_status, stats, execution_time)
        return report

    def _log_comparison_start(
        self,
        computed_hashes: list[DataGroupHashResult],
        expected_hashes: dict[int, bytes],
        algorithm: HashAlgorithm,
    ) -> None:
        """Log the start of hash comparison."""
        self.logger.info(
            "Starting hash comparison for %d computed hashes against %d expected "
            "hashes using %s",
            len(computed_hashes),
            len(expected_hashes),
            algorithm.value,
        )

    def _process_hash_comparisons(
        self,
        computed_lookup: dict[int, DataGroupHashResult],
        expected_hashes: dict[int, bytes],
        algorithm: HashAlgorithm,
    ) -> tuple[list[HashComparisonEntry], dict[str, int]]:
        """Process all hash comparisons and return entries and statistics."""
        comparison_entries = []
        stats = {"successful": 0, "failed": 0, "critical": 0, "warnings": 0}

        # Process expected hashes
        for dg_number, expected_hash in expected_hashes.items():
            entry, entry_stats = self._process_expected_hash(
                dg_number, expected_hash, computed_lookup, algorithm
            )
            if entry:
                comparison_entries.append(entry)
                self._update_stats(stats, entry_stats)

        # Process computed hashes without expected values
        for dg_number, computed_result in computed_lookup.items():
            if dg_number not in expected_hashes:
                entry = self._create_missing_expected_entry(computed_result, algorithm)
                comparison_entries.append(entry)

        return comparison_entries, stats

    def _process_expected_hash(
        self,
        dg_number: int,
        expected_hash: bytes,
        computed_lookup: dict[int, DataGroupHashResult],
        algorithm: HashAlgorithm,
    ) -> tuple[HashComparisonEntry | None, dict[str, int]]:
        """Process a single expected hash entry."""
        try:
            dg_type = DataGroupType(dg_number)
        except ValueError:
            self.logger.warning("Unknown data group number in SOD: %d", dg_number)
            return None, {}

        if dg_number in computed_lookup:
            # Compare expected vs computed
            computed_result = computed_lookup[dg_number]
            entry = self._compare_single_hash(dg_type, expected_hash, computed_result, algorithm)

            if entry.is_valid:
                return entry, {"successful": 1}
            stats = {"failed": 1}
            if entry.is_critical_error:
                stats["critical"] = 1
            else:
                stats["warnings"] = 1
            return entry, stats
        # Missing computed hash
        entry = self._create_missing_computed_entry(dg_type, expected_hash, algorithm)
        stats = {"failed": 1}
        if entry.is_critical_error:
            stats["critical"] = 1
        else:
            stats["warnings"] = 1
        return entry, stats

    def _create_missing_computed_entry(
        self, dg_type: DataGroupType, expected_hash: bytes, algorithm: HashAlgorithm
    ) -> HashComparisonEntry:
        """Create entry for missing computed hash."""
        return HashComparisonEntry(
            data_group=dg_type,
            result=ComparisonResult.MISSING_COMPUTED,
            severity=(SeverityLevel.CRITICAL if dg_type.is_mandatory else SeverityLevel.WARNING),
            expected_hash=expected_hash,
            algorithm=algorithm,
            message=f"Computed hash missing for {dg_type.description}",
        )

    def _create_missing_expected_entry(
        self, computed_result: DataGroupHashResult, algorithm: HashAlgorithm
    ) -> HashComparisonEntry:
        """Create entry for missing expected hash."""
        try:
            dg_type = DataGroupType(computed_result.data_group)
        except ValueError:
            # Fallback for unknown data group numbers
            dg_type = DataGroupType.DG1_MRZ  # Use a default, but this shouldn't happen
        return HashComparisonEntry(
            data_group=dg_type,
            result=ComparisonResult.MISSING_EXPECTED,
            severity=SeverityLevel.INFO,
            computed_hash=computed_result.hash_value,
            algorithm=algorithm,
            message=f"No expected hash in SOD for {dg_type.description}",
        )

    def _update_stats(self, stats: dict[str, int], entry_stats: dict[str, int]) -> None:
        """Update statistics counters."""
        for key, value in entry_stats.items():
            stats[key] = stats.get(key, 0) + value

    def _determine_overall_status(self, stats: dict[str, int]) -> str:
        """Determine overall verification status."""
        critical_errors = stats.get("critical", 0)
        failed_verifications = stats.get("failed", 0)
        successful_verifications = stats.get("successful", 0)
        warnings = stats.get("warnings", 0)

        if critical_errors > 0:
            return "FAILED - Critical errors detected"
        if failed_verifications > successful_verifications:
            return "FAILED - More failures than successes"
        if warnings > 0:
            return "PASSED - With warnings"
        return "PASSED - All verifications successful"

    def _create_verification_report(
        self,
        start_time: datetime,
        comparison_entries: list[HashComparisonEntry],
        stats: dict[str, int],
        algorithm: HashAlgorithm,
        overall_status: str,
        execution_time: float,
    ) -> IntegrityVerificationReport:
        """Create the final verification report."""
        return IntegrityVerificationReport(
            timestamp=start_time,
            total_data_groups=len(comparison_entries),
            successful_verifications=stats.get("successful", 0),
            failed_verifications=stats.get("failed", 0),
            critical_errors=stats.get("critical", 0),
            warnings=stats.get("warnings", 0),
            algorithm_used=algorithm,
            comparison_entries=sorted(comparison_entries, key=lambda e: e.data_group.value),
            overall_status=overall_status,
            execution_time_ms=execution_time,
        )

    def _log_comparison_results(
        self, overall_status: str, stats: dict[str, int], execution_time: float
    ) -> None:
        """Log the final comparison results."""
        self.logger.info(
            "Hash comparison completed: %s (%d successful, %d failed, %d critical) " "in %.2fms",
            overall_status,
            stats.get("successful", 0),
            stats.get("failed", 0),
            stats.get("critical", 0),
            execution_time,
        )

    def _compare_single_hash(
        self,
        dg_type: DataGroupType,
        expected_hash: bytes,
        computed_result: DataGroupHashResult,
        algorithm: HashAlgorithm,
    ) -> HashComparisonEntry:
        """Compare a single hash pair."""

        # Verify algorithm consistency
        if computed_result.algorithm != algorithm:
            return HashComparisonEntry(
                data_group=dg_type,
                result=ComparisonResult.ALGORITHM_ERROR,
                severity=SeverityLevel.ERROR,
                expected_hash=expected_hash,
                computed_hash=computed_result.hash_value,
                algorithm=algorithm,
                message=(
                    f"Algorithm mismatch: expected {algorithm.value}, "
                    f"got {computed_result.algorithm.value}"
                ),
            )

        # Verify hash sizes match
        if len(expected_hash) != len(computed_result.hash_value):
            return HashComparisonEntry(
                data_group=dg_type,
                result=ComparisonResult.MISMATCH,
                severity=SeverityLevel.CRITICAL,
                expected_hash=expected_hash,
                computed_hash=computed_result.hash_value,
                algorithm=algorithm,
                message=(
                    f"Hash size mismatch: expected {len(expected_hash)} bytes, "
                    f"got {len(computed_result.hash_value)} bytes"
                ),
            )

        # Compare hash values
        if expected_hash == computed_result.hash_value:
            return HashComparisonEntry(
                data_group=dg_type,
                result=ComparisonResult.MATCH,
                severity=SeverityLevel.INFO,
                expected_hash=expected_hash,
                computed_hash=computed_result.hash_value,
                algorithm=algorithm,
                message=f"Hash verification successful for {dg_type.description}",
            )
        severity = SeverityLevel.CRITICAL if dg_type.is_mandatory else SeverityLevel.WARNING
        return HashComparisonEntry(
            data_group=dg_type,
            result=ComparisonResult.MISMATCH,
            severity=severity,
            expected_hash=expected_hash,
            computed_hash=computed_result.hash_value,
            algorithm=algorithm,
            message=f"Hash mismatch detected for {dg_type.description}",
        )

    def generate_detailed_mismatch_report(
        self, report: IntegrityVerificationReport
    ) -> dict[str, Any]:
        """
        Generate detailed analysis of hash mismatches.

        Args:
            report: Integrity verification report

        Returns:
            Detailed mismatch analysis
        """
        mismatches = report.get_mismatches()

        if not mismatches:
            return {
                "summary": "No hash mismatches detected",
                "total_mismatches": 0,
                "analysis": "All data group hashes match their expected values",
            }

        mismatch_analysis = {
            "summary": f"{len(mismatches)} hash mismatches detected",
            "total_mismatches": len(mismatches),
            "critical_mismatches": sum(1 for m in mismatches if m.is_critical_error),
            "mandatory_dg_mismatches": sum(1 for m in mismatches if m.data_group.is_mandatory),
            "biometric_dg_mismatches": sum(1 for m in mismatches if m.data_group.is_biometric),
            "detailed_mismatches": [],
        }

        for mismatch in mismatches:
            # Analyze the type of mismatch
            mismatch_type = "unknown"
            if mismatch.expected_hash and mismatch.computed_hash:
                if len(mismatch.expected_hash) != len(mismatch.computed_hash):
                    mismatch_type = "size_mismatch"
                else:
                    # Check if it's completely different or partially similar
                    matching_bytes = sum(
                        1
                        for i in range(len(mismatch.expected_hash))
                        if mismatch.expected_hash[i] == mismatch.computed_hash[i]
                    )
                    similarity_percent = (matching_bytes / len(mismatch.expected_hash)) * 100

                    if similarity_percent < 10:
                        mismatch_type = "completely_different"
                    elif similarity_percent < 50:
                        mismatch_type = "partially_different"
                    else:
                        mismatch_type = "minor_difference"

            mismatch_detail = {
                "data_group": mismatch.data_group.name,
                "description": mismatch.data_group.description,
                "mismatch_type": mismatch_type,
                "severity": mismatch.severity.value,
                "is_mandatory": mismatch.data_group.is_mandatory,
                "is_biometric": mismatch.data_group.is_biometric,
                "expected_hash": mismatch.expected_hex,
                "computed_hash": mismatch.computed_hex,
                "hash_size_bytes": len(mismatch.expected_hash) if mismatch.expected_hash else 0,
            }

            if (
                mismatch_type in ["partially_different", "minor_difference"]
                and mismatch.expected_hash
                and mismatch.computed_hash
            ):
                # Add similarity analysis for partially matching hashes
                min_len = min(len(mismatch.expected_hash), len(mismatch.computed_hash))
                matching_bytes = sum(
                    1
                    for i in range(min_len)
                    if mismatch.expected_hash[i] == mismatch.computed_hash[i]
                )
                total_bytes = max(len(mismatch.expected_hash), len(mismatch.computed_hash))
                mismatch_detail["similarity_analysis"] = {
                    "matching_bytes": matching_bytes,
                    "total_bytes": total_bytes,
                    "similarity_percent": round((matching_bytes / total_bytes) * 100, 2),
                }

            mismatch_analysis["detailed_mismatches"].append(mismatch_detail)

        # Add security implications
        mismatch_analysis["security_implications"] = self._assess_security_implications(mismatches)

        return mismatch_analysis

    def _assess_security_implications(
        self, mismatches: list[HashComparisonEntry]
    ) -> dict[str, Any]:
        """Assess security implications of hash mismatches."""

        critical_count = sum(1 for m in mismatches if m.is_critical_error)
        mandatory_count = sum(1 for m in mismatches if m.data_group.is_mandatory)
        biometric_count = sum(1 for m in mismatches if m.data_group.is_biometric)

        # Determine overall security risk
        if critical_count > 0 or mandatory_count > 0:
            risk_level = "HIGH"
            risk_description = "Critical security risk - mandatory data groups compromised"
        elif biometric_count > 0:
            risk_level = "MEDIUM"
            risk_description = "Moderate security risk - biometric data integrity compromised"
        elif len(mismatches) > 3:
            risk_level = "MEDIUM"
            risk_description = "Moderate security risk - multiple data groups affected"
        else:
            risk_level = "LOW"
            risk_description = "Low security risk - limited impact to optional data groups"

        return {
            "risk_level": risk_level,
            "risk_description": risk_description,
            "affected_mandatory_dgs": mandatory_count,
            "affected_biometric_dgs": biometric_count,
            "total_affected_dgs": len(mismatches),
            "recommendations": self._generate_security_recommendations(risk_level, mismatches),
        }

    def _generate_security_recommendations(
        self, risk_level: str, mismatches: list[HashComparisonEntry]
    ) -> list[str]:
        """Generate security recommendations based on mismatch analysis."""

        recommendations = []

        if risk_level == "HIGH":
            recommendations.extend(
                [
                    "REJECT passport - critical security failure detected",
                    "Verify passport authenticity through alternative means",
                    "Report potential document tampering to authorities",
                    "Do not rely on digital verification for this document",
                ]
            )
        elif risk_level == "MEDIUM":
            recommendations.extend(
                [
                    "Exercise caution - moderate security concerns detected",
                    "Perform additional manual verification steps",
                    "Consider secondary authentication methods",
                    "Review biometric data integrity if affected",
                ]
            )
        else:  # LOW risk
            recommendations.extend(
                [
                    "Proceed with caution - minor integrity issues detected",
                    "Document findings for audit trail",
                    "Consider re-scanning if possible",
                ]
            )

        # Add specific recommendations based on affected data groups
        mandatory_mismatches = [m for m in mismatches if m.data_group.is_mandatory]
        if mandatory_mismatches:
            dg_names = ", ".join(m.data_group.name for m in mandatory_mismatches)
            recommendations.append(f"Pay special attention to mandatory data groups: {dg_names}")

        biometric_mismatches = [m for m in mismatches if m.data_group.is_biometric]
        if biometric_mismatches:
            dg_names = ", ".join(m.data_group.name for m in biometric_mismatches)
            recommendations.append(f"Verify biometric data independently: {dg_names}")

        return recommendations


# Convenience functions
def compare_passport_hashes(
    computed_hashes: list[DataGroupHashResult],
    expected_hashes: dict[int, bytes],
    algorithm: HashAlgorithm = HashAlgorithm.SHA256,
) -> IntegrityVerificationReport:
    """Compare passport hashes using default engine."""
    engine = HashComparisonEngine()
    return engine.compare_hashes(computed_hashes, expected_hashes, algorithm)


def generate_verification_report_json(
    report: IntegrityVerificationReport, include_mismatch_analysis: bool = True
) -> str:
    """Generate JSON verification report."""
    report_dict = report.to_dict()

    if include_mismatch_analysis and not report.is_passport_valid:
        engine = HashComparisonEngine()
        mismatch_analysis = engine.generate_detailed_mismatch_report(report)
        report_dict["mismatch_analysis"] = mismatch_analysis

    return json.dumps(report_dict, indent=2, ensure_ascii=False)
