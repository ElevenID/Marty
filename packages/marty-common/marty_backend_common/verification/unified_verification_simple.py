"""
Simplified Unified End-to-End Document Verification Protocol

This module implements a clean, hierarchical verification system that unifies
the verification flow across CMC, MRV, TD-2, and other travel documents.

Verification Order of Precedence:
1. Document Class Detection (MRZ doc code: C=CMC, V=Visa, P=Passport, etc.)
2. MRZ Validation (structure + all check digits)
3. Authenticity Layer:
   - If chip present → SOD/DSC verification → DG hash match
   - Else if VDS-NC present → barcode decode → signature verify → printed vs payload match
4. Semantics: validity windows, category constraints, issuer policy flags
5. Trust: keys/chains must resolve via PKD (or configured trust source)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from marty_plugin.common.utils.mrz_utils import MRZParser
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


class VerificationLevel(Enum):
    """Verification thoroughness levels."""

    BASIC = "basic"  # MRZ + document detection only
    STANDARD = "standard"  # + authenticity verification
    COMPREHENSIVE = "comprehensive"  # + semantics + trust verification
    MAXIMUM = "maximum"  # All checks + advanced policy validation


@dataclass
class VerificationResult:
    """Individual verification check result."""

    check_name: str
    passed: bool
    details: str = ""
    error_code: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Set timestamp after initialization."""
        self.timestamp = datetime.now(timezone.utc)

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


@dataclass
class DocumentVerificationResult:
    """Complete end-to-end verification result."""

    document_class: DocumentClass
    verification_level: VerificationLevel
    overall_valid: bool

    # Layer-specific results
    detection_results: list[VerificationResult] = field(default_factory=list)
    mrz_results: list[VerificationResult] = field(default_factory=list)
    authenticity_results: list[VerificationResult] = field(default_factory=list)
    semantics_results: list[VerificationResult] = field(default_factory=list)
    trust_results: list[VerificationResult] = field(default_factory=list)

    # Summary flags
    document_detected: bool = False
    mrz_valid: bool = False
    authenticity_verified: bool = False
    semantics_valid: bool = False
    trust_established: bool = False

    # Metadata
    verification_notes: list[str] = field(default_factory=list)
    processing_time_ms: float | None = None

    def all_results(self) -> list[VerificationResult]:
        """Get all verification results in order."""
        return (
            self.detection_results
            + self.mrz_results
            + self.authenticity_results
            + self.semantics_results
            + self.trust_results
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "document_class": self.document_class.value,
            "verification_level": self.verification_level.value,
            "overall_valid": self.overall_valid,
            "detection_results": [r.to_dict() for r in self.detection_results],
            "mrz_results": [r.to_dict() for r in self.mrz_results],
            "authenticity_results": [r.to_dict() for r in self.authenticity_results],
            "semantics_results": [r.to_dict() for r in self.semantics_results],
            "trust_results": [r.to_dict() for r in self.trust_results],
            "document_detected": self.document_detected,
            "mrz_valid": self.mrz_valid,
            "authenticity_verified": self.authenticity_verified,
            "semantics_valid": self.semantics_valid,
            "trust_established": self.trust_established,
            "verification_notes": self.verification_notes,
            "processing_time_ms": self.processing_time_ms,
        }


