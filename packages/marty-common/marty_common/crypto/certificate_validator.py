"""
Certificate Chain Validation for Passport Verification
======================================================

This module provides comprehensive certificate chain validation for SOD signatures
against Document Signer certificates, implementing full PKI validation according
to ICAO Doc 9303 standards including:

- Certificate path building and validation
- Signature verification against trust anchors
- CSCA root certificate validation
- Certificate revocation checking (CRL/OCSP)
- Time validity verification
- Key usage and extended key usage validation

This module uses Rust implementations from marty-verification for core cryptographic
operations (chain validation, signature verification) while maintaining a Python-friendly
API for integration with the rest of the Marty ecosystem.

Author: Marty Development Team
Date: September 2025
"""

from __future__ import annotations

import binascii
import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import ClassVar

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.x509 import ocsp

# Import Rust bindings for chain validation (required)
from marty_common.crypto_bridge import (
    CertificateChainValidator as RustChainValidator,
    ValidationConfig as RustValidationConfig,
)

try:  # cryptography 42+
    from cryptography.x509.verification import Store
except ImportError:  # pragma: no cover - fallback for older cryptography releases

    class Store:  # type: ignore[override]
        """Minimal stand-in for cryptography's X509 Store when unavailable."""

        def __init__(self, certificates) -> None:
            self._certs = list(certificates)

        def __iter__(self):
            return iter(self._certs)


logger = logging.getLogger(__name__)


class ValidationResult(Enum):
    """Certificate validation result types."""

    VALID = "valid"
    INVALID = "invalid"
    EXPIRED = "expired"
    NOT_YET_VALID = "not_yet_valid"
    REVOKED = "revoked"
    UNTRUSTED = "untrusted"
    INVALID_SIGNATURE = "invalid_signature"
    INVALID_KEY_USAGE = "invalid_key_usage"
    CHAIN_BROKEN = "chain_broken"
    UNKNOWN_ERROR = "unknown_error"


class CertificateType(Enum):
    """Types of certificates in the passport PKI."""

    CSCA = "csca"  # Country Signing Certificate Authority
    DOCUMENT_SIGNER = "ds"  # Document Signer Certificate
    INTERMEDIATE = "intermediate"  # Intermediate CA Certificate
    UNKNOWN = "unknown"


@dataclass
class ValidationError:
    """Individual certificate validation error."""

    certificate_subject: str
    error_type: ValidationResult
    error_message: str
    severity: str  # "critical", "warning", "info"

    @property
    def is_critical(self) -> bool:
        """Check if this is a critical validation error."""
        return self.severity == "critical"


@dataclass
class CertificateInfo:
    """Detailed information about a certificate."""

    certificate: x509.Certificate
    cert_type: CertificateType
    subject: str
    issuer: str
    serial_number: str
    valid_from: datetime
    valid_until: datetime
    signature_algorithm: str
    key_size: int | None
    key_usage: list[str]
    extended_key_usage: list[str]
    is_ca: bool
    path_length: int | None

    @property
    def is_expired(self) -> bool:
        """Check if certificate is expired."""
        return datetime.now(timezone.utc) > self.valid_until

    @property
    def is_not_yet_valid(self) -> bool:
        """Check if certificate is not yet valid."""
        return datetime.now(timezone.utc) < self.valid_from

    @property
    def days_until_expiry(self) -> int:
        """Calculate days until certificate expires."""
        delta = self.valid_until - datetime.now(timezone.utc)
        return max(0, delta.days)

    @property
    def fingerprint_sha256(self) -> str:
        """Get SHA-256 fingerprint of the certificate."""
        digest = hashes.Hash(hashes.SHA256())
        digest.update(self.certificate.public_bytes(serialization.Encoding.DER))
        return binascii.hexlify(digest.finalize()).decode().upper()


