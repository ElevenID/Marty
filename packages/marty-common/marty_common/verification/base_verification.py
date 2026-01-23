"""
Base verification engine and shared utilities for document verification.

This module provides common patterns and base classes to reduce redundancy
across different document verification implementations (CMC, Visa, TD2, etc.).
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class VerificationStep(str, Enum):
    """Common verification step identifiers."""

    DOCUMENT_DETECTION = "document_detection"
    MRZ_PARSE = "mrz_parse"
    CHECK_DIGITS = "check_digits"
    CHIP_VERIFICATION = "chip_verification"
    SOD_VERIFICATION = "sod_verification"
    VDS_NC_DECODE = "vds_nc_decode"
    SIGNATURE_VERIFY = "signature_verify"
    FIELD_CONSISTENCY = "field_consistency"
    AUTHENTICITY_CHECK = "authenticity_check"
    SEMANTICS_CHECK = "semantics_check"
    POLICY_CHECK = "policy_check"
    TRUST_VERIFICATION = "trust_verification"
    ONLINE_VERIFY = "online_verify"


class VerificationLevel(str, Enum):
    """Standard verification thoroughness levels."""

    BASIC = "basic"  # Document detection + MRZ only
    STANDARD = "standard"  # Basic + authenticity
    COMPREHENSIVE = "comprehensive"  # Standard + semantics + policy
    MAXIMUM = "maximum"  # Comprehensive + trust + online


class VerificationStatus(str, Enum):
    """Status of verification steps."""

    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"
    NOT_APPLICABLE = "not_applicable"


@dataclass
class VerificationStepResult:
    """Result of a single verification step."""

    step: VerificationStep
    status: VerificationStatus
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0  # 0.0 - 1.0


@dataclass
class BaseVerificationResult:
    """Base verification result structure."""

    is_valid: bool = False
    overall_confidence: float = 0.0
    verification_timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    step_results: list[VerificationStepResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_step_result(
        self,
        step: VerificationStep,
        status: VerificationStatus,
        message: str = "",
        details: dict[str, Any] | None = None,
        confidence: float = 1.0,
    ) -> None:
        """Add a verification step result."""
        result = VerificationStepResult(
            step=step, status=status, message=message, details=details or {}, confidence=confidence
        )
        self.step_results.append(result)

        # Update overall status
        if status == VerificationStatus.FAILED:
            self.is_valid = False
            self.errors.append(f"{step.value}: {message}")
        elif status == VerificationStatus.WARNING:
            self.warnings.append(f"{step.value}: {message}")

    def get_step_result(self, step: VerificationStep) -> VerificationStepResult | None:
        """Get result for a specific step."""
        for result in self.step_results:
            if result.step == step:
                return result
        return None

    def calculate_overall_confidence(self) -> float:
        """Calculate overall confidence based on step results."""
        if not self.step_results:
            return 0.0

        weights = {
            VerificationStep.DOCUMENT_DETECTION: 0.1,
            VerificationStep.MRZ_PARSE: 0.15,
            VerificationStep.CHECK_DIGITS: 0.15,
            VerificationStep.AUTHENTICITY_CHECK: 0.25,
            VerificationStep.SEMANTICS_CHECK: 0.15,
            VerificationStep.TRUST_VERIFICATION: 0.2,
        }

        total_weighted_confidence = 0.0
        total_weight = 0.0

        for result in self.step_results:
            weight = weights.get(result.step, 0.1)
            if result.status == VerificationStatus.PASSED:
                total_weighted_confidence += result.confidence * weight
            elif result.status == VerificationStatus.WARNING:
                total_weighted_confidence += result.confidence * weight * 0.7
            # Failed steps contribute 0
            total_weight += weight

        self.overall_confidence = (
            total_weighted_confidence / total_weight if total_weight > 0 else 0.0
        )
        return self.overall_confidence


class DocumentProtocol(Protocol):
    """Protocol for document objects."""

    @property
    def document_type(self) -> str:
        """Document type identifier."""
        ...


class BaseVerificationEngine(ABC):
    """Base class for document verification engines."""

    def __init__(
        self,
        trust_store_path: str | None = None,
        enable_online_verification: bool = False,
        verification_timeout: int = 30,
    ) -> None:
        self.trust_store_path = trust_store_path
        self.enable_online_verification = enable_online_verification
        self.verification_timeout = verification_timeout
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    async def verify_document(
        self,
        document: DocumentProtocol,
        verification_level: VerificationLevel = VerificationLevel.STANDARD,
        **kwargs: Any,
    ) -> BaseVerificationResult:
        """Verify a document with the specified level."""
        ...

    async def verify_mrz_structure(
        self, mrz_data: str | list[str], document_type: str
    ) -> VerificationStepResult:
        """Common MRZ structure verification."""
        try:
            # Basic structure checks
            lines = mrz_data.strip().split("\n") if isinstance(mrz_data, str) else mrz_data

            if not lines or not any(line.strip() for line in lines):
                return VerificationStepResult(
                    step=VerificationStep.MRZ_PARSE,
                    status=VerificationStatus.FAILED,
                    message="MRZ data is empty or invalid",
                )

            # Document-specific line count validation
            expected_lines = self._get_expected_mrz_lines(document_type)
            if len(lines) != expected_lines:
                return VerificationStepResult(
                    step=VerificationStep.MRZ_PARSE,
                    status=VerificationStatus.FAILED,
                    message=f"Expected {expected_lines} MRZ lines, got {len(lines)}",
                )

            return VerificationStepResult(
                step=VerificationStep.MRZ_PARSE,
                status=VerificationStatus.PASSED,
                message="MRZ structure validation passed",
            )

        except Exception as e:
            self.logger.exception("MRZ structure verification failed")
            return VerificationStepResult(
                step=VerificationStep.MRZ_PARSE,
                status=VerificationStatus.FAILED,
                message=f"MRZ parsing error: {e}",
            )

    def _get_expected_mrz_lines(self, document_type: str) -> int:
        """Get expected number of MRZ lines for document type."""
        mrz_line_map = {
            "passport": 2,  # TD-3
            "visa": 2,  # MRV
            "id_card": 3,  # TD-1
            "td2": 2,  # TD-2
            "cmc": 2,  # CMC
        }
        return mrz_line_map.get(document_type.lower(), 2)

    async def verify_date_validity(
        self, issue_date: date | None, expiry_date: date | None, validity_date: date | None = None
    ) -> VerificationStepResult:
        """Common date validity verification."""
        check_date = validity_date or date.today()

        try:
            if expiry_date and expiry_date < check_date:
                return VerificationStepResult(
                    step=VerificationStep.SEMANTICS_CHECK,
                    status=VerificationStatus.FAILED,
                    message=f"Document expired on {expiry_date}",
                    details={"expiry_date": expiry_date.isoformat()},
                )

            if issue_date and issue_date > check_date:
                return VerificationStepResult(
                    step=VerificationStep.SEMANTICS_CHECK,
                    status=VerificationStatus.FAILED,
                    message=f"Document issue date {issue_date} is in the future",
                    details={"issue_date": issue_date.isoformat()},
                )

            # Check if expiring soon (within 6 months)
            if expiry_date:
                days_until_expiry = (expiry_date - check_date).days
                if 0 < days_until_expiry <= 180:
                    return VerificationStepResult(
                        step=VerificationStep.SEMANTICS_CHECK,
                        status=VerificationStatus.WARNING,
                        message=f"Document expires in {days_until_expiry} days",
                        details={"days_until_expiry": days_until_expiry},
                    )

            return VerificationStepResult(
                step=VerificationStep.SEMANTICS_CHECK,
                status=VerificationStatus.PASSED,
                message="Date validity checks passed",
            )

        except Exception as e:
            self.logger.exception("Date validity verification failed")
            return VerificationStepResult(
                step=VerificationStep.SEMANTICS_CHECK,
                status=VerificationStatus.FAILED,
                message=f"Date validation error: {e}",
            )

    async def verify_check_digits(
        self,
        data_fields: list[tuple[str, str]],  # (field_name, field_value_with_check_digit)
        algorithm: str = "mod10",
    ) -> VerificationStepResult:
        """Common check digit verification."""
        try:
            for field_name, field_value in data_fields:
                if not self._validate_check_digit(field_value, algorithm):
                    return VerificationStepResult(
                        step=VerificationStep.CHECK_DIGITS,
                        status=VerificationStatus.FAILED,
                        message=f"Check digit validation failed for {field_name}",
                        details={"field": field_name, "value": field_value},
                    )

            return VerificationStepResult(
                step=VerificationStep.CHECK_DIGITS,
                status=VerificationStatus.PASSED,
                message="All check digits are valid",
            )

        except Exception as e:
            self.logger.exception("Check digit verification failed")
            return VerificationStepResult(
                step=VerificationStep.CHECK_DIGITS,
                status=VerificationStatus.FAILED,
                message=f"Check digit validation error: {e}",
            )

    def _validate_check_digit(self, value: str, algorithm: str) -> bool:
        """Validate check digit using specified algorithm."""
        if algorithm == "mod10":
            return self._validate_mod10_check_digit(value)
        if algorithm == "mod37":
            return self._validate_mod37_check_digit(value)
        msg = f"Unsupported check digit algorithm: {algorithm}"
        raise ValueError(msg)

    def _validate_mod10_check_digit(self, value: str) -> bool:
        """Validate MOD-10 check digit (ISO/IEC 7064)."""
        if len(value) < 2:
            return False

        data = value[:-1]
        expected_check = value[-1]

        # Convert characters to numeric values for MOD-10
        numeric_data = ""
        for char in data:
            if char.isalpha():
                # A=10, B=11, ..., Z=35
                numeric_data += str(ord(char.upper()) - ord("A") + 10)
            elif char.isdigit():
                numeric_data += char
            elif char == "<":
                numeric_data += "0"  # Filler character
            else:
                return False  # Invalid character

        # Calculate MOD-10 check digit
        total = 0
        for i, digit in enumerate(numeric_data):
            weight = 2 if i % 2 == 0 else 1
            product = int(digit) * weight
            total += product // 10 + product % 10

        calculated_check = str((10 - (total % 10)) % 10)
        return calculated_check == expected_check

    def _validate_mod37_check_digit(self, value: str) -> bool:
        """Validate MOD-37 check digit (for alphanumeric data)."""
        if len(value) < 2:
            return False

        data = value[:-1]
        expected_check = value[-1]

        # Character set for MOD-37: 0-9, A-Z, <
        char_values = {}
        for i in range(10):
            char_values[str(i)] = i
        for i in range(26):
            char_values[chr(ord("A") + i)] = i + 10
        char_values["<"] = 0

        # Calculate weighted sum
        total = 0
        weight = len(data)
        for char in data:
            if char.upper() not in char_values:
                return False
            total += char_values[char.upper()] * weight
            weight -= 1

        calculated_check_value = total % 37
        if calculated_check_value < 10:
            calculated_check = str(calculated_check_value)
        elif calculated_check_value < 36:
            calculated_check = chr(ord("A") + calculated_check_value - 10)
        else:
            calculated_check = "<"

        return calculated_check == expected_check.upper()


# Utility functions for common verification patterns
def create_error_result(
    step: VerificationStep, message: str, details: dict[str, Any] | None = None
) -> VerificationStepResult:
    """Create a failed verification step result."""
    return VerificationStepResult(
        step=step, status=VerificationStatus.FAILED, message=message, details=details or {}
    )


def create_success_result(
    step: VerificationStep,
    message: str = "",
    details: dict[str, Any] | None = None,
    confidence: float = 1.0,
) -> VerificationStepResult:
    """Create a successful verification step result."""
    return VerificationStepResult(
        step=step,
        status=VerificationStatus.PASSED,
        message=message or f"{step.value} verification passed",
        details=details or {},
        confidence=confidence,
    )


def create_warning_result(
    step: VerificationStep,
    message: str,
    details: dict[str, Any] | None = None,
    confidence: float = 0.7,
) -> VerificationStepResult:
    """Create a warning verification step result."""
    return VerificationStepResult(
        step=step,
        status=VerificationStatus.WARNING,
        message=message,
        details=details or {},
        confidence=confidence,
    )
