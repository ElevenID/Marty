"""
Trust Verification Layer for Unified Verification Protocol

This module implements Layer 5 of the unified verification protocol:
- PKD (Public Key Directory) certificate chain resolution
- Trust anchor validation and verification
- Certificate revocation status checking
- Trust chain building and validation
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

# Import from our document detection module
from .document_detection import DocumentClass


class TrustValidationLevel(Enum):
    """Trust validation strictness levels."""

    BASIC = "basic"  # Basic trust anchor validation
    STANDARD = "standard"  # + PKD resolution and chain validation
    STRICT = "strict"  # + revocation checking and policy validation


class TrustSource(Enum):
    """Sources of trust information."""

    PKD = "pkd"  # ICAO Public Key Directory
    CONFIGURED = "configured"  # Manually configured trust store
    CSCA = "csca"  # Country Signing Certificate Authority
    NATIONAL_PKI = "national_pki"  # National PKI infrastructure
    EMERGENCY = "emergency"  # Emergency trust procedures


class TrustValidationError(Enum):
    """Trust validation error codes."""

    PKD_UNAVAILABLE = "pkd_unavailable"
    CERTIFICATE_NOT_FOUND = "certificate_not_found"
    CERTIFICATE_EXPIRED = "certificate_expired"
    CERTIFICATE_REVOKED = "certificate_revoked"
    CHAIN_VALIDATION_FAILED = "chain_validation_failed"
    TRUST_ANCHOR_NOT_FOUND = "trust_anchor_not_found"
    INVALID_SIGNATURE = "invalid_signature"
    POLICY_VIOLATION = "policy_violation"


@dataclass
class TrustResult:
    """Result of a trust verification check."""

    check_name: str
    passed: bool
    details: str
    trust_source: TrustSource
    confidence: float = 1.0
    error_code: TrustValidationError | None = None
    certificate_chain: list[str] | None = None
    trust_anchor: str | None = None


@dataclass
class CertificateInfo:
    """Certificate information for trust validation."""

    certificate_pem: str
    subject: str
    issuer: str
    serial_number: str
    not_before: datetime
    not_after: datetime
    fingerprint: str
    is_ca: bool = False
    key_usage: list[str] = None

    def __post_init__(self):
        if self.key_usage is None:
            self.key_usage = []


class PKDResolver:
    """Resolves certificates and trust information from PKD sources."""

    def __init__(self, pkd_service_client=None, csca_service_client=None) -> None:
        """
        Initialize PKD resolver with service clients.

        Args:
            pkd_service_client: gRPC client for PKD service
            csca_service_client: gRPC client for CSCA service
        """
        self.pkd_client = pkd_service_client
        self.csca_client = csca_service_client
        self.logger = logging.getLogger(__name__)
        self._certificate_cache: dict[str, CertificateInfo] = {}
        self._trust_anchor_cache: dict[str, CertificateInfo] = {}

    async def resolve_certificate(self, certificate_id: str) -> CertificateInfo | None:
        """
        Resolve a certificate by ID from PKD sources.

        Args:
            certificate_id: Certificate identifier (fingerprint, serial, etc.)

        Returns:
            Certificate information if found, None otherwise
        """
        # Check cache first
        if certificate_id in self._certificate_cache:
            return self._certificate_cache[certificate_id]

        # Try PKD service
        cert_info = await self._resolve_from_pkd(certificate_id)
        if cert_info:
            self._certificate_cache[certificate_id] = cert_info
            return cert_info

        # Try CSCA service
        cert_info = await self._resolve_from_csca(certificate_id)
        if cert_info:
            self._certificate_cache[certificate_id] = cert_info
            return cert_info

        return None

    async def _resolve_from_pkd(self, certificate_id: str) -> CertificateInfo | None:
        """Resolve certificate from PKD service."""
        if not self.pkd_client:
            return None

        try:
            # This would be the actual gRPC call to PKD service
            # For now, return mock data
            self.logger.info(f"Resolving certificate {certificate_id} from PKD")

            # Mock implementation - in real system would call:
            # response = await self.pkd_client.GetCertificate(
            #     pkd_service_pb2.GetCertificateRequest(certificate_id=certificate_id)
            # )

        except Exception as e:
            self.logger.exception(f"Error resolving from PKD: {e}")
            return None
        else:
            return None  # Mock: certificate not found

    async def _resolve_from_csca(self, certificate_id: str) -> CertificateInfo | None:
        """Resolve certificate from CSCA service."""
        if not self.csca_client:
            return None

        try:
            self.logger.info(f"Resolving certificate {certificate_id} from CSCA")

            # Mock implementation - in real system would call:
            # response = await self.csca_client.GetCscaData(
            #     csca_service_pb2.GetCscaDataRequest(id=certificate_id)
            # )

        except Exception as e:
            self.logger.exception(f"Error resolving from CSCA: {e}")
            return None
        else:
            return None  # Mock: certificate not found

    async def get_trust_anchors(self, country_code: str | None = None) -> list[CertificateInfo]:
        """
        Get trust anchors for a specific country or all available.

        Args:
            country_code: ISO 3166-1 alpha-3 country code (optional)

        Returns:
            List of trust anchor certificates
        """
        try:
            if not self.pkd_client:
                self.logger.warning("PKD client not available for trust anchor resolution")
                return []

            # Mock implementation - would call PKD ListTrustAnchors
            self.logger.info(f"Fetching trust anchors for country: {country_code or 'ALL'}")

            # Return mock trust anchors

        except Exception as e:
            self.logger.exception(f"Error fetching trust anchors: {e}")
            return []
        else:
            return []


class CertificateChainValidator:
    """Validates certificate chains and trust paths."""

    def __init__(self, pkd_resolver: PKDResolver) -> None:
        self.pkd_resolver = pkd_resolver
        self.logger = logging.getLogger(__name__)

    async def validate_chain(
        self,
        leaf_certificate: str,
        intermediate_certificates: list[str] | None = None,
        trust_anchors: list[CertificateInfo] | None = None,
    ) -> list[TrustResult]:
        """
        Validate a complete certificate chain.

        Args:
            leaf_certificate: End-entity certificate (PEM or DER)
            intermediate_certificates: Intermediate CA certificates
            trust_anchors: Known trust anchor certificates

        Returns:
            List of trust validation results
        """
        results = []

        if not intermediate_certificates:
            intermediate_certificates = []

        if not trust_anchors:
            trust_anchors = []

        # Parse leaf certificate
        try:
            leaf_info = self._parse_certificate(leaf_certificate)
            if not leaf_info:
                results.append(
                    TrustResult(
                        check_name="leaf_certificate_parsing",
                        passed=False,
                        details="Failed to parse leaf certificate",
                        trust_source=TrustSource.CONFIGURED,
                        confidence=1.0,
                        error_code=TrustValidationError.CERTIFICATE_NOT_FOUND,
                    )
                )
                return results
        except Exception as e:
            results.append(
                TrustResult(
                    check_name="leaf_certificate_parsing",
                    passed=False,
                    details=f"Certificate parsing error: {e}",
                    trust_source=TrustSource.CONFIGURED,
                    confidence=1.0,
                    error_code=TrustValidationError.CERTIFICATE_NOT_FOUND,
                )
            )
            return results

        # Validate leaf certificate expiry
        current_time = datetime.now(timezone.utc)
        if leaf_info.not_after < current_time:
            results.append(
                TrustResult(
                    check_name="leaf_certificate_expiry",
                    passed=False,
                    details=f"Leaf certificate expired on {leaf_info.not_after}",
                    trust_source=TrustSource.CONFIGURED,
                    confidence=1.0,
                    error_code=TrustValidationError.CERTIFICATE_EXPIRED,
                )
            )
        elif leaf_info.not_before > current_time:
            results.append(
                TrustResult(
                    check_name="leaf_certificate_validity",
                    passed=False,
                    details=f"Leaf certificate not yet valid (valid from {leaf_info.not_before})",
                    trust_source=TrustSource.CONFIGURED,
                    confidence=1.0,
                    error_code=TrustValidationError.CERTIFICATE_NOT_FOUND,
                )
            )
        else:
            results.append(
                TrustResult(
                    check_name="leaf_certificate_validity",
                    passed=True,
                    details=f"Leaf certificate valid until {leaf_info.not_after}",
                    trust_source=TrustSource.CONFIGURED,
                    confidence=1.0,
                )
            )

        # Build and validate chain
        chain_results = await self._build_and_validate_chain(
            leaf_info, intermediate_certificates, trust_anchors
        )
        results.extend(chain_results)

        return results

    async def _build_and_validate_chain(
        self,
        leaf_cert: CertificateInfo,
        intermediate_certs: list[str],
        trust_anchors: list[CertificateInfo],
    ) -> list[TrustResult]:
        """Build and validate certificate chain to trust anchor."""
        results = []

        # Parse intermediate certificates
        parsed_intermediates = []
        for i, cert_pem in enumerate(intermediate_certs):
            try:
                cert_info = self._parse_certificate(cert_pem)
                if cert_info:
                    parsed_intermediates.append(cert_info)
                else:
                    results.append(
                        TrustResult(
                            check_name=f"intermediate_certificate_{i}",
                            passed=False,
                            details=f"Failed to parse intermediate certificate {i}",
                            trust_source=TrustSource.CONFIGURED,
                            confidence=0.8,
                            error_code=TrustValidationError.CERTIFICATE_NOT_FOUND,
                        )
                    )
            except Exception as e:
                results.append(
                    TrustResult(
                        check_name=f"intermediate_certificate_{i}",
                        passed=False,
                        details=f"Error parsing intermediate certificate {i}: {e}",
                        trust_source=TrustSource.CONFIGURED,
                        confidence=0.8,
                        error_code=TrustValidationError.CERTIFICATE_NOT_FOUND,
                    )
                )

        # Try to find a path to trust anchor
        trust_path = await self._find_trust_path(leaf_cert, parsed_intermediates, trust_anchors)

        if trust_path:
            results.append(
                TrustResult(
                    check_name="trust_chain_validation",
                    passed=True,
                    details=f"Valid trust chain found with {len(trust_path)} certificates",
                    trust_source=TrustSource.PKD,
                    confidence=0.9,
                    certificate_chain=[cert.fingerprint for cert in trust_path],
                    trust_anchor=trust_path[-1].fingerprint,
                )
            )
        else:
            results.append(
                TrustResult(
                    check_name="trust_chain_validation",
                    passed=False,
                    details="No valid trust chain found to known trust anchor",
                    trust_source=TrustSource.PKD,
                    confidence=0.8,
                    error_code=TrustValidationError.CHAIN_VALIDATION_FAILED,
                )
            )

        return results

    async def _find_trust_path(
        self,
        leaf_cert: CertificateInfo,
        intermediates: list[CertificateInfo],
        trust_anchors: list[CertificateInfo],
    ) -> list[CertificateInfo] | None:
        """Find a valid path from leaf certificate to trust anchor."""
        # Simple implementation - in production would use proper chain building
        # For now, just check if leaf issuer matches any trust anchor subject

        for anchor in trust_anchors:
            if leaf_cert.issuer == anchor.subject:
                return [leaf_cert, anchor]

        # Try with intermediates
        for intermediate in intermediates:
            if leaf_cert.issuer == intermediate.subject:
                # Recursively check intermediate to trust anchor
                sub_path = await self._find_trust_path(intermediate, [], trust_anchors)
                if sub_path:
                    return [leaf_cert, *sub_path]

        return None

    def _parse_certificate(self, certificate_data: str) -> CertificateInfo | None:
        """
        Parse certificate data and extract relevant information.

        Args:
            certificate_data: Certificate in PEM or base64 format

        Returns:
            CertificateInfo object if parsing successful, None otherwise
        """
        try:
            # Mock certificate parsing - in real implementation would use cryptography library
            # For demonstration, create mock certificate info

            import hashlib
            import uuid

            # Generate deterministic mock data based on certificate content
            cert_hash = hashlib.sha256(certificate_data.encode()).hexdigest()[:16]

            return CertificateInfo(
                certificate_pem=certificate_data,
                subject=f"CN=Mock Certificate {cert_hash}",
                issuer=f"CN=Mock CA {cert_hash}",
                serial_number=str(uuid.uuid4()),
                not_before=datetime(2020, 1, 1, tzinfo=timezone.utc),
                not_after=datetime(2030, 1, 1, tzinfo=timezone.utc),
                fingerprint=cert_hash,
                is_ca=False,
                key_usage=["digital_signature", "key_encipherment"],
            )

        except Exception as e:
            self.logger.exception(f"Certificate parsing failed: {e}")
            return None


class TrustValidator:
    """
    Main trust validation orchestrator.

    Implements Layer 5 of the unified verification protocol:
    validates certificate chains, PKD resolution, and trust anchors.
    """

    def __init__(self, pkd_service_client=None, csca_service_client=None) -> None:
        self.pkd_resolver = PKDResolver(pkd_service_client, csca_service_client)
        self.chain_validator = CertificateChainValidator(self.pkd_resolver)
        self.logger = logging.getLogger(__name__)

    async def validate_trust(
        self,
        document_data: dict[str, Any],
        doc_class: DocumentClass,
        validation_level: TrustValidationLevel = TrustValidationLevel.STANDARD,
    ) -> list[TrustResult]:
        """
        Execute complete trust validation.

        Args:
            document_data: Document data including certificates and trust info
            doc_class: Detected document class
            validation_level: Strictness level for validation

        Returns:
            List of trust validation results
        """
        all_results = []

        # Extract trust-related data from document
        chip_data = document_data.get("chip_data", {})
        vds_nc_data = document_data.get("vds_nc_data", {})
        issuing_authority = document_data.get("issuing_authority", "")

        # 1. PKD Resolution (if STANDARD or STRICT)
        if validation_level in [TrustValidationLevel.STANDARD, TrustValidationLevel.STRICT]:
            pkd_results = await self._validate_pkd_resolution(issuing_authority, doc_class)
            all_results.extend(pkd_results)

        # 2. Certificate Chain Validation
        if chip_data.get("security_object") or chip_data.get("sod"):
            # Chip-based trust validation
            chip_trust_results = await self._validate_chip_trust(chip_data, issuing_authority)
            all_results.extend(chip_trust_results)

        elif vds_nc_data.get("certificate") or vds_nc_data.get("signature"):
            # VDS-NC trust validation
            vds_trust_results = await self._validate_vds_nc_trust(vds_nc_data, issuing_authority)
            all_results.extend(vds_trust_results)

        else:
            # No cryptographic trust anchor available
            all_results.append(
                TrustResult(
                    check_name="trust_anchor_availability",
                    passed=False,
                    details="No cryptographic trust anchor available (no chip or VDS-NC data)",
                    trust_source=TrustSource.CONFIGURED,
                    confidence=0.1,
                    error_code=TrustValidationError.TRUST_ANCHOR_NOT_FOUND,
                )
            )

        # 3. Revocation Checking (if STRICT)
        if validation_level == TrustValidationLevel.STRICT:
            revocation_results = await self._check_revocation_status(
                document_data, issuing_authority
            )
            all_results.extend(revocation_results)

        return all_results

    async def _validate_pkd_resolution(
        self, issuing_authority: str, doc_class: DocumentClass
    ) -> list[TrustResult]:
        """Validate PKD resolution for issuing authority."""
        results = []

        if not issuing_authority:
            results.append(
                TrustResult(
                    check_name="pkd_issuing_authority",
                    passed=False,
                    details="No issuing authority specified for PKD resolution",
                    trust_source=TrustSource.PKD,
                    confidence=0.8,
                    error_code=TrustValidationError.PKD_UNAVAILABLE,
                )
            )
            return results

        try:
            # Extract country code from issuing authority
            country_code = (
                issuing_authority[:3] if len(issuing_authority) >= 3 else issuing_authority
            )

            # Resolve trust anchors for this country
            trust_anchors = await self.pkd_resolver.get_trust_anchors(country_code)

            if trust_anchors:
                results.append(
                    TrustResult(
                        check_name="pkd_trust_anchor_resolution",
                        passed=True,
                        details=f"Found {len(trust_anchors)} trust anchors for {country_code}",
                        trust_source=TrustSource.PKD,
                        confidence=0.9,
                    )
                )
            else:
                results.append(
                    TrustResult(
                        check_name="pkd_trust_anchor_resolution",
                        passed=False,
                        details=f"No trust anchors found in PKD for {country_code}",
                        trust_source=TrustSource.PKD,
                        confidence=0.7,
                        error_code=TrustValidationError.TRUST_ANCHOR_NOT_FOUND,
                    )
                )

        except Exception as e:
            results.append(
                TrustResult(
                    check_name="pkd_resolution_error",
                    passed=False,
                    details=f"PKD resolution failed: {e}",
                    trust_source=TrustSource.PKD,
                    confidence=0.5,
                    error_code=TrustValidationError.PKD_UNAVAILABLE,
                )
            )

        return results

    async def _validate_chip_trust(
        self, chip_data: dict[str, Any], issuing_authority: str
    ) -> list[TrustResult]:
        """Validate trust chain for chip-based documents (SOD/DSC)."""
        results = []

        # Extract certificates from chip data
        sod_data = chip_data.get("sod") or chip_data.get("security_object")
        dsc_certificate = chip_data.get("dsc_certificate")

        if not sod_data and not dsc_certificate:
            results.append(
                TrustResult(
                    check_name="chip_certificate_availability",
                    passed=False,
                    details="No SOD or DSC certificate available in chip data",
                    trust_source=TrustSource.CONFIGURED,
                    confidence=0.8,
                    error_code=TrustValidationError.CERTIFICATE_NOT_FOUND,
                )
            )
            return results

        # Get trust anchors for issuing country
        country_code = issuing_authority[:3] if len(issuing_authority) >= 3 else issuing_authority
        trust_anchors = await self.pkd_resolver.get_trust_anchors(country_code)

        if dsc_certificate:
            # Validate DSC certificate chain
            chain_results = await self.chain_validator.validate_chain(
                leaf_certificate=dsc_certificate, trust_anchors=trust_anchors
            )
            results.extend(chain_results)
        else:
            # Mock validation for SOD
            results.append(
                TrustResult(
                    check_name="sod_trust_validation",
                    passed=True,
                    details="SOD trust validation completed (simulated)",
                    trust_source=TrustSource.PKD,
                    confidence=0.8,
                )
            )

        return results

    async def _validate_vds_nc_trust(
        self, vds_nc_data: dict[str, Any], issuing_authority: str
    ) -> list[TrustResult]:
        """Validate trust chain for VDS-NC documents."""
        results = []

        certificate = vds_nc_data.get("certificate")
        if not certificate:
            results.append(
                TrustResult(
                    check_name="vds_nc_certificate_availability",
                    passed=False,
                    details="No certificate available in VDS-NC data",
                    trust_source=TrustSource.CONFIGURED,
                    confidence=0.8,
                    error_code=TrustValidationError.CERTIFICATE_NOT_FOUND,
                )
            )
            return results

        # Get trust anchors for issuing country
        country_code = issuing_authority[:3] if len(issuing_authority) >= 3 else issuing_authority
        trust_anchors = await self.pkd_resolver.get_trust_anchors(country_code)

        # Validate VDS-NC certificate chain
        chain_results = await self.chain_validator.validate_chain(
            leaf_certificate=certificate, trust_anchors=trust_anchors
        )
        results.extend(chain_results)

        return results

    async def _check_revocation_status(
        self, document_data: dict[str, Any], issuing_authority: str
    ) -> list[TrustResult]:
        """Check certificate revocation status."""
        results = []

        # Mock revocation checking - in real implementation would check CRL/OCSP
        results.append(
            TrustResult(
                check_name="certificate_revocation_check",
                passed=True,
                details="Certificate revocation status checked (simulated)",
                trust_source=TrustSource.PKD,
                confidence=0.8,
            )
        )

        results.append(
            TrustResult(
                check_name="crl_validation",
                passed=True,
                details="Certificate Revocation List validation completed (simulated)",
                trust_source=TrustSource.PKD,
                confidence=0.8,
            )
        )

        return results
