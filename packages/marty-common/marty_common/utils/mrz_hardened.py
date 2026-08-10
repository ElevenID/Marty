"""Structured compatibility adapters for the native ICAO MRZ parser."""

from __future__ import annotations

from time import perf_counter

from marty_common.models.mrz_validation import (
    MRZDocumentType,
    MRZDocumentTypeInference,
    MRZErrorCode,
    MRZValidationError,
    MRZValidationResult,
)
from marty_common.models.passport import MRZData
from marty_common.utils.mrz_utils import MRZException, MRZParser


class HardenedMRZException(MRZException):  # noqa: N818
    """Compatibility error carrying the historical structured attributes."""

    def __init__(
        self,
        message: str,
        error_code: MRZErrorCode = MRZErrorCode.MALFORMED_MRZ_STRUCTURE,
        position=None,
        suggestion: str | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.position = position
        self.suggestion = suggestion


class MRZChecksumValidator:
    """Native-backed check-digit compatibility surface."""

    WEIGHT_PATTERN = [7, 3, 1]

    @classmethod
    def calculate_check_digit(cls, data: str) -> str:
        return MRZParser.calculate_check_digit(data)

    @classmethod
    def validate_check_digit(cls, data: str, check_digit: str) -> tuple[bool, str]:
        calculated = cls.calculate_check_digit(data)
        return MRZParser.validate_check_digit(data, check_digit), calculated

    @classmethod
    def validate_composite_checksum(
        cls,
        doc_number: str,
        doc_check: str,
        birth_date: str,
        birth_check: str,
        expiry_date: str,
        expiry_check: str,
        personal_number: str = "",
        personal_check: str = "",
        composite_check: str = "",
    ) -> tuple[bool, str]:
        value = "".join(
            (
                doc_number,
                doc_check,
                birth_date,
                birth_check,
                expiry_date,
                expiry_check,
                personal_number,
                personal_check,
            )
        )
        return cls.validate_check_digit(value, composite_check)


class HardenedMRZParser:
    """Preserve structured results while using Rust as the only parser."""

    def __init__(self, strict_mode: bool = True) -> None:
        self.strict_mode = strict_mode
        self.checksum_validator = MRZChecksumValidator()

    def parse_mrz(self, mrz_data: str) -> MRZValidationResult:
        started = perf_counter()
        normalized = "\n".join(line.strip().upper() for line in mrz_data.splitlines() if line.strip())
        try:
            parsed = MRZParser._parse(normalized)
            lines = normalized.splitlines()
            format_by_shape = {
                (3, 30): MRZDocumentType.TD1,
                (2, 36): MRZDocumentType.TD2,
                (2, 44): MRZDocumentType.TD3,
            }
            document_type = format_by_shape[(len(lines), len(lines[0]))]
            inference = MRZDocumentTypeInference(
                inferred_type=document_type,
                confidence=1.0,
                candidates=[(document_type, 1.0)],
                reasons=["Format selected by the native ICAO parser"],
            )
            return MRZValidationResult(
                is_valid=True,
                document_type=document_type,
                type_inference=inference,
                parsed_data=parsed.model_dump(),
                confidence=1.0,
                parsing_time_ms=(perf_counter() - started) * 1000,
                raw_mrz=mrz_data,
                normalized_mrz=normalized,
            )
        except Exception as exc:
            message = str(exc)
            code = (
                MRZErrorCode.CHECKSUM_MISMATCH
                if "check digit" in message.lower()
                else MRZErrorCode.MALFORMED_MRZ_STRUCTURE
            )
            return MRZValidationResult(
                is_valid=False,
                errors=[MRZValidationError(code=code, message=message)],
                confidence=0.0,
                parsing_time_ms=(perf_counter() - started) * 1000,
                raw_mrz=mrz_data,
                normalized_mrz=normalized or None,
            )


def parse_mrz_with_validation(mrz_data: str, strict_mode: bool = True) -> MRZValidationResult:
    return HardenedMRZParser(strict_mode=strict_mode).parse_mrz(mrz_data)


def parse_mrz_simple(mrz_data: str) -> MRZData | None:
    result = parse_mrz_with_validation(mrz_data, strict_mode=False)
    return MRZData(**result.parsed_data) if result.is_valid and result.parsed_data else None


__all__ = [
    "HardenedMRZException",
    "HardenedMRZParser",
    "MRZChecksumValidator",
    "parse_mrz_simple",
    "parse_mrz_with_validation",
]
