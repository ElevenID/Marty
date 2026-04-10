"""
Certificate processing utilities to eliminate duplicate cryptography patterns.

This module consolidates common certificate operations using Rust bindings
to reduce code duplication across services that handle certificates.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from marty_plugin.common.crypto_bridge import (
    get_certificate_info as rust_get_certificate_info,
    certificate_pem_to_der,
    is_certificate_expired,
    is_certificate_not_yet_valid,
    get_certificate_public_key,
    verify_certificate_signature,
)

logger = logging.getLogger(__name__)


class CertificateError(Exception):
    """Base exception for certificate processing errors."""

    def __init__(self, message: str, certificate_path: str | None = None) -> None:
        """Initialize certificate error."""
        super().__init__(message)
        self.certificate_path = certificate_path
        self.message = message


class CertificateValidationError(CertificateError):
    """Exception raised when certificate validation fails."""


class CertificateExpirationError(CertificateError):
    """Exception raised when certificate is expired or expires soon."""


class CertificateProcessor:
    """
    Unified certificate processing utilities.

    Consolidates common patterns for certificate loading, parsing,
    validation, and information extraction using Rust bindings.
    """

    @staticmethod
    def load_certificate_from_file(cert_path: str | Path) -> bytes:
        """
        Load certificate from PEM or DER file.

        Args:
            cert_path: Path to certificate file

        Returns:
            DER-encoded certificate bytes

        Raises:
            CertificateError: If certificate cannot be loaded
        """
        cert_path = Path(cert_path)
        if not cert_path.exists():
            error_msg = "Certificate file not found"
            raise CertificateError(error_msg, str(cert_path))

        try:
            with cert_path.open("rb") as f:
                cert_data = f.read()

            return CertificateProcessor.load_certificate_from_bytes(cert_data)

        except OSError as e:
            error_msg = f"Failed to load certificate: {e}"
            raise CertificateError(error_msg, str(cert_path)) from e

    @staticmethod
    def load_certificate_from_bytes(cert_data: bytes) -> bytes:
        """
        Load certificate from bytes (PEM or DER format).

        Args:
            cert_data: Certificate data as bytes

        Returns:
            DER-encoded certificate bytes

        Raises:
            CertificateError: If certificate cannot be loaded
        """
        try:
            # Try PEM format first (check for PEM header)
            if b"-----BEGIN CERTIFICATE-----" in cert_data:
                return certificate_pem_to_der(cert_data.decode("utf-8"))
            # Assume DER format
            return cert_data
        except Exception as e:
            error_msg = f"Failed to parse certificate data: {e}"
            raise CertificateError(error_msg) from e

    @staticmethod
    def get_certificate_info(certificate: bytes) -> dict[str, Any]:
        """
        Extract comprehensive information from certificate.

        Args:
            certificate: DER-encoded certificate bytes

        Returns:
            Dictionary containing certificate information with RFC 5280 naming:
            - subject: X.500 DN string
            - issuer: X.500 DN string  
            - serial_number: hex string
            - not_before: ISO 8601 UTC string
            - not_after: ISO 8601 UTC string
            - is_ca: bool
            - key_usage: list of key usage strings
            - subject_alt_names: list of SAN strings
            - fingerprint_sha256: lowercase hex string
        """
        return rust_get_certificate_info(certificate)

    @staticmethod
    def validate_certificate(
        certificate: bytes,
        check_expiration: bool = True,
        days_warning: int = 30,
    ) -> dict[str, Any]:
        """
        Validate certificate and check expiration.

        Args:
            certificate: DER-encoded certificate bytes
            check_expiration: Whether to check expiration dates
            days_warning: Days before expiration to warn

        Returns:
            Dictionary with validation results

        Raises:
            CertificateValidationError: If validation fails
        """
        now = datetime.now(timezone.utc)
        validation_result: dict[str, Any] = {
            "valid": True,
            "warnings": [],
            "errors": [],
            "expires_in_days": None,
        }

        # Get certificate info for validation details
        cert_info = rust_get_certificate_info(certificate)
        not_before = datetime.fromisoformat(cert_info["not_before"].replace("Z", "+00:00"))
        not_after = datetime.fromisoformat(cert_info["not_after"].replace("Z", "+00:00"))

        # Check if certificate is currently valid using Rust bindings
        if is_certificate_not_yet_valid(certificate):
            validation_result["valid"] = False
            validation_result["errors"].append(
                f"Certificate not yet valid (valid from {cert_info['not_before']})"
            )

        if is_certificate_expired(certificate):
            validation_result["valid"] = False
            validation_result["errors"].append(
                f"Certificate expired on {cert_info['not_after']}"
            )

        if check_expiration and validation_result["valid"]:
            # Calculate days until expiration
            time_until_expiry = not_after - now
            days_until_expiry = time_until_expiry.days
            validation_result["expires_in_days"] = days_until_expiry

            # Check if expiring soon
            if days_until_expiry <= days_warning:
                warning_msg = (
                    f"Certificate expires in {days_until_expiry} days "
                    f"({cert_info['not_after']})"
                )
                validation_result["warnings"].append(warning_msg)

        # Include key usage info if available
        if cert_info.get("key_usage"):
            validation_result["key_usage"] = {
                "digital_signature": "digitalSignature" in cert_info["key_usage"],
                "key_cert_sign": "keyCertSign" in cert_info["key_usage"],
                "crl_sign": "cRLSign" in cert_info["key_usage"],
            }
        else:
            validation_result["warnings"].append("No Key Usage extension found")

        if validation_result["errors"]:
            error_msg = "; ".join(validation_result["errors"])
            raise CertificateValidationError(error_msg)

        return validation_result

    @staticmethod
    def extract_public_key_info(certificate: bytes) -> dict[str, Any]:
        """
        Extract public key information from certificate.

        Args:
            certificate: DER-encoded certificate bytes

        Returns:
            Dictionary containing public key information
        """
        # Get public key in SPKI DER format
        pubkey_der = get_certificate_public_key(certificate)
        cert_info = rust_get_certificate_info(certificate)
        
        return {
            "public_key_der": pubkey_der,
            "fingerprint_sha256": cert_info["fingerprint_sha256"],
        }

    @staticmethod
    def compare_certificates(cert1: bytes, cert2: bytes) -> dict[str, Any]:
        """
        Compare two certificates for equality and differences.

        Args:
            cert1: First certificate (DER-encoded bytes)
            cert2: Second certificate (DER-encoded bytes)

        Returns:
            Dictionary with comparison results
        """
        result: dict[str, Any] = {
            "identical": False,
            "same_subject": False,
            "same_issuer": False,
            "same_public_key": False,
            "differences": [],
        }

        # Check if certificates are identical (byte comparison)
        if cert1 == cert2:
            result["identical"] = True
            return result

        # Get certificate info for comparison
        info1 = rust_get_certificate_info(cert1)
        info2 = rust_get_certificate_info(cert2)

        # Compare subjects
        if info1["subject"] == info2["subject"]:
            result["same_subject"] = True
        else:
            result["differences"].append("Different subjects")

        # Compare issuers
        if info1["issuer"] == info2["issuer"]:
            result["same_issuer"] = True
        else:
            result["differences"].append("Different issuers")

        # Compare public keys
        try:
            key1_bytes = get_certificate_public_key(cert1)
            key2_bytes = get_certificate_public_key(cert2)
            if key1_bytes == key2_bytes:
                result["same_public_key"] = True
            else:
                result["differences"].append("Different public keys")
        except Exception:
            result["differences"].append("Could not compare public keys")

        # Compare validity periods
        if info1["not_before"] != info2["not_before"]:
            result["differences"].append("Different start dates")
        if info1["not_after"] != info2["not_after"]:
            result["differences"].append("Different expiration dates")

        # Compare serial numbers
        if info1["serial_number"] != info2["serial_number"]:
            result["differences"].append("Different serial numbers")

        return result

    @staticmethod
    def get_certificate_chain_info(certificates: list[bytes]) -> dict[str, Any]:
        """
        Analyze a certificate chain.

        Args:
            certificates: List of DER-encoded certificates in chain order

        Returns:
            Dictionary with chain analysis
        """
        if not certificates:
            return {"valid_chain": False, "error": "Empty certificate chain"}

        chain_info: dict[str, Any] = {
            "valid_chain": True,
            "length": len(certificates),
            "certificates": [],
            "warnings": [],
            "errors": [],
        }

        cert_infos = []
        for i, cert in enumerate(certificates):
            cert_info = CertificateProcessor.get_certificate_info(cert)
            cert_info["position"] = i
            cert_info["is_root"] = i == len(certificates) - 1
            cert_info["is_leaf"] = i == 0
            chain_info["certificates"].append(cert_info)
            cert_infos.append(cert_info)

        # Validate chain order using issuer/subject matching
        for i in range(len(certificates) - 1):
            current_info = cert_infos[i]
            next_info = cert_infos[i + 1]

            # Check if current cert was issued by next cert
            if current_info["issuer"] != next_info["subject"]:
                chain_info["valid_chain"] = False
                chain_info["errors"].append(
                    f"Certificate {i} issuer does not match certificate {i+1} subject"
                )

            # Optionally verify signature
            try:
                if not verify_certificate_signature(certificates[i], certificates[i + 1]):
                    chain_info["valid_chain"] = False
                    chain_info["errors"].append(
                        f"Certificate {i} signature verification failed against certificate {i+1}"
                    )
            except Exception as e:
                chain_info["warnings"].append(
                    f"Could not verify signature for certificate {i}: {e}"
                )

        return chain_info


# Convenience functions for common operations
def load_and_validate_certificate(
    cert_path: str | Path,
    check_expiration: bool = True,
    days_warning: int = 30,
) -> tuple[bytes, dict[str, Any]]:
    """
    Load and validate a certificate from file.

    Args:
        cert_path: Path to certificate file
        check_expiration: Whether to check expiration dates
        days_warning: Days before expiration to warn

    Returns:
        Tuple of (DER-encoded certificate bytes, validation_result)

    Raises:
        CertificateError: If certificate cannot be loaded or validated
    """
    certificate = CertificateProcessor.load_certificate_from_file(cert_path)
    validation_result = CertificateProcessor.validate_certificate(
        certificate, check_expiration, days_warning
    )
    return certificate, validation_result


def get_certificate_summary(cert_path: str | Path) -> dict[str, Any]:
    """
    Get a comprehensive summary of certificate information.

    Args:
        cert_path: Path to certificate file

    Returns:
        Dictionary with certificate summary
    """
    certificate = CertificateProcessor.load_certificate_from_file(cert_path)
    cert_info = CertificateProcessor.get_certificate_info(certificate)
    validation_result = CertificateProcessor.validate_certificate(certificate)
    key_info = CertificateProcessor.extract_public_key_info(certificate)

    return {
        "file_path": str(cert_path),
        "certificate_info": cert_info,
        "validation": validation_result,
        "public_key": key_info,
    }


def check_certificate_expiration(cert_path: str | Path, days_warning: int = 30) -> dict[str, Any]:
    """
    Check certificate expiration status.

    Args:
        cert_path: Path to certificate file
        days_warning: Days before expiration to warn

    Returns:
        Dictionary with expiration information
    """
    certificate = CertificateProcessor.load_certificate_from_file(cert_path)
    cert_info = CertificateProcessor.get_certificate_info(certificate)
    validation_result = CertificateProcessor.validate_certificate(
        certificate, check_expiration=True, days_warning=days_warning
    )

    now = datetime.now(timezone.utc)
    not_after = datetime.fromisoformat(cert_info["not_after"].replace("Z", "+00:00"))
    time_until_expiry = not_after - now

    return {
        "file_path": str(cert_path),
        "expires_on": cert_info["not_after"],
        "expires_in_days": time_until_expiry.days,
        "expires_in_hours": int(time_until_expiry.total_seconds() // 3600),
        "is_expired": is_certificate_expired(certificate),
        "warnings": validation_result.get("warnings", []),
        "needs_renewal": time_until_expiry.days <= days_warning,
    }