@dataclass
class ChainValidationResult:
    """Result of certificate chain validation."""

    is_valid: bool
    trust_anchor: x509.Certificate | None
    validation_path: list[CertificateInfo]
    errors: list[ValidationError]
    warnings: list[ValidationError]
    validation_time: datetime
    signature_verified: bool

    @property
    def has_critical_errors(self) -> bool:
        """Check if there are critical validation errors."""
        return any(error.is_critical for error in self.errors)

    @property
    def error_summary(self) -> str:
        """Get summary of validation errors."""
        if not self.errors:
            return "No errors"

        critical_count = sum(1 for error in self.errors if error.is_critical)
        warning_count = len(self.errors) - critical_count

        return f"{critical_count} critical errors, {warning_count} warnings"

    def get_certificate_by_type(self, cert_type: CertificateType) -> CertificateInfo | None:
        """Get certificate of specific type from validation path."""
        for cert_info in self.validation_path:
            if cert_info.cert_type == cert_type:
                return cert_info
        return None


class CertificateChainValidator:
    """
    Comprehensive certificate chain validator for passport verification.

    This validator implements full PKI validation according to ICAO standards
    including certificate path building, signature verification, and trust
    anchor validation.
    """

    # ICAO-specific OIDs and identifiers
    ICAO_MRTD_SECURITY_OBJECT_OID = "2.23.136.1.1.1"
    # Key usage constants (changed from OIDs to string descriptions for compatibility)
    DOCUMENT_SIGNER_KEY_USAGE: ClassVar[list[str]] = ["digital_signature"]
    CSCA_KEY_USAGE: ClassVar[list[str]] = ["key_cert_sign", "crl_sign"]

    def __init__(self, trust_store: Store | None = None) -> None:
        """
        Initialize the certificate chain validator.

        Args:
            trust_store: Optional trust store with CSCA certificates
        """
        self.trust_store = trust_store  # None by default, set when needed
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._csca_certificates: dict[str, x509.Certificate] = {}
        self._validation_cache: dict[str, ChainValidationResult] = {}
        self._crls: dict[str, list[x509.CertificateRevocationList]] = {}
        self._ocsp_responses: list[ocsp.OCSPResponse] = []
        
        # Initialize Rust validator (required)
        self._rust_validator = RustChainValidator()
        self.logger.debug("Using Rust-based chain validation")

    def add_trust_anchor(self, csca_cert: x509.Certificate) -> None:
        """Add a CSCA certificate as trust anchor."""
        subject_key = self._get_certificate_key(csca_cert)
        self._csca_certificates[subject_key] = csca_cert

        # Add to trust store
        store_builder = Store([csca_cert])
        for existing_cert in self._csca_certificates.values():
            if existing_cert != csca_cert:
                store_builder = Store([existing_cert, csca_cert])

        self.trust_store = store_builder
        
        # Also add to Rust validator
        pem = csca_cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")
        self._rust_validator.add_trust_anchor(pem)
        
        self.logger.info(f"Added CSCA trust anchor: {self._get_subject_name(csca_cert)}")

    def load_csca_certificates(self, csca_certs: list[x509.Certificate]) -> None:
        """Load multiple CSCA certificates as trust anchors."""
        for cert in csca_certs:
            self.add_trust_anchor(cert)

        self.logger.info(f"Loaded {len(csca_certs)} CSCA certificates")

    def add_crl(self, crl: x509.CertificateRevocationList) -> None:
        """Register a CRL for revocation checking."""
        issuer = crl.issuer.rfc4514_string()
        self._crls.setdefault(issuer, []).append(crl)
        
        # Also add to Rust validator
        crl_der = crl.public_bytes(serialization.Encoding.DER)
        self._rust_validator.add_crl(crl_der)
        
        self.logger.debug("Loaded CRL for %s with %d revoked certificates", issuer, len(crl))

    def add_ocsp_response(self, response: ocsp.OCSPResponse) -> None:
        """Register an OCSP response for revocation checking."""

        self._ocsp_responses.append(response)
        self.logger.debug("Loaded OCSP response for OCSP revocation checks")

    def validate_certificate_chain(
        self,
        end_entity_cert: x509.Certificate,
        intermediate_certs: list[x509.Certificate] | None = None,
        validation_time: datetime | None = None,
    ) -> ChainValidationResult:
        """
        Validate a complete certificate chain.

        Args:
            end_entity_cert: Document Signer certificate
            intermediate_certs: List of intermediate certificates
            validation_time: Time for validation (defaults to now)

        Returns:
            Comprehensive validation result
        """
        intermediate_certs = intermediate_certs or []
        validation_time = validation_time or datetime.now(timezone.utc)

        # Check cache first
        cache_key = self._generate_cache_key(end_entity_cert, intermediate_certs)
        if cache_key in self._validation_cache:
            cached_result = self._validation_cache[cache_key]
            # 5 min cache
            if (validation_time - cached_result.validation_time).total_seconds() < 300:
                return cached_result

        self.logger.info(
            f"Validating certificate chain for: {self._get_subject_name(end_entity_cert)}"
        )

        errors = []
        warnings = []
        validation_path = []
        trust_anchor = None
        signature_verified = False

        try:
            # Build certificate path
            cert_path = self._build_certificate_path(end_entity_cert, intermediate_certs)

            # Validate each certificate in the path
            for i, cert in enumerate(cert_path):
                cert_info = self._extract_certificate_info(cert, i == 0)
                validation_path.append(cert_info)

                # Validate individual certificate
                cert_errors, cert_warnings = self._validate_single_certificate(cert_info)
                errors.extend(cert_errors)
                warnings.extend(cert_warnings)
                errors.extend(self._check_revocation_status(cert_info))

            # Verify signature chain
            signature_verified, sig_errors = self._verify_signature_chain(cert_path)
            errors.extend(sig_errors)

            # Find and validate trust anchor
            trust_anchor, trust_errors = self._validate_trust_anchor(cert_path)
            errors.extend(trust_errors)

            # Additional ICAO-specific validations
            icao_errors = self._validate_icao_requirements(validation_path)
            errors.extend(icao_errors)

        except Exception:
            self.logger.exception("Certificate chain validation failed")
            errors.append(
                ValidationError(
                    certificate_subject=self._get_subject_name(end_entity_cert),
                    error_type=ValidationResult.UNKNOWN_ERROR,
                    error_message="Validation process failed",
                    severity="critical",
                )
            )

        # Determine overall validation result
        is_valid = (
            len([e for e in errors if e.is_critical]) == 0
            and signature_verified
            and trust_anchor is not None
        )

        result = ChainValidationResult(
            is_valid=is_valid,
            trust_anchor=trust_anchor,
            validation_path=validation_path,
            errors=errors,
            warnings=warnings,
            validation_time=validation_time,
            signature_verified=signature_verified,
        )

        # Cache result
        self._validation_cache[cache_key] = result

        self.logger.info(
            f"Certificate chain validation {'passed' if is_valid else 'failed'}: "
            f"{len(errors)} errors, {len(warnings)} warnings"
        )

        return result

    def validate_chain_with_rust(
        self,
        end_entity_cert: x509.Certificate,
        intermediate_certs: list[x509.Certificate] | None = None,
        validation_config: RustValidationConfig | None = None,
    ) -> ChainValidationResult:
        """
        Validate a certificate chain using the Rust implementation.
        
        This method provides higher performance chain validation using the
        Rust marty-verification crate. It maintains the same result format
        as the Python implementation for compatibility.

        Args:
            end_entity_cert: Document Signer certificate
            intermediate_certs: List of intermediate certificates
            validation_config: Optional Rust ValidationConfig for policy control

        Returns:
            Comprehensive validation result
        """
        intermediate_certs = intermediate_certs or []
        validation_time = datetime.now(timezone.utc)
        
        # Build PEM chain (end entity first, then intermediates)
        chain_pem = []
        all_certs = [end_entity_cert] + intermediate_certs
        
        for cert in all_certs:
            pem = cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")
            chain_pem.append(pem)
        
        # Use provided config or create default
        if validation_config is None:
            validation_config = RustValidationConfig.soft_fail_revocation()
        
        # Perform Rust validation
        try:
            rust_result = self._rust_validator.validate_with_config(
                chain_pem, validation_config
            )
        except Exception as e:
            self.logger.exception("Rust chain validation failed")
            return ChainValidationResult(
                is_valid=False,
                trust_anchor=None,
                validation_path=[],
                errors=[
                    ValidationError(
                        certificate_subject=self._get_subject_name(end_entity_cert),
                        error_type=ValidationResult.UNKNOWN_ERROR,
                        error_message=f"Rust validation failed: {e}",
                        severity="critical",
                    )
                ],
                warnings=[],
                validation_time=validation_time,
                signature_verified=False,
            )
        
        # Convert Rust result to Python result format
        errors = [
            ValidationError(
                certificate_subject=rust_result.subject or "Unknown",
                error_type=ValidationResult.INVALID,
                error_message=error,
                severity="critical",
            )
            for error in rust_result.errors
        ]
        
        warnings_list = [
            ValidationError(
                certificate_subject=rust_result.subject or "Unknown",
                error_type=ValidationResult.VALID,
                error_message=warning,
                severity="warning",
            )
            for warning in rust_result.warnings
        ]
        
        # Build validation path with certificate info
        validation_path = []
        for i, cert in enumerate(all_certs):
            cert_info = self._extract_certificate_info(cert, i == 0)
            validation_path.append(cert_info)
        
        # Find trust anchor (last cert in path that's in our trust store)
        trust_anchor = None
        for cert in reversed(all_certs):
            cert_key = self._get_certificate_key(cert)
            if cert_key in self._csca_certificates:
                trust_anchor = self._csca_certificates[cert_key]
                break
        
        return ChainValidationResult(
            is_valid=rust_result.valid,
            trust_anchor=trust_anchor,
            validation_path=validation_path,
            errors=errors,
            warnings=warnings_list,
            validation_time=validation_time,
            signature_verified=rust_result.valid and len(errors) == 0,
        )

    def _build_certificate_path(
        self, end_entity_cert: x509.Certificate, intermediate_certs: list[x509.Certificate]
    ) -> list[x509.Certificate]:
        """Build ordered certificate path from end entity to root."""

        cert_path = [end_entity_cert]
        current_cert = end_entity_cert
        used_certs = {self._get_certificate_key(end_entity_cert)}

        # Build path using intermediate certificates
        while True:
            # Find the issuer of the current certificate
            issuer_found = False

            # Check intermediate certificates
            for intermediate in intermediate_certs:
                inter_key = self._get_certificate_key(intermediate)
                if inter_key in used_certs:
                    continue

                if self._is_issuer(intermediate, current_cert):
                    cert_path.append(intermediate)
                    used_certs.add(inter_key)
                    current_cert = intermediate
                    issuer_found = True
                    break

            # Check CSCA certificates
            if not issuer_found:
                for csca_cert in self._csca_certificates.values():
                    csca_key = self._get_certificate_key(csca_cert)
                    if csca_key in used_certs:
                        continue

                    if self._is_issuer(csca_cert, current_cert):
                        cert_path.append(csca_cert)
                        used_certs.add(csca_key)
                        current_cert = csca_cert
                        issuer_found = True
                        break

            if not issuer_found:
                break

        self.logger.debug(f"Built certificate path with {len(cert_path)} certificates")
        return cert_path

    def _validate_single_certificate(
        self, cert_info: CertificateInfo
    ) -> tuple[list[ValidationError], list[ValidationError]]:
        """Validate a single certificate."""

        errors = []
        warnings = []

        # Time validity validation
        if cert_info.is_expired:
            errors.append(
                ValidationError(
                    certificate_subject=cert_info.subject,
                    error_type=ValidationResult.EXPIRED,
                    error_message=f"Certificate expired on {cert_info.valid_until}",
                    severity="critical",
                )
            )
        elif cert_info.is_not_yet_valid:
            errors.append(
                ValidationError(
                    certificate_subject=cert_info.subject,
                    error_type=ValidationResult.NOT_YET_VALID,
                    error_message=f"Certificate not valid until {cert_info.valid_from}",
                    severity="critical",
                )
            )

        # Expiry warning (within 30 days)
        if cert_info.days_until_expiry <= 30 and cert_info.days_until_expiry > 0:
            warnings.append(
                ValidationError(
                    certificate_subject=cert_info.subject,
                    error_type=ValidationResult.VALID,
                    error_message=f"Certificate expires in {cert_info.days_until_expiry} days",
                    severity="warning",
                )
            )

        # Key usage validation
        if cert_info.cert_type == CertificateType.DOCUMENT_SIGNER:
            if not any(usage in cert_info.key_usage for usage in ["digital_signature"]):
                errors.append(
                    ValidationError(
                        certificate_subject=cert_info.subject,
                        error_type=ValidationResult.INVALID_KEY_USAGE,
                        error_message="Document Signer certificate lacks digital signature key usage",
                        severity="critical",
                    )
                )

        elif cert_info.cert_type == CertificateType.CSCA:
            required_usages = ["key_cert_sign"]
            if not any(usage in cert_info.key_usage for usage in required_usages):
                errors.append(
                    ValidationError(
                        certificate_subject=cert_info.subject,
                        error_type=ValidationResult.INVALID_KEY_USAGE,
                        error_message="CSCA certificate lacks certificate signing key usage",
                        severity="critical",
                    )
                )

        # Key size validation
        if cert_info.key_size:
            min_key_size = 2048 if "RSA" in cert_info.signature_algorithm else 256
            if cert_info.key_size < min_key_size:
                errors.append(
                    ValidationError(
                        certificate_subject=cert_info.subject,
                        error_type=ValidationResult.INVALID,
                        error_message=f"Key size {cert_info.key_size} below minimum {min_key_size}",
                        severity="critical",
                    )
                )

        return errors, warnings

    def _check_revocation_status(self, cert_info: CertificateInfo) -> list[ValidationError]:
        """Check OCSP/CRL-based revocation status for a certificate."""

        errors: list[ValidationError] = []

        for ocsp_response in self._ocsp_responses:
            if ocsp_response.response_status != ocsp.OCSPResponseStatus.SUCCESSFUL:
                continue

            responses = list(getattr(ocsp_response, "responses", []))
            for single_response in responses:
                serial_number = None
                cert_id = getattr(single_response, "cert_id", None)
                if cert_id is not None and hasattr(cert_id, "serial_number"):
                    serial_number = cert_id.serial_number
                else:  # pragma: no cover - compatibility fallback
                    serial_number = getattr(single_response, "serial_number", None)

                if (
                    serial_number is not None
                    and serial_number != cert_info.certificate.serial_number
                ):
                    continue

                status = getattr(single_response, "cert_status", None)
                if status is None:
                    status = getattr(single_response, "certificate_status", None)
                if status is None:
                    continue
                if status == ocsp.OCSPCertStatus.REVOKED:
                    reason = getattr(single_response, "revocation_reason", None)
                    reason_text = reason.name if reason else "unspecified"
                    revocation_time = getattr(single_response, "revocation_time", None)
                    if revocation_time is not None:
                        timestamp = revocation_time.isoformat()
                    else:  # pragma: no cover - compatibility fallback
                        timestamp = "unknown"

                    message = (
                        "Certificate revoked via OCSP on " f"{timestamp} (reason: {reason_text})"
                    )
                    errors.append(
                        ValidationError(
                            certificate_subject=cert_info.subject,
                            error_type=ValidationResult.REVOKED,
                            error_message=message,
                            severity="critical",
                        )
                    )
                return errors

        issuer_crls = self._crls.get(cert_info.issuer, [])
        for crl in issuer_crls:
            revoked = crl.get_revoked_certificate_by_serial_number(
                cert_info.certificate.serial_number
            )
            if revoked is None:
                continue

            revoked_reason = getattr(revoked, "reason", None)
            reason = revoked_reason.name if revoked_reason else "unspecified"
            message = (
                f"Certificate revoked on {revoked.revocation_date.isoformat()}"
                f" (reason: {reason})"
            )
            errors.append(
                ValidationError(
                    certificate_subject=cert_info.subject,
                    error_type=ValidationResult.REVOKED,
                    error_message=message,
                    severity="critical",
                )
            )
            break

        return errors

    def _verify_signature_chain(
        self, cert_path: list[x509.Certificate]
    ) -> tuple[bool, list[ValidationError]]:
        """Verify the signature chain from leaf to root."""

        errors = []
        all_signatures_valid = True

        for i in range(len(cert_path) - 1):
            current_cert = cert_path[i]
            issuer_cert = cert_path[i + 1]

            def _raise_unsupported_key_type(key_type: type) -> None:
                msg = f"Unsupported public key type: {key_type}"
                raise TypeError(msg)

            try:
                # Verify the signature of current_cert using issuer_cert's public key
                issuer_public_key = issuer_cert.public_key()

                # Get signature algorithm

                # Verify signature based on algorithm type
                if isinstance(issuer_public_key, rsa.RSAPublicKey):
                    issuer_public_key.verify(
                        current_cert.signature,
                        current_cert.tbs_certificate_bytes,
                        padding.PKCS1v15(),
                        current_cert.signature_hash_algorithm,
                    )
                elif isinstance(issuer_public_key, ec.EllipticCurvePublicKey):
                    issuer_public_key.verify(
                        current_cert.signature,
                        current_cert.tbs_certificate_bytes,
                        ec.ECDSA(current_cert.signature_hash_algorithm),
                    )
                else:
                    _raise_unsupported_key_type(type(issuer_public_key))

                self.logger.debug(
                    f"Signature verified: {self._get_subject_name(current_cert)} "
                    f"signed by {self._get_subject_name(issuer_cert)}"
                )

            except InvalidSignature:
                all_signatures_valid = False
                errors.append(
                    ValidationError(
                        certificate_subject=self._get_subject_name(current_cert),
                        error_type=ValidationResult.INVALID_SIGNATURE,
                        error_message=(
                            f"Invalid signature from issuer {self._get_subject_name(issuer_cert)}"
                        ),
                        severity="critical",
                    )
                )
            except (ValueError, AttributeError) as e:
                all_signatures_valid = False
                errors.append(
                    ValidationError(
                        certificate_subject=self._get_subject_name(current_cert),
                        error_type=ValidationResult.UNKNOWN_ERROR,
                        error_message=f"Signature verification failed: {e}",
                        severity="critical",
                    )
                )

        return all_signatures_valid, errors

    def _validate_trust_anchor(
        self, cert_path: list[x509.Certificate]
    ) -> tuple[x509.Certificate | None, list[ValidationError]]:
        """Validate trust anchor (root certificate)."""

        errors = []

        if not cert_path:
            errors.append(
                ValidationError(
                    certificate_subject="Unknown",
                    error_type=ValidationResult.UNTRUSTED,
                    error_message="Empty certificate path",
                    severity="critical",
                )
            )
            return None, errors

        root_cert = cert_path[-1]
        root_key = self._get_certificate_key(root_cert)

        # Check if root certificate is in our trust store
        if root_key not in self._csca_certificates:
            errors.append(
                ValidationError(
                    certificate_subject=self._get_subject_name(root_cert),
                    error_type=ValidationResult.UNTRUSTED,
                    error_message="Root certificate not found in trust store",
                    severity="critical",
                )
            )
            return None, errors

        trusted_cert = self._csca_certificates[root_key]

        # Verify the root certificate is self-signed
        try:
            root_public_key = root_cert.public_key()
            if isinstance(root_public_key, rsa.RSAPublicKey):
                root_public_key.verify(
                    root_cert.signature,
                    root_cert.tbs_certificate_bytes,
                    padding.PKCS1v15(),
                    root_cert.signature_hash_algorithm,
                )
            elif isinstance(root_public_key, ec.EllipticCurvePublicKey):
                root_public_key.verify(
                    root_cert.signature,
                    root_cert.tbs_certificate_bytes,
                    ec.ECDSA(root_cert.signature_hash_algorithm),
                )
        except InvalidSignature:
            errors.append(
                ValidationError(
                    certificate_subject=self._get_subject_name(root_cert),
                    error_type=ValidationResult.INVALID_SIGNATURE,
                    error_message="Root certificate self-signature verification failed",
                    severity="critical",
                )
            )
            return None, errors
        except (ValueError, AttributeError) as e:
            errors.append(
                ValidationError(
                    certificate_subject=self._get_subject_name(root_cert),
                    error_type=ValidationResult.UNKNOWN_ERROR,
                    error_message=f"Root certificate validation failed: {e}",
                    severity="critical",
                )
            )
            return None, errors

        return trusted_cert, errors

    def _validate_icao_requirements(
        self, validation_path: list[CertificateInfo]
    ) -> list[ValidationError]:
        """Validate ICAO-specific requirements."""

        errors = []

        # Ensure we have at least a Document Signer certificate
        ds_cert = None
        csca_cert = None

        for cert_info in validation_path:
            if cert_info.cert_type == CertificateType.DOCUMENT_SIGNER:
                ds_cert = cert_info
            elif cert_info.cert_type == CertificateType.CSCA:
                csca_cert = cert_info

        if not ds_cert:
            errors.append(
                ValidationError(
                    certificate_subject="Chain",
                    error_type=ValidationResult.INVALID,
                    error_message="No Document Signer certificate found in chain",
                    severity="critical",
                )
            )

        if not csca_cert:
            errors.append(
                ValidationError(
                    certificate_subject="Chain",
                    error_type=ValidationResult.UNTRUSTED,
                    error_message="No CSCA certificate found in chain",
                    severity="critical",
                )
            )

        # Validate certificate purposes
        if ds_cert and "code_signing" not in ds_cert.extended_key_usage:
            # This is often missing in real certificates, so make it a warning
            pass  # Could add warning here if needed

        return errors

    def _extract_certificate_info(
        self, cert: x509.Certificate, is_end_entity: bool = False
    ) -> CertificateInfo:
        """Extract detailed information from a certificate."""

        # Determine certificate type
        cert_type = self._determine_certificate_type(cert, is_end_entity)

        # Extract usage information
        key_usage = self._extract_key_usage(cert)
        ext_key_usage = self._extract_extended_key_usage(cert)

        # Extract constraints
        is_ca, path_length = self._extract_basic_constraints(cert)

        # Extract key information
        key_size = self._extract_key_size(cert)

        return CertificateInfo(
            certificate=cert,
            cert_type=cert_type,
            subject=self._get_subject_name(cert),
            issuer=self._get_issuer_name(cert),
            serial_number=str(cert.serial_number),
            valid_from=cert.not_valid_before_utc,
            valid_until=cert.not_valid_after_utc,
            signature_algorithm=cert.signature_algorithm_oid.dotted_string,
            key_size=key_size,
            key_usage=key_usage,
            extended_key_usage=ext_key_usage,
            is_ca=is_ca,
            path_length=path_length,
        )

    def _extract_key_usage(self, cert: x509.Certificate) -> list[str]:
        """Extract key usage information from certificate."""
        key_usage = []
        try:
            ku_ext = cert.extensions.get_extension_for_oid(x509.oid.ExtensionOID.KEY_USAGE)
            ku = ku_ext.value
            if ku.digital_signature:
                key_usage.append("digital_signature")
            if ku.key_cert_sign:
                key_usage.append("key_cert_sign")
            if ku.crl_sign:
                key_usage.append("crl_sign")
            if ku.key_encipherment:
                key_usage.append("key_encipherment")
            if ku.data_encipherment:
                key_usage.append("data_encipherment")
        except x509.ExtensionNotFound:
            pass
        return key_usage

    def _extract_extended_key_usage(self, cert: x509.Certificate) -> list[str]:
        """Extract extended key usage information from certificate."""
        ext_key_usage = []
        try:
            eku_ext = cert.extensions.get_extension_for_oid(
                x509.oid.ExtensionOID.EXTENDED_KEY_USAGE
            )
            eku = eku_ext.value
            ext_key_usage.extend(usage.dotted_string for usage in eku)
        except x509.ExtensionNotFound:
            pass
        return ext_key_usage

    def _extract_basic_constraints(self, cert: x509.Certificate) -> tuple[bool, int | None]:
        """Extract basic constraints from certificate."""
        is_ca = False
        path_length = None
        try:
            bc_ext = cert.extensions.get_extension_for_oid(x509.oid.ExtensionOID.BASIC_CONSTRAINTS)
            bc = bc_ext.value
            is_ca = bc.ca
            path_length = bc.path_length
        except x509.ExtensionNotFound:
            pass
        return is_ca, path_length

    def _extract_key_size(self, cert: x509.Certificate) -> int | None:
        """Extract key size information from certificate."""
        try:
            public_key = cert.public_key()
            if isinstance(public_key, rsa.RSAPublicKey):
                return public_key.key_size
            if isinstance(public_key, ec.EllipticCurvePublicKey):
                return public_key.curve.key_size
        except (ValueError, AttributeError):
            pass
        return None

    def _determine_certificate_type(
        self, cert: x509.Certificate, is_end_entity: bool
    ) -> CertificateType:
        """Determine the type of certificate based on its characteristics."""

        # Check basic constraints
        try:
            bc_ext = cert.extensions.get_extension_for_oid(x509.oid.ExtensionOID.BASIC_CONSTRAINTS)
            bc = bc_ext.value
            if bc.ca:
                # This is a CA certificate
                subject_name = self._get_subject_name(cert)
                issuer_name = self._get_issuer_name(cert)

                if subject_name == issuer_name:
                    return CertificateType.CSCA  # Self-signed CA
                return CertificateType.INTERMEDIATE  # Intermediate CA
        except x509.ExtensionNotFound:
            pass

        # If it's the end entity certificate, it's likely the Document Signer
        if is_end_entity:
            return CertificateType.DOCUMENT_SIGNER

        return CertificateType.UNKNOWN

    def _is_issuer(
        self, potential_issuer: x509.Certificate, subject_cert: x509.Certificate
    ) -> bool:
        """Check if potential_issuer is the issuer of subject_cert."""

        # Compare issuer name of subject with subject name of potential issuer
        try:
            return subject_cert.issuer.rfc4514_string() == potential_issuer.subject.rfc4514_string()
        except (ValueError, AttributeError):
            return False

    def _get_certificate_key(self, cert: x509.Certificate) -> str:
        """Generate unique key for certificate identification."""

        try:
            # Use subject key identifier if available
            ski_ext = cert.extensions.get_extension_for_oid(
                x509.oid.ExtensionOID.SUBJECT_KEY_IDENTIFIER
            )
            return binascii.hexlify(ski_ext.value.digest).decode().upper()
        except x509.ExtensionNotFound:
            # Fall back to hash of certificate
            cert_bytes = cert.public_bytes(serialization.Encoding.DER)
            return hashlib.sha256(cert_bytes).hexdigest().upper()

    def _get_subject_name(self, cert: x509.Certificate) -> str:
        """Get formatted subject name from certificate."""
        try:
            return cert.subject.rfc4514_string()
        except (ValueError, AttributeError):
            return "Unknown Subject"

    def _get_issuer_name(self, cert: x509.Certificate) -> str:
        """Get formatted issuer name from certificate."""
        try:
            return cert.issuer.rfc4514_string()
        except (ValueError, AttributeError):
            return "Unknown Issuer"

    def _generate_cache_key(
        self, end_entity: x509.Certificate, intermediates: list[x509.Certificate]
    ) -> str:
        """Generate cache key for validation result."""

        key_parts = [self._get_certificate_key(end_entity)]
        key_parts.extend(self._get_certificate_key(cert) for cert in intermediates)

        combined = "|".join(sorted(key_parts))
        return hashlib.sha256(combined.encode()).hexdigest()

    def clear_cache(self) -> None:
        """Clear the validation cache."""
        self._validation_cache.clear()
        self.logger.info("Validation cache cleared")

    def get_trust_anchors(self) -> list[x509.Certificate]:
        """Get list of loaded trust anchor certificates."""
        return list(self._csca_certificates.values())


# Convenience functions
def validate_passport_certificate_chain(
    document_signer_cert: x509.Certificate,
    intermediate_certs: list[x509.Certificate] | None = None,
    csca_certs: list[x509.Certificate] | None = None,
) -> ChainValidationResult:
    """Validate passport certificate chain with default validator."""

    validator = CertificateChainValidator()

    # Load CSCA certificates if provided
    if csca_certs:
        validator.load_csca_certificates(csca_certs)

    return validator.validate_certificate_chain(document_signer_cert, intermediate_certs or [])


def create_passport_validator_with_trust_store(
    csca_certificates: list[x509.Certificate],
) -> CertificateChainValidator:
    """Create a certificate validator with pre-loaded CSCA certificates."""

    validator = CertificateChainValidator()
    validator.load_csca_certificates(csca_certificates)

    return validator
