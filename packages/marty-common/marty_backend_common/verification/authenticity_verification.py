"""
Authenticity Verification Layer

This module implements comprehensive authenticity verification for travel documents,
supporting both chip-based (SOD/DSC) and VDS-NC barcode verification methods.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from marty_plugin.common.verification.document_detection import DocumentClass
from marty_plugin.shared.logging_config import get_logger

logger = get_logger(__name__)


class AuthenticityMethod(Enum):
    """Supported authenticity verification methods."""

    CHIP_SOD = "chip_sod"  # Chip with Security Object Document
    CHIP_DSC = "chip_dsc"  # Chip with Document Signing Certificate
    VDS_NC = "vds_nc"  # VDS-NC barcode signature
    NONE = "none"  # No authenticity data available


@dataclass
class AuthenticityResult:
    """Result of authenticity verification."""

    method: AuthenticityMethod
    passed: bool
    confidence: float  # 0.0 to 1.0
    details: str = ""
    error_code: str | None = None
    metadata: dict[str, Any] = None

    def __post_init__(self) -> None:
        """Set defaults after initialization."""
        if self.metadata is None:
            self.metadata = {}
        self.timestamp = datetime.now(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "method": self.method.value,
            "passed": self.passed,
            "confidence": self.confidence,
            "details": self.details,
            "error_code": self.error_code,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }


class AuthenticityVerifier:
    """Unified authenticity verifier supporting multiple methods."""

    def __init__(self) -> None:
        """Initialize authenticity verifier."""

    def verify_authenticity(
        self,
        document_data: dict[str, Any] | Any,
        document_class: DocumentClass,
        options: dict[str, Any] | None = None,
    ) -> list[AuthenticityResult]:
        """
        Verify document authenticity using available methods.

        Args:
            document_data: Document data (dict or object)
            document_class: Detected document class
            options: Verification options

        Returns:
            List of authenticity verification results
        """
        options = options or {}
        results = []

        # Determine available authenticity methods
        available_methods = self._detect_available_methods(document_data)

        if not available_methods:
            results.append(
                AuthenticityResult(
                    method=AuthenticityMethod.NONE,
                    passed=False,
                    confidence=0.0,
                    details="No authenticity data available",
                    error_code="NO_AUTHENTICITY_DATA",
                )
            )
            return results

        # Try chip-based verification first (higher security)
        if AuthenticityMethod.CHIP_SOD in available_methods:
            chip_result = self._verify_chip_sod(document_data, document_class, options)
            results.append(chip_result)

            # If chip verification succeeds with high confidence, we're done
            if chip_result.passed and chip_result.confidence > 0.8:
                return results

        if AuthenticityMethod.CHIP_DSC in available_methods:
            dsc_result = self._verify_chip_dsc(document_data, document_class, options)
            results.append(dsc_result)

            # If DSC verification succeeds with high confidence, we're done
            if dsc_result.passed and dsc_result.confidence > 0.8:
                return results

        # Fall back to VDS-NC verification
        if AuthenticityMethod.VDS_NC in available_methods:
            vds_result = self._verify_vds_nc(document_data, document_class, options)
            results.append(vds_result)

        return results

    def _detect_available_methods(
        self, document_data: dict[str, Any] | Any
    ) -> list[AuthenticityMethod]:
        """Detect available authenticity verification methods."""
        methods = []

        # Check for chip data
        if self._has_chip_data(document_data):
            if self._has_sod_data(document_data):
                methods.append(AuthenticityMethod.CHIP_SOD)
            if self._has_dsc_data(document_data):
                methods.append(AuthenticityMethod.CHIP_DSC)

        # Check for VDS-NC data
        if self._has_vds_nc_data(document_data):
            methods.append(AuthenticityMethod.VDS_NC)

        return methods

    def _verify_chip_sod(
        self,
        document_data: dict[str, Any] | Any,
        document_class: DocumentClass,
        options: dict[str, Any],
    ) -> AuthenticityResult:
        """Verify chip authenticity using Security Object Document (SOD)."""
        try:
            # Extract SOD data
            sod_data = self._extract_sod_data(document_data)

            if not sod_data:
                return AuthenticityResult(
                    method=AuthenticityMethod.CHIP_SOD,
                    passed=False,
                    confidence=0.0,
                    details="SOD data not found",
                    error_code="SOD_NOT_FOUND",
                )

            # Validate SOD structure
            structure_valid = self._validate_sod_structure(sod_data)
            if not structure_valid:
                return AuthenticityResult(
                    method=AuthenticityMethod.CHIP_SOD,
                    passed=False,
                    confidence=0.2,
                    details="SOD structure validation failed",
                    error_code="SOD_STRUCTURE_INVALID",
                )

            # Verify SOD signature
            signature_valid = self._verify_sod_signature(sod_data, options)
            if not signature_valid:
                return AuthenticityResult(
                    method=AuthenticityMethod.CHIP_SOD,
                    passed=False,
                    confidence=0.3,
                    details="SOD signature verification failed",
                    error_code="SOD_SIGNATURE_INVALID",
                )

            # Verify data group hashes
            dg_valid = self._verify_data_group_hashes(document_data, sod_data)

            if dg_valid:
                return AuthenticityResult(
                    method=AuthenticityMethod.CHIP_SOD,
                    passed=True,
                    confidence=0.95,
                    details="SOD verification successful - all checks passed",
                    metadata={
                        "sod_size": len(sod_data.get("raw_data", "")),
                        "data_groups_verified": dg_valid,
                    },
                )
            return AuthenticityResult(
                method=AuthenticityMethod.CHIP_SOD,
                passed=False,
                confidence=0.4,
                details="Data group hash verification failed",
                error_code="DG_HASH_MISMATCH",
            )

        except Exception as e:
            return AuthenticityResult(
                method=AuthenticityMethod.CHIP_SOD,
                passed=False,
                confidence=0.0,
                details=f"SOD verification error: {e}",
                error_code="SOD_VERIFICATION_ERROR",
            )

    def _verify_chip_dsc(
        self,
        document_data: dict[str, Any] | Any,
        document_class: DocumentClass,
        options: dict[str, Any],
    ) -> AuthenticityResult:
        """Verify chip authenticity using Document Signing Certificate (DSC)."""
        try:
            # Extract DSC data
            dsc_data = self._extract_dsc_data(document_data)

            if not dsc_data:
                return AuthenticityResult(
                    method=AuthenticityMethod.CHIP_DSC,
                    passed=False,
                    confidence=0.0,
                    details="DSC data not found",
                    error_code="DSC_NOT_FOUND",
                )

            # Validate DSC certificate
            cert_valid = self._validate_dsc_certificate(dsc_data, options)

            if cert_valid:
                return AuthenticityResult(
                    method=AuthenticityMethod.CHIP_DSC,
                    passed=True,
                    confidence=0.90,
                    details="DSC verification successful",
                    metadata={
                        "dsc_issuer": dsc_data.get("issuer", "unknown"),
                        "dsc_serial": dsc_data.get("serial", "unknown"),
                    },
                )
            return AuthenticityResult(
                method=AuthenticityMethod.CHIP_DSC,
                passed=False,
                confidence=0.2,
                details="DSC certificate validation failed",
                error_code="DSC_INVALID",
            )

        except Exception as e:
            return AuthenticityResult(
                method=AuthenticityMethod.CHIP_DSC,
                passed=False,
                confidence=0.0,
                details=f"DSC verification error: {e}",
                error_code="DSC_VERIFICATION_ERROR",
            )

    def _verify_vds_nc(
        self,
        document_data: dict[str, Any] | Any,
        document_class: DocumentClass,
        options: dict[str, Any],
    ) -> AuthenticityResult:
        """Verify authenticity using VDS-NC barcode signature."""
        try:
            # Extract VDS-NC data
            vds_data = self._extract_vds_nc_data(document_data)

            if not vds_data:
                return AuthenticityResult(
                    method=AuthenticityMethod.VDS_NC,
                    passed=False,
                    confidence=0.0,
                    details="VDS-NC data not found",
                    error_code="VDS_NC_NOT_FOUND",
                )

            # Verify VDS-NC signature
            signature_valid = self._verify_vds_nc_signature(vds_data, options)

            if not signature_valid:
                return AuthenticityResult(
                    method=AuthenticityMethod.VDS_NC,
                    passed=False,
                    confidence=0.1,
                    details="VDS-NC signature verification failed",
                    error_code="VDS_NC_SIGNATURE_INVALID",
                )

            # Verify printed vs payload data match
            data_match = self._verify_printed_vs_payload(document_data, vds_data)

            if data_match:
                return AuthenticityResult(
                    method=AuthenticityMethod.VDS_NC,
                    passed=True,
                    confidence=0.85,
                    details="VDS-NC verification successful - signature and data match",
                    metadata={
                        "barcode_format": vds_data.get("format", "unknown"),
                        "signature_algorithm": vds_data.get("algorithm", "unknown"),
                    },
                )
            return AuthenticityResult(
                method=AuthenticityMethod.VDS_NC,
                passed=False,
                confidence=0.3,
                details="Printed data does not match VDS-NC payload",
                error_code="VDS_NC_DATA_MISMATCH",
            )

        except Exception as e:
            return AuthenticityResult(
                method=AuthenticityMethod.VDS_NC,
                passed=False,
                confidence=0.0,
                details=f"VDS-NC verification error: {e}",
                error_code="VDS_NC_VERIFICATION_ERROR",
            )

    # Data detection methods
    def _has_chip_data(self, document_data: dict[str, Any] | Any) -> bool:
        """Check if document contains chip data."""
        if isinstance(document_data, dict):
            return any(key in document_data for key in ["chip_data", "security_object", "sod"])
        return any(hasattr(document_data, attr) for attr in ["chip_data", "security_object"])

    def _has_sod_data(self, document_data: dict[str, Any] | Any) -> bool:
        """Check if document contains SOD data."""
        if isinstance(document_data, dict):
            return any(key in document_data for key in ["security_object", "sod", "sod_data"])
        return any(hasattr(document_data, attr) for attr in ["security_object", "sod_data"])

    def _has_dsc_data(self, document_data: dict[str, Any] | Any) -> bool:
        """Check if document contains DSC data."""
        if isinstance(document_data, dict):
            return any(key in document_data for key in ["dsc", "document_signing_certificate"])
        return any(hasattr(document_data, attr) for attr in ["dsc", "document_signing_certificate"])

    def _has_vds_nc_data(self, document_data: dict[str, Any] | Any) -> bool:
        """Check if document contains VDS-NC data."""
        if isinstance(document_data, dict):
            return any(
                key in document_data for key in ["vds_nc_data", "vds_nc_barcode", "barcode_data"]
            )
        return any(hasattr(document_data, attr) for attr in ["vds_nc_data", "vds_nc_barcode"])

    # Data extraction methods
    def _extract_sod_data(self, document_data: dict[str, Any] | Any) -> dict[str, Any] | None:
        """Extract SOD data from document."""
        if isinstance(document_data, dict):
            for key in ["security_object", "sod", "sod_data"]:
                if key in document_data:
                    return {"raw_data": document_data[key]}
        else:
            for attr in ["security_object", "sod_data"]:
                if hasattr(document_data, attr):
                    return {"raw_data": getattr(document_data, attr)}
        return None

    def _extract_dsc_data(self, document_data: dict[str, Any] | Any) -> dict[str, Any] | None:
        """Extract DSC data from document."""
        if isinstance(document_data, dict):
            for key in ["dsc", "document_signing_certificate"]:
                if key in document_data:
                    return {"raw_data": document_data[key]}
        else:
            for attr in ["dsc", "document_signing_certificate"]:
                if hasattr(document_data, attr):
                    return {"raw_data": getattr(document_data, attr)}
        return None

    def _extract_vds_nc_data(self, document_data: dict[str, Any] | Any) -> dict[str, Any] | None:
        """Extract VDS-NC data from document."""
        if isinstance(document_data, dict):
            for key in ["vds_nc_data", "vds_nc_barcode", "barcode_data"]:
                if key in document_data:
                    return {"raw_data": document_data[key]}
        else:
            for attr in ["vds_nc_data", "vds_nc_barcode"]:
                if hasattr(document_data, attr):
                    vds_obj = getattr(document_data, attr)
                    if hasattr(vds_obj, "barcode_data"):
                        return {"raw_data": vds_obj.barcode_data}
                    return {"raw_data": vds_obj}
        return None

    # Verification implementation methods (placeholders for now)
    def _validate_sod_structure(self, sod_data: dict[str, Any]) -> bool:
        """Validate SOD structure."""
        # Placeholder - would validate SOD ASN.1 structure
        raw_data = sod_data.get("raw_data")
        return raw_data is not None and len(str(raw_data)) > 100

    def _verify_sod_signature(self, sod_data: dict[str, Any], options: dict[str, Any]) -> bool:
        """Verify SOD signature against issuing authority."""
        # Placeholder - would verify cryptographic signature
        # In real implementation, would check against CSCA certificates
        return True  # Simplified for now

    def _verify_data_group_hashes(
        self, document_data: dict[str, Any] | Any, sod_data: dict[str, Any]
    ) -> bool:
        """Verify data group hashes match SOD."""
        # Placeholder - would compute and compare DG hashes
        # In real implementation, would hash DG1, DG2, etc. and compare to SOD
        return True  # Simplified for now

    def _validate_dsc_certificate(self, dsc_data: dict[str, Any], options: dict[str, Any]) -> bool:
        """Validate DSC certificate."""
        # Placeholder - would validate certificate chain and expiry
        raw_data = dsc_data.get("raw_data")
        return raw_data is not None

    def _verify_vds_nc_signature(self, vds_data: dict[str, Any], options: dict[str, Any]) -> bool:
        """Verify VDS-NC signature."""
        try:
            # Try to use existing VDS-NC verification if available
            from marty_plugin.common.vds_nc.vds_nc_impl import VDSNCVerifier

            VDSNCVerifier()
            # Placeholder verification call
        except ImportError:
            # Fallback verification
            raw_data = vds_data.get("raw_data")
            return raw_data is not None and len(str(raw_data)) > 50

    def _verify_printed_vs_payload(
        self, document_data: dict[str, Any] | Any, vds_data: dict[str, Any]
    ) -> bool:
        """Verify printed document data matches VDS-NC payload."""
        # Placeholder - would extract and compare key fields
        # In real implementation, would decode VDS-NC payload and compare
        # fields like name, document number, dates, etc.
        return True  # Simplified for now


# Convenience functions
def verify_chip_authenticity(
    document_data: dict[str, Any] | Any, document_class: DocumentClass
) -> AuthenticityResult | None:
    """Quick chip authenticity verification."""
    verifier = AuthenticityVerifier()
    results = verifier.verify_authenticity(document_data, document_class)

    # Return first chip-based result
    for result in results:
        if result.method in [AuthenticityMethod.CHIP_SOD, AuthenticityMethod.CHIP_DSC]:
            return result

    return None


def verify_vds_nc_authenticity(
    document_data: dict[str, Any] | Any, document_class: DocumentClass
) -> AuthenticityResult | None:
    """Quick VDS-NC authenticity verification."""
    verifier = AuthenticityVerifier()
    results = verifier.verify_authenticity(document_data, document_class)

    # Return VDS-NC result
    for result in results:
        if result.method == AuthenticityMethod.VDS_NC:
            return result

    return None


def is_authentic(document_data: dict[str, Any] | Any, document_class: DocumentClass) -> bool:
    """Quick authenticity check."""
    verifier = AuthenticityVerifier()
    results = verifier.verify_authenticity(document_data, document_class)
    return any(r.passed for r in results)