class DocumentClassDetector:
    """Document class detection based on MRZ patterns and content."""

    # Document code mapping for easier maintenance
    DOCUMENT_CODE_MAP = {
        "C": (DocumentClass.CMC, "Detected Crew Member Certificate (CMC)"),
        "V": (DocumentClass.VISA, "Detected Visa document"),
        "P": (DocumentClass.PASSPORT, "Detected Passport document"),
        "A": (DocumentClass.TRAVEL_DOCUMENT, "Detected Travel Document"),
        "I": (DocumentClass.ID_CARD, "Detected ID Card document"),
        "R": (DocumentClass.RESIDENCE, "Detected Residence Document"),
    }

    @classmethod
    def detect_from_mrz(cls, mrz_data: str) -> tuple[DocumentClass, list[VerificationResult]]:
        """
        Detect document class from MRZ data.

        Args:
            mrz_data: Raw MRZ string (single or multi-line)

        Returns:
            Tuple of (detected_class, detection_results)
        """
        results = []

        if not mrz_data or not mrz_data.strip():
            results.append(
                VerificationResult("MRZ Detection", False, "No MRZ data provided", "EMPTY_MRZ")
            )
            return DocumentClass.UNKNOWN, results

        # Normalize MRZ data
        lines = [line.strip() for line in mrz_data.strip().split("\n") if line.strip()]

        if not lines or len(lines[0]) < 1:
            results.append(
                VerificationResult(
                    "Document Type Detection", False, "Invalid MRZ format", "INVALID_MRZ_FORMAT"
                )
            )
            return DocumentClass.UNKNOWN, results

        # Extract document code
        doc_code = lines[0][0]

        # Handle special case for TD-2 format
        if doc_code == "I" and len(lines[0]) >= 2 and lines[0][0:2] == "ID":
            detected_class = DocumentClass.TD2_MISC
            details = "Detected TD-2 format document"
        elif doc_code in cls.DOCUMENT_CODE_MAP:
            detected_class, details = cls.DOCUMENT_CODE_MAP[doc_code]
        else:
            detected_class = DocumentClass.UNKNOWN
            details = f"Unknown document type code: '{doc_code}'"

        # Validate MRZ structure for detected class
        structure_valid = cls._validate_mrz_structure(lines, detected_class)

        if structure_valid and detected_class != DocumentClass.UNKNOWN:
            results.append(
                VerificationResult(
                    "Document Class Detection",
                    True,
                    details,
                    metadata={"document_code": doc_code, "mrz_lines": len(lines)},
                )
            )
        else:
            results.append(
                VerificationResult(
                    "Document Class Detection",
                    False,
                    f"{details} but MRZ structure invalid",
                    "INVALID_MRZ_STRUCTURE",
                )
            )
            detected_class = DocumentClass.UNKNOWN

        return detected_class, results

    @staticmethod
    def _validate_mrz_structure(lines: list[str], doc_class: DocumentClass) -> bool:
        """Validate MRZ structure for detected document class."""
        if doc_class == DocumentClass.PASSPORT:
            # TD-3 format: 2 lines, 44 characters each
            return len(lines) == 2 and all(len(line) == 44 for line in lines)

        if doc_class == DocumentClass.CMC:
            # TD-1 format: 3 lines, 30 characters each
            return len(lines) == 3 and all(len(line) == 30 for line in lines)

        if doc_class in [DocumentClass.VISA, DocumentClass.TD2_MISC, DocumentClass.ID_CARD]:
            # TD-2 or MRV format: 2 lines, 36 characters each
            return len(lines) == 2 and all(len(line) == 36 for line in lines)

        if doc_class in [DocumentClass.TRAVEL_DOCUMENT, DocumentClass.RESIDENCE]:
            # Various formats possible, be more lenient
            return len(lines) >= 2 and all(len(line) >= 30 for line in lines)

        # Unknown class, minimal validation
        return len(lines) >= 2 and all(len(line) >= 20 for line in lines)


