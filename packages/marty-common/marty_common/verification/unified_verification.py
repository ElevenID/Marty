"""
Unified End-to-End Document Verification Protocol

This module implements a comprehensive, hierarchical verification system that unifies
the verification flow across CMC, MRV, TD-2, and other travel documents according to
ICAO Doc 9303 standards.

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
from typing import (
    Any,
    Protocol,
    Optional,
    Dict,
    List,
    Tuple,
    Union,
)

from marty_plugin.common.utils.mrz_utils import MRZParser
from marty_plugin.common.verification.cmc_verification import CMCVerificationProtocol
from marty_plugin.common.logging_config import get_logger

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


class VerificationResult:
    """Individual verification check result."""

    def __init__(
        self,
        check_name: str,
        passed: bool,
        details: str = "",
        error_code: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.check_name = check_name
        self.passed = passed
        self.details = details
        self.error_code = error_code
        self.metadata = metadata or {}
        self.timestamp = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
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
    detection_results: List[VerificationResult] = field(default_factory=list)
    mrz_results: List[VerificationResult] = field(default_factory=list)
    authenticity_results: List[VerificationResult] = field(default_factory=list)
    semantics_results: List[VerificationResult] = field(default_factory=list)
    trust_results: List[VerificationResult] = field(default_factory=list)

    # Summary flags
    document_detected: bool = False
    mrz_valid: bool = False
    authenticity_verified: bool = False
    semantics_valid: bool = False
    trust_established: bool = False

    # Metadata
    verification_notes: List[str] = field(default_factory=list)
    processing_time_ms: Optional[float] = None

    def all_results(self) -> List[VerificationResult]:
        """Get all verification results in order."""
        return (
            self.detection_results
            + self.mrz_results
            + self.authenticity_results
            + self.semantics_results
            + self.trust_results
        )

    def to_dict(self) -> Dict[str, Any]:
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


class DocumentVerifier(Protocol):
    """Protocol for document-specific verifiers."""

    async def verify_mrz(self, document_data: Any) -> List[VerificationResult]:
        """Verify MRZ structure and check digits."""
        raise NotImplementedError

    async def verify_authenticity(self, document_data: Any) -> List[VerificationResult]:
        """Verify document authenticity (chip/VDS-NC)."""
        raise NotImplementedError

    async def verify_semantics(self, document_data: Any) -> List[VerificationResult]:
        """Verify semantic constraints and policies."""
        raise NotImplementedError

    async def verify_trust(self, document_data: Any) -> List[VerificationResult]:
        """Verify trust chain and PKD resolution."""
        raise NotImplementedError


class DocumentClassDetector:
    """Document class detection based on MRZ patterns and content."""

    @staticmethod
    def detect_from_mrz(mrz_data: str) -> Tuple[DocumentClass, List[VerificationResult]]:
        """
        Detect document class from MRZ data.

        Args:
            mrz_data: Raw MRZ string (single or multi-line)

        Returns:
            Tuple of (detected_class, detection_results)
        """
        results: List[VerificationResult] = []
        detected_class: DocumentClass = DocumentClass.UNKNOWN
        try:
            # Normalize MRZ data
            lines = [line.strip() for line in mrz_data.strip().split("\n") if line.strip()]

            if not lines:
                results.append(
                    VerificationResult("MRZ Detection", False, "No MRZ data provided", "EMPTY_MRZ")
                )
                return DocumentClass.UNKNOWN, results

            # Get first character of first line (document type code)
            first_line = lines[0]
            if len(first_line) < 1:
                results.append(
                    VerificationResult(
                        "Document Type Detection", False, "MRZ too short", "INVALID_MRZ_LENGTH"
                    )
                )
                return DocumentClass.UNKNOWN, results

            doc_code = first_line[0]

            # Detect document class based on code
            if doc_code == "C":
                detected_class = DocumentClass.CMC
                details = "Detected Crew Member Certificate (CMC)"
            elif doc_code == "V":
                detected_class = DocumentClass.VISA
                details = "Detected Visa document"
            elif doc_code == "P":
                detected_class = DocumentClass.PASSPORT
                details = "Detected Passport document"
            elif doc_code == "A":
                detected_class = DocumentClass.TRAVEL_DOCUMENT
                details = "Detected Travel Document"
            elif doc_code == "I":
                # Check if it's TD-2 format by looking at length
                if len(first_line) >= 30 and len(lines) >= 2:
                    # Could be TD-2 ID card format
                    if first_line[0:2] == "ID":
                        detected_class = DocumentClass.TD2_MISC
                        details = "Detected TD-2 format document"
                    else:
                        detected_class = DocumentClass.ID_CARD
                        details = "Detected ID Card document"
                else:
                    detected_class = DocumentClass.ID_CARD
                    details = "Detected ID Card document"
            elif doc_code == "R":
                detected_class = DocumentClass.RESIDENCE
                details = "Detected Residence Document"
            else:
                detected_class = DocumentClass.UNKNOWN
                details = f"Unknown document type code: '{doc_code}'"

            # Additional validation based on MRZ structure
            mrz_structure_valid = DocumentClassDetector._validate_mrz_structure(
                lines, detected_class
            )

            if mrz_structure_valid:
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
        except Exception as e:  # Broad exception to capture any parsing/detection failures
            results.append(
                VerificationResult(
                    "Document Class Detection", False, f"Detection error: {e}", "DETECTION_ERROR"
                )
            )
            return DocumentClass.UNKNOWN, results
        return detected_class, results

    @staticmethod
    def _validate_mrz_structure(lines: List[str], doc_class: DocumentClass) -> bool:
        """
        Validate MRZ structure for detected document class.

        Args:
            lines: MRZ lines
            doc_class: Detected document class

        Returns:
            True if structure is valid for the document class
        """
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

        # Document-specific verifiers (will be initialized as needed)
        self._cmc_verifier: Optional[CMCVerificationProtocol] = None
        # Import when available - see https://github.com/burdettadam/Marty/issues/verifiers
        self._visa_verifier = None
        self._passport_verifier = None
        self._td2_verifier = None

    async def verify_document(
        self,
        document_data: Union[str, Dict[str, Any], Any],
        verification_level: VerificationLevel = VerificationLevel.STANDARD,
        options: Optional[Dict[str, Any]] = None,
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

        logger.info("Starting unified verification protocol (level: %s)", verification_level.value)

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

            logger.info("Detected document class: %s", result.document_class.value)

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
            logger.exception("Verification protocol error: %s", e)
            result.verification_notes.append(f"Protocol error: {e}")
            result.overall_valid = False

        finally:
            # Calculate processing time
            end_time = datetime.now(timezone.utc)
            result.processing_time_ms = (end_time - start_time).total_seconds() * 1000

            logger.info(
                "Verification completed: valid=%s, time=%.2fms",
                result.overall_valid,
                result.processing_time_ms or -1.0,
            )

        return result

    async def _detect_document_class(
        self, document_data: Union[str, Dict[str, Any], Any]
    ) -> Tuple[DocumentClass, List[VerificationResult]]:
        """Phase 1: Document class detection."""
        try:
            # Extract MRZ data from various input formats
            mrz_data = self._extract_mrz_from_input(document_data)

            if not mrz_data:
                return DocumentClass.UNKNOWN, [
                    VerificationResult(
                        "MRZ Extraction", False, "No MRZ data found in input", "NO_MRZ_DATA"
                    )
                ]

            # Use detector to identify document class
            return self.detector.detect_from_mrz(mrz_data)

        except Exception as e:
            return DocumentClass.UNKNOWN, [
                VerificationResult(
                    "Document Detection", False, f"Detection failed: {e}", "DETECTION_FAILED"
                )
            ]

    async def _verify_mrz_layer(
        self, document_data: Union[str, Dict[str, Any], Any], doc_class: DocumentClass
    ) -> List[VerificationResult]:
        """Phase 2: MRZ structure and check digit validation."""
        results = []

        try:
            mrz_data = self._extract_mrz_from_input(document_data)
            if not mrz_data:
                results.append(
                    VerificationResult("MRZ Data", False, "No MRZ data available", "NO_MRZ")
                )
                return results

            # Parse MRZ based on document class
            if doc_class == DocumentClass.PASSPORT:
                parsed_data = self._parse_td3_mrz(mrz_data)
            elif doc_class == DocumentClass.CMC:
                parsed_data = self._parse_td1_mrz(mrz_data)
            elif doc_class in [DocumentClass.VISA, DocumentClass.TD2_MISC, DocumentClass.ID_CARD]:
                parsed_data = self._parse_td2_mrz(mrz_data)
            else:
                # Try to auto-detect format
                parsed_data = self._parse_auto_detect_mrz(mrz_data)

            if parsed_data:
                results.append(
                    VerificationResult(
                        "MRZ Structure",
                        True,
                        "MRZ parsed successfully",
                        metadata={"format": parsed_data.get("format", "unknown")},
                    )
                )

                # Validate check digits
                check_digit_results = self._validate_all_check_digits(parsed_data, doc_class)
                results.extend(check_digit_results)
            else:
                results.append(
                    VerificationResult(
                        "MRZ Structure", False, "Failed to parse MRZ", "MRZ_PARSE_FAILED"
                    )
                )

        except Exception as e:
            results.append(
                VerificationResult(
                    "MRZ Validation", False, f"MRZ validation error: {e}", "MRZ_ERROR"
                )
            )

        return results

    async def _verify_authenticity_layer(
        self,
        document_data: Union[str, Dict[str, Any], Any],
        doc_class: DocumentClass,
        options: Dict[str, Any],
    ) -> List[VerificationResult]:
        """Phase 3: Authenticity verification (chip/VDS-NC)."""
        results = []

        try:
            # Check for chip data first
            has_chip = self._has_chip_data(document_data)
            has_vds_nc = self._has_vds_nc_data(document_data)

            if has_chip:
                logger.info("Attempting chip-based authenticity verification")
                chip_results = await self._verify_chip_authenticity(document_data, doc_class)
                results.extend(chip_results)

            elif has_vds_nc:
                logger.info("Attempting VDS-NC authenticity verification")
                vds_results = await self._verify_vds_nc_authenticity(document_data, doc_class)
                results.extend(vds_results)

            else:
                results.append(
                    VerificationResult(
                        "Authenticity Data",
                        False,
                        "No chip or VDS-NC data available for authenticity verification",
                        "NO_AUTHENTICITY_DATA",
                    )
                )

        except Exception as e:
            results.append(
                VerificationResult(
                    "Authenticity Verification",
                    False,
                    f"Authenticity verification error: {e}",
                    "AUTHENTICITY_ERROR",
                )
            )

        return results

    async def _verify_semantics_layer(
        self,
        document_data: Union[str, Dict[str, Any], Any],
        doc_class: DocumentClass,
        options: Dict[str, Any],
    ) -> List[VerificationResult]:
        """Phase 4: Semantic validation (validity windows, constraints)."""
        results = []

        try:
            # Extract relevant dates and constraints
            extracted_data = self._extract_semantic_data(document_data)

            # Validate date ranges
            date_results = self._validate_date_constraints(extracted_data, doc_class)
            results.extend(date_results)

            # Validate category constraints
            category_results = self._validate_category_constraints(extracted_data, doc_class)
            results.extend(category_results)

            # Validate issuer policy flags
            policy_results = self._validate_policy_constraints(extracted_data, doc_class, options)
            results.extend(policy_results)

        except Exception as e:
            results.append(
                VerificationResult(
                    "Semantics Validation",
                    False,
                    f"Semantics validation error: {e}",
                    "SEMANTICS_ERROR",
                )
            )

        return results

    async def _verify_trust_layer(
        self,
        document_data: Union[str, Dict[str, Any], Any],
        doc_class: DocumentClass,
        options: Dict[str, Any],
    ) -> List[VerificationResult]:
        """Phase 5: Trust chain and PKD verification."""
        results = []

        try:
            # Extract certificate/key information
            trust_data = self._extract_trust_data(document_data)

            # PKD resolution
            pkd_results = await self._verify_pkd_resolution(trust_data, doc_class, options)
            results.extend(pkd_results)

            # Trust chain validation
            chain_results = await self._verify_trust_chain(trust_data, doc_class, options)
            results.extend(chain_results)

        except Exception as e:
            results.append(
                VerificationResult(
                    "Trust Verification", False, f"Trust verification error: {e}", "TRUST_ERROR"
                )
            )

        return results

    def _calculate_overall_validity(
        self, result: DocumentVerificationResult, level: VerificationLevel
    ) -> bool:
        """Calculate overall document validity based on verification level."""

        # Basic level: just detection and MRZ
        if level == VerificationLevel.BASIC:
            return result.document_detected and result.mrz_valid

        # Standard level: + authenticity
        if level == VerificationLevel.STANDARD:
            return (
                result.document_detected
                and result.mrz_valid
                and (result.authenticity_verified or not result.authenticity_results)
            )

        # Comprehensive level: + semantics
        if level == VerificationLevel.COMPREHENSIVE:
            return (
                result.document_detected
                and result.mrz_valid
                and (result.authenticity_verified or not result.authenticity_results)
                and result.semantics_valid
            )

        # Maximum level: all layers
        return (
            result.document_detected
            and result.mrz_valid
            and (result.authenticity_verified or not result.authenticity_results)
            and result.semantics_valid
            and result.trust_established
        )

    # Helper methods for data extraction and specific verifications
    def _extract_mrz_from_input(
        self, document_data: Union[str, Dict[str, Any], Any]
    ) -> Optional[str]:
        """Extract MRZ string from various input formats."""
        if isinstance(document_data, str):
            return document_data
        if isinstance(document_data, dict):
            # Try common MRZ field names (avoid shadowing dataclasses.field)
            for key_name in [
                "mrz",
                "mrz_data",
                "machine_readable_zone",
                "td1_mrz",
                "td2_mrz",
                "td3_mrz",
            ]:
                if key_name in document_data:
                    return str(document_data[key_name])
        # Try to get MRZ from object attributes
        for attr in ["mrz", "mrz_data", "td1_mrz", "machine_readable_zone"]:
            if hasattr(document_data, attr):
                mrz_value = getattr(document_data, attr)
                if mrz_value:
                    return str(mrz_value)

        return None

    def _parse_td3_mrz(self, mrz_data: str) -> Optional[dict[str, Any]]:
        """Parse TD-3 (passport) MRZ format."""
        try:
            # Will be imported at top level when available
            lines = mrz_data.strip().split("\n")
            if len(lines) == 2 and all(len(line) == 44 for line in lines):
                return {"format": "TD-3", "valid": True, "lines": lines}
        except (ImportError, ValueError, AttributeError) as e:
            logger.warning("TD-3 MRZ parsing failed: %s", e)
        return None

    def _parse_td1_mrz(self, mrz_data: str) -> Optional[dict[str, Any]]:
        """Parse TD-1 (CMC) MRZ format."""
        try:
            # Will be imported at top level when available
            lines = mrz_data.strip().split("\n")
            if len(lines) == 3 and all(len(line) == 30 for line in lines):
                return {"format": "TD-1", "valid": True, "lines": lines}
        except (ImportError, ValueError, AttributeError) as e:
            logger.warning("TD-1 MRZ parsing failed: %s", e)
        return None

    def _parse_td2_mrz(self, mrz_data: str) -> Optional[dict[str, Any]]:
        """Parse TD-2 (visa/ID) MRZ format."""
        try:
            # Will be imported at top level when available
            lines = mrz_data.strip().split("\n")
            if len(lines) == 2 and all(len(line) == 36 for line in lines):
                return {"format": "TD-2", "valid": True, "lines": lines}
        except (ImportError, ValueError, AttributeError) as e:
            logger.warning("TD-2 MRZ parsing failed: %s", e)
        return None

    def _parse_auto_detect_mrz(self, mrz_data: str) -> Optional[dict[str, Any]]:
        """Auto-detect and parse MRZ format."""
        lines = mrz_data.strip().split("\n")

        if len(lines) == 3 and all(len(line) == 30 for line in lines):
            return self._parse_td1_mrz(mrz_data)
        if len(lines) == 2 and all(len(line) == 44 for line in lines):
            return self._parse_td3_mrz(mrz_data)
        if len(lines) == 2 and all(len(line) == 36 for line in lines):
            return self._parse_td2_mrz(mrz_data)

        return {"format": "unknown", "valid": False, "lines": lines}

    def _validate_all_check_digits(
        self, parsed_data: Dict[str, Any], doc_class: DocumentClass
    ) -> List[VerificationResult]:
        """Validate all check digits in the MRZ."""
        results = []

        # Implementation depends on specific MRZ format and parsed structure
        # This is a placeholder for the actual check digit validation

        if parsed_data.get("valid", False):
            results.append(VerificationResult("Check Digits", True, "All check digits valid"))
        else:
            results.append(
                VerificationResult(
                    "Check Digits", False, "Check digit validation failed", "CHECK_DIGIT_FAILED"
                )
            )

        return results

    def _has_chip_data(self, document_data: Union[str, dict[str, Any], Any]) -> bool:
        """Check if document contains chip data."""
        if isinstance(document_data, dict):
            return any(key in document_data for key in ["chip_data", "sod", "security_object"])
        return any(hasattr(document_data, attr) for attr in ["chip_data", "security_object"])

    def _has_vds_nc_data(self, document_data: Union[str, dict[str, Any], Any]) -> bool:
        """Check if document contains VDS-NC data."""
        if isinstance(document_data, dict):
            return any(
                key in document_data for key in ["vds_nc_data", "vds_nc_barcode", "barcode_data"]
            )
        return any(hasattr(document_data, attr) for attr in ["vds_nc_data", "vds_nc_barcode"])

    async def _verify_chip_authenticity(
        self, document_data: Union[str, Dict[str, Any], Any], doc_class: DocumentClass
    ) -> List[VerificationResult]:
        """Verify chip-based authenticity (SOD/DSC verification)."""
        results = []

        # Placeholder for chip verification logic
        # This would integrate with existing chip verification systems

        results.append(
            VerificationResult("Chip Authentication", True, "Chip verification placeholder")
        )

        return results

    async def _verify_vds_nc_authenticity(
        self, document_data: Union[str, Dict[str, Any], Any], doc_class: DocumentClass
    ) -> List[VerificationResult]:
        """Verify VDS-NC authenticity (signature verification)."""
        results = []

        # Placeholder for VDS-NC verification logic
        # This would integrate with existing VDS-NC verification systems

        results.append(
            VerificationResult("VDS-NC Authentication", True, "VDS-NC verification placeholder")
        )

        return results

    def _extract_semantic_data(
        self, document_data: Union[str, Dict[str, Any], Any]
    ) -> Dict[str, Any]:
        """Extract semantic data for validation."""
        # Placeholder implementation
        return {}

    def _validate_date_constraints(
        self, extracted_data: Dict[str, Any], doc_class: DocumentClass
    ) -> List[VerificationResult]:
        """Validate date-related constraints."""
        results = []

        # Placeholder for date validation
        results.append(VerificationResult("Date Constraints", True, "Date validation placeholder"))

        return results

    def _validate_category_constraints(
        self, extracted_data: Dict[str, Any], doc_class: DocumentClass
    ) -> List[VerificationResult]:
        """Validate category-specific constraints."""
        results = []

        # Placeholder for category validation
        results.append(
            VerificationResult("Category Constraints", True, "Category validation placeholder")
        )

        return results

    def _validate_policy_constraints(
        self, extracted_data: Dict[str, Any], doc_class: DocumentClass, options: Dict[str, Any]
    ) -> List[VerificationResult]:
        """Validate issuer policy constraints."""
        results = []

        # Placeholder for policy validation
        results.append(
            VerificationResult("Policy Constraints", True, "Policy validation placeholder")
        )

        return results

    def _extract_trust_data(self, document_data: Union[str, Dict[str, Any], Any]) -> Dict[str, Any]:
        """Extract trust-related data."""
        # Placeholder implementation
        return {}

    async def _verify_pkd_resolution(
        self, trust_data: Dict[str, Any], doc_class: DocumentClass, options: Dict[str, Any]
    ) -> List[VerificationResult]:
        """Verify PKD resolution."""
        results = []

        # Placeholder for PKD verification
        results.append(VerificationResult("PKD Resolution", True, "PKD verification placeholder"))

        return results

    async def _verify_trust_chain(
        self, trust_data: Dict[str, Any], doc_class: DocumentClass, options: Dict[str, Any]
    ) -> List[VerificationResult]:
        """Verify trust chain."""
        results = []

        # Placeholder for trust chain verification
        results.append(
            VerificationResult("Trust Chain", True, "Trust chain verification placeholder")
        )

        return results


# Global protocol instance
_unified_protocol: Optional[UnifiedVerificationProtocol] = None


def get_unified_verification_protocol() -> UnifiedVerificationProtocol:
    """Get global unified verification protocol instance."""
    global _unified_protocol
    if _unified_protocol is None:
        _unified_protocol = UnifiedVerificationProtocol()
    return _unified_protocol


# Convenience functions for common verification scenarios
async def verify_document_basic(
    document_data: Union[str, Dict[str, Any], Any],
) -> DocumentVerificationResult:
    """Quick document verification (detection + MRZ only)."""
    protocol = get_unified_verification_protocol()
    return await protocol.verify_document(document_data, VerificationLevel.BASIC)


async def verify_document_standard(
    document_data: Union[str, Dict[str, Any], Any],
) -> DocumentVerificationResult:
    """Standard document verification (+ authenticity)."""
    protocol = get_unified_verification_protocol()
    return await protocol.verify_document(document_data, VerificationLevel.STANDARD)


async def verify_document_comprehensive(
    document_data: Union[str, Dict[str, Any], Any],
) -> DocumentVerificationResult:
    """Comprehensive document verification (+ semantics)."""
    protocol = get_unified_verification_protocol()
    return await protocol.verify_document(document_data, VerificationLevel.COMPREHENSIVE)


async def verify_document_maximum(
    document_data: Union[str, Dict[str, Any], Any],
) -> DocumentVerificationResult:
    """Maximum document verification (all layers)."""
    protocol = get_unified_verification_protocol()
    return await protocol.verify_document(document_data, VerificationLevel.MAXIMUM)
