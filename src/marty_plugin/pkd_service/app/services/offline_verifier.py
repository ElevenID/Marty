"""
Service for offline verification of certificates against a local trust store
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings
from app.db.database import DatabaseManager
from app.models.pkd_models import CertificateStatus, VerificationResult

logger = logging.getLogger(__name__)


class OfflineVerifier:
    """
    Service for offline verification of certificates against local trust store.

    This service provides functionality to:
    - Validate certificates without internet connectivity
    - Check certificate chains against local master lists
    - Verify revocation status using cached CRLs
    """

    def __init__(self) -> None:
        """Initialize the offline verifier"""
        self.trust_store_path = settings.LOCAL_TRUST_STORE_PATH
        self.crl_path = settings.LOCAL_CRL_PATH

    async def verify_certificate(self, certificate_data: bytes) -> VerificationResult:
        """
        Verify a certificate against the local trust store

        Args:
            certificate_data: The raw certificate data to verify

        Returns:
            VerificationResult object with verification status and details
        """
        try:
            # Parse the certificate
            cert = self._parse_certificate(certificate_data)

            if not cert:
                return VerificationResult(
                    is_valid=False,
                    status="INVALID_FORMAT",
                    details="Could not parse certificate data",
                )

            # Check if certificate has expired
            now = datetime.now(tz=timezone.utc)
            if cert["valid_to"] < now or cert["valid_from"] > now:
                return VerificationResult(
                    is_valid=False,
                    status="EXPIRED" if cert["valid_to"] < now else "NOT_YET_VALID",
                    details=f"Certificate is {'expired' if cert['valid_to'] < now else 'not yet valid'}",
                )

            # Check if certificate is in trust store
            is_trusted = await self._is_certificate_trusted(cert)
            if not is_trusted:
                return VerificationResult(
                    is_valid=False,
                    status="UNTRUSTED",
                    details="Certificate is not in the local trust store",
                )

            # Check if certificate is revoked
            is_revoked = await self._is_certificate_revoked(cert)
            if is_revoked:
                return VerificationResult(
                    is_valid=False, status="REVOKED", details="Certificate has been revoked"
                )

            # Certificate is valid
            return VerificationResult(
                is_valid=True, status="VALID", details="Certificate is valid and trusted"
            )

        except Exception as e:
            logger.exception(f"Error verifying certificate: {e}")
            return VerificationResult(
                is_valid=False, status="ERROR", details=f"Error during verification: {e!s}"
            )

    def _parse_certificate(self, certificate_data: bytes) -> dict | None:
        """
        Parse certificate data into a dictionary of certificate properties

        Args:
            certificate_data: The raw certificate data

        Returns:
            Dictionary of certificate properties or None if parsing failed
        """
        try:
            # In a real implementation, this would use cryptographic libraries
            # like cryptography/pyOpenSSL to parse X.509 certificates
            # For this implementation, we'll use a simplified approach

            # Basic check to see if this looks like a certificate
            if b"CERTIFICATE" not in certificate_data and not certificate_data.startswith(b"0\x82"):
                logger.warning("Data does not appear to be a certificate")
                return None

            # For a proper implementation, we would do something like:
            # from cryptography import x509
            # from cryptography.hazmat.backends import default_backend
            # cert = x509.load_der_x509_certificate(certificate_data, default_backend())
            # or
            # cert = x509.load_pem_x509_certificate(certificate_data, default_backend())

            # This is a placeholder implementation
            # In a real implementation, we would extract these values from the certificate
            return {
                "subject": "CN=Example",
                "issuer": "CN=Example CA",
                "serial_number": "12345678",
                "valid_from": datetime(2020, 1, 1),
                "valid_to": datetime(2030, 1, 1),
                "fingerprint": "01:23:45:67:89:AB:CD:EF",
                "raw_data": certificate_data,
            }

        except Exception as e:
            logger.exception(f"Error parsing certificate: {e}")
            return None

    async def _is_certificate_trusted(self, cert: dict) -> bool:
        """
        Check if a certificate is in the local trust store

        Args:
            cert: The certificate to check

        Returns:
            True if the certificate is trusted, False otherwise
        """
        try:
            # Get all trusted certificates from the database
            trusted_certs = await DatabaseManager.get_certificates(
                cert_type="CSCA", status=CertificateStatus.ACTIVE
            )

            # In a real implementation, we would check if the certificate is in the trust store
            # by comparing fingerprints or other unique identifiers
            for trusted_cert in trusted_certs:
                if trusted_cert.get("serial_number") == cert["serial_number"]:
                    return True

            # If not found in database, check local filesystem trust store
            return self._check_filesystem_trust_store(cert)

        except Exception as e:
            logger.exception(f"Error checking if certificate is trusted: {e}")
            return False

    def _check_filesystem_trust_store(self, cert: dict) -> bool:
        """
        Check if a certificate is in the filesystem-based trust store

        Args:
            cert: The certificate to check

        Returns:
            True if the certificate is in the trust store, False otherwise
        """
        try:
            if not self.trust_store_path or not os.path.exists(self.trust_store_path):
                logger.warning(f"Trust store path {self.trust_store_path} does not exist")
                return False

            # In a real implementation, we would iterate through certificate files
            # in the trust store directory and compare with the provided certificate

            # For this implementation, we'll just check if any file exists in the directory
            trust_store_dir = Path(self.trust_store_path)
            if not any(trust_store_dir.glob("*.cer")) and not any(trust_store_dir.glob("*.pem")):
                logger.warning("No certificates found in trust store directory")
                return False

            # For demo purposes, we'll assume the certificate is not in the trust store
            # In a real implementation, we would load each certificate and compare

        except Exception as e:
            logger.exception(f"Error checking filesystem trust store: {e}")
            return False
        else:
            return False

    async def _is_certificate_revoked(self, cert: dict) -> bool:
        """
        Check if a certificate is revoked using local CRLs

        Args:
            cert: The certificate to check

        Returns:
            True if the certificate is revoked, False otherwise
        """
        try:
            if not self.crl_path or not os.path.exists(self.crl_path):
                logger.warning(f"CRL path {self.crl_path} does not exist")
                return False

            # In a real implementation, we would:
            # 1. Load CRLs from the local cache directory
            # 2. Check if the certificate's serial number is in any of the CRLs

            # For this implementation, we'll assume the certificate is not revoked

        except Exception as e:
            logger.exception(f"Error checking if certificate is revoked: {e}")
            return False
        else:
            return False

    async def build_trust_store(self) -> int:
        """
        Build or update local trust store from the database

        Returns:
            Number of certificates exported to the trust store
        """
        try:
            # Create trust store directory if it doesn't exist
            os.makedirs(self.trust_store_path, exist_ok=True)

            # Get all active CSCA certificates
            trusted_certs = await DatabaseManager.get_certificates(
                cert_type="CSCA", status=CertificateStatus.ACTIVE
            )

            count = 0
            for cert_dict in trusted_certs:
                try:
                    cert_id = cert_dict.get("id")
                    cert_data = cert_dict.get("certificate_data")
                    country = cert_dict.get("country_code", "XX")

                    if not cert_data:
                        logger.warning(f"No certificate data for {cert_id}")
                        continue

                    # Write certificate to trust store
                    cert_path = os.path.join(self.trust_store_path, f"{country}_{cert_id}.cer")
                    with open(cert_path, "wb") as f:
                        f.write(cert_data)

                    count += 1

                except Exception as e:
                    logger.exception(f"Error exporting certificate {cert_dict.get('id')}: {e}")

            logger.info(f"Exported {count} certificates to local trust store")

        except Exception as e:
            logger.exception(f"Error building trust store: {e}")
            return 0
        else:
            return count

    async def update_local_crls(self) -> int:
        """
        Update local CRL cache from the database

        Returns:
            Number of CRLs exported to the local cache
        """
        try:
            # Create CRL directory if it doesn't exist
            os.makedirs(self.crl_path, exist_ok=True)

            # In a real implementation, we would:
            # 1. Get all CRLs from the database
            # 2. Export them to the CRL cache directory

            # For this implementation, we'll just return 0
            logger.info("CRL update not implemented in this version")

        except Exception as e:
            logger.exception(f"Error updating local CRLs: {e}")
            return 0
        else:
            return 0