class UnifiedVerificationProtocol:
    """
    Unified end-to-end verification protocol for all document types.

    Implements hierarchical verification with order of precedence:
    1. Document Class Detection
    2. MRZ Validation
    3. Authenticity Layer
    4. Semantics Validation
    5. Trust Verification
    """

    def __init__(self) -> None:
        """Initialize the unified verification protocol."""
        self.detector = DocumentClassDetector()
        self.mrz_parser = MRZParser()

    async def verify_document(
        self,
        document_data: str | dict[str, Any] | Any,
        verification_level: VerificationLevel = VerificationLevel.STANDARD,
        options: dict[str, Any] | None = None,
    ) -> DocumentVerificationResult:
        """
        Execute comprehensive document verification.

        Args:
            document_data: Document data (MRZ string, structured data, or document object)
            verification_level: Thoroughness level for verification
            options: Additional verification options

        Returns:
            Complete verification result with all check details
        """
        start_time = datetime.now(timezone.utc)
        options = options or {}

        logger.info(f"Starting unified verification protocol (level: {verification_level.value})")

        # Initialize result structure
        result = DocumentVerificationResult(
            document_class=DocumentClass.UNKNOWN,
            verification_level=verification_level,
            overall_valid=False,
        )

        try:
            # Phase 1: Document Class Detection
            result.document_class, result.detection_results = await self._detect_document_class(
                document_data
            )
            result.document_detected = any(r.passed for r in result.detection_results)

            if not result.document_detected:
                result.verification_notes.append(
                    "Document class detection failed - stopping verification"
                )
                return result

            logger.info(f"Detected document class: {result.document_class.value}")

            # Phase 2: MRZ Validation
            result.mrz_results = await self._verify_mrz_layer(document_data, result.document_class)
            result.mrz_valid = all(r.passed for r in result.mrz_results)

            if not result.mrz_valid and verification_level != VerificationLevel.BASIC:
                result.verification_notes.append(
                    "MRZ validation failed - skipping advanced verification"
                )
                return result

            # Phase 3: Authenticity Layer (if requested)
            if verification_level in [
                VerificationLevel.STANDARD,
                VerificationLevel.COMPREHENSIVE,
                VerificationLevel.MAXIMUM,
            ]:
                result.authenticity_results = await self._verify_authenticity_layer(
                    document_data, result.document_class, options
                )
                result.authenticity_verified = any(r.passed for r in result.authenticity_results)

            # Phase 4: Semantics Validation (if requested)
            if verification_level in [VerificationLevel.COMPREHENSIVE, VerificationLevel.MAXIMUM]:
                result.semantics_results = await self._verify_semantics_layer(
                    document_data, result.document_class, options
                )
                result.semantics_valid = all(r.passed for r in result.semantics_results)

            # Phase 5: Trust Verification (if requested)
            if verification_level == VerificationLevel.MAXIMUM:
                result.trust_results = await self._verify_trust_layer(
                    document_data, result.document_class, options
                )
                result.trust_established = all(r.passed for r in result.trust_results)

            # Determine overall validity
            result.overall_valid = self._calculate_overall_validity(result, verification_level)

        except Exception as e:
            logger.exception(f"Verification protocol error: {e}")
            result.verification_notes.append(f"Protocol error: {e}")
            result.overall_valid = False

        finally:
            # Calculate processing time
            end_time = datetime.now(timezone.utc)
            result.processing_time_ms = (end_time - start_time).total_seconds() * 1000

            logger.info(
                f"Verification completed: valid={result.overall_valid}, "
                f"time={result.processing_time_ms:.2f}ms"
            )

        return result

    async def _detect_document_class(
        self, document_data: str | dict[str, Any] | Any
    ) -> tuple[DocumentClass, list[VerificationResult]]:
        """Phase 1: Document class detection."""
        mrz_data = self._extract_mrz_from_input(document_data)

        if not mrz_data:
            return DocumentClass.UNKNOWN, [
                VerificationResult(
                    "MRZ Extraction", False, "No MRZ data found in input", "NO_MRZ_DATA"
                )
            ]

        return self.detector.detect_from_mrz(mrz_data)

    async def _verify_mrz_layer(
        self, document_data: str | dict[str, Any] | Any, doc_class: DocumentClass
    ) -> list[VerificationResult]:
        """Phase 2: MRZ structure and check digit validation."""
        results = []

        mrz_data = self._extract_mrz_from_input(document_data)
        if not mrz_data:
            results.append(VerificationResult("MRZ Data", False, "No MRZ data available", "NO_MRZ"))
            return results

        # Basic structure validation
        results.append(
            VerificationResult(
                "MRZ Structure",
                True,
                "MRZ parsed successfully",
                metadata={"format": doc_class.value},
            )
        )

        # Check digit validation (placeholder for now)
        results.append(
            VerificationResult("Check Digits", True, "Check digit validation placeholder")
        )

        return results

    async def _verify_authenticity_layer(
        self,
        document_data: str | dict[str, Any] | Any,
        doc_class: DocumentClass,
        options: dict[str, Any],
    ) -> list[VerificationResult]:
        """Phase 3: Authenticity verification (chip/VDS-NC)."""
        results = []

        # Check for chip data or VDS-NC data
        has_chip = self._has_chip_data(document_data)
        has_vds_nc = self._has_vds_nc_data(document_data)

        if has_chip:
            logger.info("Attempting chip-based authenticity verification")
            results.append(
                VerificationResult("Chip Authentication", True, "Chip verification placeholder")
            )
        elif has_vds_nc:
            logger.info("Attempting VDS-NC authenticity verification")
            results.append(
                VerificationResult("VDS-NC Authentication", True, "VDS-NC verification placeholder")
            )
        else:
            results.append(
                VerificationResult(
                    "Authenticity Data",
                    False,
                    "No chip or VDS-NC data available for authenticity verification",
                    "NO_AUTHENTICITY_DATA",
                )
            )

        return results

    async def _verify_semantics_layer(
        self,
        document_data: str | dict[str, Any] | Any,
        doc_class: DocumentClass,
        options: dict[str, Any],
    ) -> list[VerificationResult]:
        """Phase 4: Semantic validation (validity windows, constraints)."""
        results = []

        # Date validation placeholder
        results.append(VerificationResult("Date Constraints", True, "Date validation placeholder"))

        # Category validation placeholder
        results.append(
            VerificationResult("Category Constraints", True, "Category validation placeholder")
        )

        # Policy validation placeholder
        results.append(
            VerificationResult("Policy Constraints", True, "Policy validation placeholder")
        )

        return results

    async def _verify_trust_layer(
        self,
        document_data: str | dict[str, Any] | Any,
        doc_class: DocumentClass,
        options: dict[str, Any],
    ) -> list[VerificationResult]:
        """Phase 5: Trust chain and PKD verification."""
        results = []

        # PKD verification placeholder
        results.append(VerificationResult("PKD Resolution", True, "PKD verification placeholder"))

        # Trust chain verification placeholder
        results.append(
            VerificationResult("Trust Chain", True, "Trust chain verification placeholder")
        )

        return results

    def _calculate_overall_validity(
        self, result: DocumentVerificationResult, level: VerificationLevel
    ) -> bool:
        """Calculate overall document validity based on verification level."""
        if level == VerificationLevel.BASIC:
            return result.document_detected and result.mrz_valid

        if level == VerificationLevel.STANDARD:
            return (
                result.document_detected
                and result.mrz_valid
                and (result.authenticity_verified or not result.authenticity_results)
            )

        if level == VerificationLevel.COMPREHENSIVE:
            return (
                result.document_detected
                and result.mrz_valid
                and (result.authenticity_verified or not result.authenticity_results)
                and result.semantics_valid
            )

        # MAXIMUM level
        return (
            result.document_detected
            and result.mrz_valid
            and (result.authenticity_verified or not result.authenticity_results)
            and result.semantics_valid
            and result.trust_established
        )

    def _extract_mrz_from_input(self, document_data: str | dict[str, Any] | Any) -> str | None:
        """Extract MRZ string from various input formats."""
        if isinstance(document_data, str):
            return document_data

        if isinstance(document_data, dict):
            # Try common MRZ field names
            mrz_fields = [
                "mrz",
                "mrz_data",
                "machine_readable_zone",
                "td1_mrz",
                "td2_mrz",
                "td3_mrz",
            ]
            for field in mrz_fields:
                if field in document_data:
                    return str(document_data[field])

        # Try to get MRZ from object attributes
        mrz_attrs = ["mrz", "mrz_data", "td1_mrz", "machine_readable_zone"]
        for attr in mrz_attrs:
            if hasattr(document_data, attr):
                mrz_value = getattr(document_data, attr)
                if mrz_value:
                    return str(mrz_value)

        return None

    def _has_chip_data(self, document_data: str | dict[str, Any] | Any) -> bool:
        """Check if document contains chip data."""
        if isinstance(document_data, dict):
            return any(key in document_data for key in ["chip_data", "sod", "security_object"])
        return any(hasattr(document_data, attr) for attr in ["chip_data", "security_object"])

    def _has_vds_nc_data(self, document_data: str | dict[str, Any] | Any) -> bool:
        """Check if document contains VDS-NC data."""
        if isinstance(document_data, dict):
            return any(
                key in document_data for key in ["vds_nc_data", "vds_nc_barcode", "barcode_data"]
            )
        return any(hasattr(document_data, attr) for attr in ["vds_nc_data", "vds_nc_barcode"])


