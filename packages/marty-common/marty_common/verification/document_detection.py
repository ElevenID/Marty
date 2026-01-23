"""
Document Class Detection Implementation

This module provides robust document class detection based on MRZ patterns
and content, supporting the unified verification protocol.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from marty_plugin.shared.logging_config import get_logger

logger = get_logger(__name__)


class DocumentClass(Enum):
    """Document classes based on MRZ document codes."""

    CMC = "C"  # Crew Member Certificate
    VISA = "V"  # Visa
    PASSPORT = "P"  # Passport
    TRAVEL_DOCUMENT = "A"  # Travel Document
    ID_CARD = "I"  # ID Card
    RESIDENCE = "R"  # Residence Document
    TD2_MISC = "ID"  # TD-2 Miscellaneous
    UNKNOWN = "?"  # Unknown/Invalid


@dataclass
class DetectionResult:
    """Result of document class detection."""

    document_class: DocumentClass
    confidence: float  # 0.0 to 1.0
    details: str
    metadata: dict[str, str | int | float]

    def __post_init__(self) -> None:
        """Set timestamp after initialization."""
        self.timestamp = datetime.now(timezone.utc)


class DocumentClassDetector:
    """Enhanced document class detection with confidence scoring."""

    # Document code mapping with expected formats
    DOCUMENT_PATTERNS = {
        "C": {
            "class": DocumentClass.CMC,
            "name": "Crew Member Certificate (CMC)",
            "format": "TD-1",
            "lines": 3,
            "line_length": 30,
            "pattern": r"^C[A-Z]{3}[A-Z0-9<]{26}$",
        },
        "V": {
            "class": DocumentClass.VISA,
            "name": "Visa document",
            "format": "TD-2/MRV",
            "lines": 2,
            "line_length": 36,
            "pattern": r"^V[A-Z<]{35}$",
        },
        "P": {
            "class": DocumentClass.PASSPORT,
            "name": "Passport document",
            "format": "TD-3",
            "lines": 2,
            "line_length": 44,
            "pattern": r"^P[A-Z<]{43}$",
        },
        "A": {
            "class": DocumentClass.TRAVEL_DOCUMENT,
            "name": "Travel Document",
            "format": "TD-3",
            "lines": 2,
            "line_length": 44,
            "pattern": r"^A[A-Z<]{43}$",
        },
        "I": {
            "class": DocumentClass.ID_CARD,
            "name": "ID Card document",
            "format": "TD-2",
            "lines": 2,
            "line_length": 36,
            "pattern": r"^I[A-Z<]{35}$",
        },
        "R": {
            "class": DocumentClass.RESIDENCE,
            "name": "Residence Document",
            "format": "TD-2",
            "lines": 2,
            "line_length": 36,
            "pattern": r"^R[A-Z<]{35}$",
        },
    }

    def detect_document_class(self, mrz_data: str) -> DetectionResult:
        """
        Detect document class from MRZ data with confidence scoring.

        Args:
            mrz_data: Raw MRZ string (single or multi-line)

        Returns:
            DetectionResult with class, confidence, and details
        """
        if not mrz_data or not mrz_data.strip():
            return DetectionResult(
                document_class=DocumentClass.UNKNOWN,
                confidence=0.0,
                details="No MRZ data provided",
                metadata={"error": "EMPTY_MRZ"},
            )

        # Normalize and validate MRZ structure
        lines = self._normalize_mrz_lines(mrz_data)

        if not lines:
            return DetectionResult(
                document_class=DocumentClass.UNKNOWN,
                confidence=0.0,
                details="Invalid MRZ format",
                metadata={"error": "INVALID_FORMAT", "raw_length": len(mrz_data)},
            )

        # Extract document type code
        first_line = lines[0]
        if len(first_line) < 1:
            return DetectionResult(
                document_class=DocumentClass.UNKNOWN,
                confidence=0.0,
                details="MRZ too short to contain document type",
                metadata={"error": "INSUFFICIENT_LENGTH", "line_length": len(first_line)},
            )

        # Handle special TD-2 format case
        if len(first_line) >= 2 and first_line[0:2] == "ID":
            return self._detect_td2_format(lines)

        # Standard document type detection
        doc_code = first_line[0]
        return self._detect_by_code(doc_code, lines)

    def _normalize_mrz_lines(self, mrz_data: str) -> list[str]:
        """Normalize MRZ data into clean lines."""
        # Split by newlines and clean each line
        lines = []
        for line in mrz_data.strip().split("\n"):
            cleaned = line.strip()
            if cleaned:  # Only include non-empty lines
                lines.append(cleaned)

        return lines

    def _detect_td2_format(self, lines: list[str]) -> DetectionResult:
        """Detect TD-2 format document."""
        expected_lines = 2
        expected_length = 36

        confidence = self._calculate_structure_confidence(lines, expected_lines, expected_length)

        if confidence > 0.7:
            return DetectionResult(
                document_class=DocumentClass.TD2_MISC,
                confidence=confidence,
                details="Detected TD-2 format document",
                metadata={
                    "format": "TD-2",
                    "lines": len(lines),
                    "expected_lines": expected_lines,
                    "line_lengths": [len(line) for line in lines],
                },
            )

        return DetectionResult(
            document_class=DocumentClass.UNKNOWN,
            confidence=confidence,
            details="TD-2 format detected but structure validation failed",
            metadata={
                "error": "STRUCTURE_MISMATCH",
                "lines": len(lines),
                "expected_lines": expected_lines,
            },
        )

    def _detect_by_code(self, doc_code: str, lines: list[str]) -> DetectionResult:
        """Detect document class by document code."""
        if doc_code not in self.DOCUMENT_PATTERNS:
            return DetectionResult(
                document_class=DocumentClass.UNKNOWN,
                confidence=0.0,
                details=f"Unknown document type code: '{doc_code}'",
                metadata={
                    "error": "UNKNOWN_CODE",
                    "document_code": doc_code,
                    "available_codes": list(self.DOCUMENT_PATTERNS.keys()),
                },
            )

        pattern_info = self.DOCUMENT_PATTERNS[doc_code]
        doc_class = pattern_info["class"]

        # Calculate confidence based on structure validation
        confidence = self._calculate_structure_confidence(
            lines, pattern_info["lines"], pattern_info["line_length"]
        )

        # Additional pattern validation for higher confidence
        if confidence > 0.5:
            pattern_confidence = self._validate_mrz_pattern(lines[0], pattern_info["pattern"])
            confidence = (confidence + pattern_confidence) / 2

        return DetectionResult(
            document_class=doc_class,
            confidence=confidence,
            details=f"Detected {pattern_info['name']} ({pattern_info['format']})",
            metadata={
                "document_code": doc_code,
                "format": pattern_info["format"],
                "lines": len(lines),
                "expected_lines": pattern_info["lines"],
                "line_lengths": [len(line) for line in lines],
                "pattern_match": confidence > 0.8,
            },
        )

    def _calculate_structure_confidence(
        self, lines: list[str], expected_lines: int, expected_length: int
    ) -> float:
        """Calculate confidence based on MRZ structure."""
        confidence = 0.0

        # Line count match
        if len(lines) == expected_lines:
            confidence += 0.5
        elif abs(len(lines) - expected_lines) == 1:
            confidence += 0.2  # Close but not exact

        # Line length validation
        if lines:
            length_matches = sum(1 for line in lines if len(line) == expected_length)
            length_confidence = length_matches / len(lines)
            confidence += 0.5 * length_confidence

        return min(confidence, 1.0)

    def _validate_mrz_pattern(self, line: str, pattern: str) -> float:
        """Validate first line against expected MRZ pattern."""
        try:
            if re.match(pattern, line):
                return 1.0

            # Partial match scoring
            # Check if it starts correctly
            if len(line) > 0 and pattern.startswith(f"^{line[0]}"):
                return 0.6

        except re.error:
            # Invalid pattern
            return 0.5
        else:
            return 0.0

    def get_format_info(self, document_class: DocumentClass) -> dict[str, str | int] | None:
        """Get format information for a document class."""
        for pattern_info in self.DOCUMENT_PATTERNS.values():
            if pattern_info["class"] == document_class:
                return {
                    "format": pattern_info["format"],
                    "lines": pattern_info["lines"],
                    "line_length": pattern_info["line_length"],
                    "name": pattern_info["name"],
                }

        if document_class == DocumentClass.TD2_MISC:
            return {"format": "TD-2", "lines": 2, "line_length": 36, "name": "TD-2 Miscellaneous"}

        return None


# Convenience functions
def detect_document_type(mrz_data: str) -> DocumentClass:
    """Quick document type detection."""
    detector = DocumentClassDetector()
    result = detector.detect_document_class(mrz_data)
    return result.document_class


def detect_with_confidence(mrz_data: str) -> tuple[DocumentClass, float]:
    """Document detection with confidence score."""
    detector = DocumentClassDetector()
    result = detector.detect_document_class(mrz_data)
    return result.document_class, result.confidence


def is_supported_document(mrz_data: str, min_confidence: float = 0.7) -> bool:
    """Check if document is supported with minimum confidence."""
    detector = DocumentClassDetector()
    result = detector.detect_document_class(mrz_data)
    return result.document_class != DocumentClass.UNKNOWN and result.confidence >= min_confidence