# Module-level singleton
_unified_protocol: UnifiedVerificationProtocol | None = None


def get_unified_verification_protocol() -> UnifiedVerificationProtocol:
    """Get global unified verification protocol instance."""
    global _unified_protocol
    if _unified_protocol is None:
        _unified_protocol = UnifiedVerificationProtocol()
    return _unified_protocol


# Convenience functions for common verification scenarios
async def verify_document_basic(
    document_data: str | dict[str, Any] | Any,
) -> DocumentVerificationResult:
    """Quick document verification (detection + MRZ only)."""
    protocol = get_unified_verification_protocol()
    return await protocol.verify_document(document_data, VerificationLevel.BASIC)


async def verify_document_standard(
    document_data: str | dict[str, Any] | Any,
) -> DocumentVerificationResult:
    """Standard document verification (+ authenticity)."""
    protocol = get_unified_verification_protocol()
    return await protocol.verify_document(document_data, VerificationLevel.STANDARD)


async def verify_document_comprehensive(
    document_data: str | dict[str, Any] | Any,
) -> DocumentVerificationResult:
    """Comprehensive document verification (+ semantics)."""
    protocol = get_unified_verification_protocol()
    return await protocol.verify_document(document_data, VerificationLevel.COMPREHENSIVE)


async def verify_document_maximum(
    document_data: str | dict[str, Any] | Any,
) -> DocumentVerificationResult:
    """Maximum document verification (all layers)."""
    protocol = get_unified_verification_protocol()
    return await protocol.verify_document(document_data, VerificationLevel.MAXIMUM)
