"""
CSCA Trust Anchor Management System
===================================

This module provides comprehensive management of Country Signing Certificate Authority (CSCA)
trust anchors for passport verification according to ICAO Doc 9303 standards.

Features:
- CSCA certificate loading and validation
- Trust store management with persistence
- Country-specific certificate organization
- Certificate metadata extraction and indexing
- Automatic certificate discovery from PKD
- Trust anchor validation and verification
- Certificate expiry monitoring and alerts

Author: Marty Development Team
Date: September 2025
"""

from __future__ import annotations

import binascii
import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import NameOID
# Import crypto_bridge Certificate for type compatibility
from marty_common.crypto_bridge import Certificate as CertificateBridge

logger = logging.getLogger(__name__)


class CSCAStatus(Enum):
    """CSCA certificate status types."""

    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    SUSPENDED = "suspended"
    PENDING = "pending"
    UNKNOWN = "unknown"


class TrustLevel(Enum):
    """Trust levels for CSCA certificates."""

    FULL_TRUST = "full_trust"  # Directly trusted CSCA
    CONDITIONAL_TRUST = "conditional"  # Trusted with conditions
    UNTRUSTED = "untrusted"  # Not trusted
    BLACKLISTED = "blacklisted"  # Explicitly blocked


@dataclass
class CountryInfo:
    """Information about a country and its passport issuance."""

    country_code: str  # ISO 3166-1 alpha-3 code
    country_name: str
    region: str  # Geographic region
    passport_type: str  # MRP, MRV, etc.
    issuing_authority: str
    security_features: list[str]
    supported_data_groups: list[int]
    eac_supported: bool
    bac_supported: bool

    @property
    def alpha_2_code(self) -> str | None:
        """Get ISO 3166-1 alpha-2 code if possible."""
        # Simple mapping for common countries
        mapping = {
            "USA": "US",
            "GBR": "GB",
            "DEU": "DE",
            "FRA": "FR",
            "ITA": "IT",
            "ESP": "ES",
            "CAN": "CA",
            "AUS": "AU",
            "NLD": "NL",
            "BEL": "BE",
            "CHE": "CH",
            "AUT": "AT",
            "SWE": "SE",
            "NOR": "NO",
            "DNK": "DK",
            "FIN": "FI",
        }
        return mapping.get(self.country_code)


@dataclass
class CertificateProcessingResult:
    """Result of processing a single certificate file."""

    success: bool
    cert_id: str | None = None
    error: Exception | None = None


@dataclass
class CSCACertificateMetadata:
    """Comprehensive metadata for CSCA certificates."""

    # Certificate identification
    subject_key_identifier: str
    fingerprint_sha256: str
    serial_number: str

    # Certificate details
    subject_name: str
    issuer_name: str
    country_code: str
    country_name: str

    # Validity information
    valid_from: datetime
    valid_until: datetime
    is_expired: bool
    days_until_expiry: int

    # Cryptographic information
    signature_algorithm: str
    public_key_algorithm: str
    key_size: int | None

    # Trust and status
    trust_level: TrustLevel
    status: CSCAStatus

    # Operational metadata
    last_verified: datetime | None
    source: str  # Where the certificate was obtained
    added_date: datetime

    # PKD information
    pkd_country_list: list[str]  # Countries that recognize this CSCA

    @property
    def is_self_signed(self) -> bool:
        """Check if the certificate is self-signed."""
        return self.subject_name == self.issuer_name

    @property
    def needs_renewal_warning(self) -> bool:
        """Check if certificate needs renewal warning (within 90 days)."""
        return 0 < self.days_until_expiry <= 90

    @property
    def is_valid(self) -> bool:
        """Check if certificate is currently valid."""
        now = datetime.now(timezone.utc)
        return (
            self.valid_from <= now <= self.valid_until
            and self.status == CSCAStatus.ACTIVE
            and self.trust_level != TrustLevel.BLACKLISTED
        )


class CSCATrustStore:
    """
    Comprehensive CSCA trust store manager.

    Manages a collection of CSCA certificates with trust levels, metadata,
    and persistence capabilities. Supports country-specific organization
    and automatic certificate discovery.
    """

    def __init__(self, trust_store_path: Path | None = None) -> None:
        """
        Initialize CSCA trust store.

        Args:
            trust_store_path: Path to persistent trust store directory
        """
        self.trust_store_path = trust_store_path or Path("data/csca")
        self.trust_store_path.mkdir(parents=True, exist_ok=True)

        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # Certificate storage
        self._certificates: dict[str, x509.Certificate] = {}
        self._metadata: dict[str, CSCACertificateMetadata] = {}
        self._country_mapping: dict[str, list[str]] = {}  # country_code -> cert_ids
        self._trust_levels: dict[str, TrustLevel] = {}

        # Country information
        self._country_info: dict[str, CountryInfo] = {}

        # Load existing trust store
        self._load_trust_store()

        # Load country information
        self._load_country_info()

    def add_csca_certificate(
        self,
        certificate: x509.Certificate | CertificateBridge,
        country_code: str | None = None,
        trust_level: TrustLevel = TrustLevel.FULL_TRUST,
        source: str = "manual",
    ) -> str:
        """
        Add a CSCA certificate to the trust store.

        Args:
            certificate: The CSCA certificate (x509.Certificate or CertificateBridge)
            country_code: ISO 3166-1 alpha-3 country code
            trust_level: Trust level for the certificate
            source: Source of the certificate

        Returns:
            Certificate identifier
        """
        # Convert CertificateBridge to x509.Certificate if needed
        if isinstance(certificate, CertificateBridge):
            certificate = certificate.to_cryptography()

        # Generate certificate ID
        cert_id = self._generate_certificate_id(certificate)

        # Extract country code from certificate if not provided
        if not country_code:
            country_code = self._extract_country_code(certificate)

        # Create metadata
        metadata = self._create_certificate_metadata(certificate, country_code, trust_level, source)

        # Store certificate and metadata
        self._certificates[cert_id] = certificate
        self._metadata[cert_id] = metadata
        self._trust_levels[cert_id] = trust_level

        # Update country mapping
        if country_code:
            if country_code not in self._country_mapping:
                self._country_mapping[country_code] = []
            if cert_id not in self._country_mapping[country_code]:
                self._country_mapping[country_code].append(cert_id)

        # Persist changes
        self._save_certificate(cert_id, certificate, metadata)
        self._save_trust_store_index()

        self.logger.info(
            f"Added CSCA certificate: {metadata.subject_name} "
            f"(Country: {country_code}, Trust: {trust_level.value})"
        )

        return cert_id

    def load_csca_certificates_from_directory(
        self,
        directory: Path,
        country_code: str | None = None,
        trust_level: TrustLevel = TrustLevel.FULL_TRUST,
        file_pattern: str = "*.pem",
    ) -> list[str]:
        """
        Load CSCA certificates from a directory.

        Args:
            directory: Directory containing certificate files
            country_code: Default country code for certificates
            trust_level: Default trust level
            file_pattern: File pattern to match

        Returns:
            List of certificate IDs
        """

        if not directory.exists():
            msg = f"Directory not found: {directory}"
            raise ValueError(msg)

        cert_ids = []
        cert_files = list(directory.glob(file_pattern))

        self.logger.info(f"Loading CSCA certificates from {directory} ({len(cert_files)} files)")

        # Process certificates with error collection
        errors = []
        for cert_file in cert_files:
            result = self._process_single_certificate(cert_file, country_code, trust_level)
            if result.success:
                cert_ids.append(result.cert_id)
            else:
                errors.append((cert_file, result.error))

        # Log all errors after processing
        for cert_file, error in errors:
            self.logger.exception(f"Failed to load certificate {cert_file}: {error}")

        self.logger.info(f"Successfully loaded {len(cert_ids)} CSCA certificates")
        return cert_ids

    def _process_single_certificate(
        self, cert_file: Path, country_code: str | None, trust_level: TrustLevel
    ) -> CertificateProcessingResult:
        """Process a single certificate file and return result."""
        try:
            # Load certificate
            with cert_file.open("rb") as f:
                cert_data = f.read()

            # Try PEM first, then DER
            try:
                certificate = x509.load_pem_x509_certificate(cert_data)
            except ValueError:
                certificate = x509.load_der_x509_certificate(cert_data)

            # Extract country from filename if not provided
            file_country = country_code
            if not file_country:
                # Try to extract from filename (e.g., USA_CSCA.pem)
                filename = cert_file.stem.upper()
                if len(filename) >= 3:
                    potential_country = filename[:3]
                    if potential_country.isalpha():
                        file_country = potential_country

            # Add to trust store
            cert_id = self.add_csca_certificate(
                certificate, file_country, trust_level, f"file:{cert_file}"
            )
            return CertificateProcessingResult(success=True, cert_id=cert_id)

        except (ValueError, OSError, TypeError, AttributeError, RuntimeError) as e:
            return CertificateProcessingResult(success=False, error=e)

    def get_csca_certificates_for_country(self, country_code: str) -> list[x509.Certificate | CertificateBridge]:
        """Get all CSCA certificates for a specific country."""

        if country_code not in self._country_mapping:
            return []

        certificates = []
        for cert_id in self._country_mapping[country_code]:
            if cert_id in self._certificates:
                metadata = self._metadata[cert_id]
                if metadata.is_valid:  # Only return valid certificates
                    certificates.append(self._certificates[cert_id])

        return certificates

    def get_all_trusted_certificates(self) -> list[x509.Certificate | CertificateBridge]:
        """Get all trusted CSCA certificates."""

        trusted_certs = []
        for cert_id, trust_level in self._trust_levels.items():
            if (
                trust_level in [TrustLevel.FULL_TRUST, TrustLevel.CONDITIONAL_TRUST]
                and cert_id in self._certificates
            ):
                metadata = self._metadata[cert_id]
                if metadata.is_valid:
                    trusted_certs.append(self._certificates[cert_id])

        return trusted_certs

    def verify_csca_certificate(
        self, certificate: x509.Certificate | CertificateBridge, country_code: str | None = None
    ) -> tuple[bool, list[str]]:
        """
        Verify a CSCA certificate against the trust store.

        Args:
            certificate: Certificate to verify (x509.Certificate or CertificateBridge)
            country_code: Expected country code

        Returns:
            (is_trusted, validation_messages)
        """
        # Convert CertificateBridge to x509.Certificate if needed
        if isinstance(certificate, CertificateBridge):
            certificate = certificate.to_cryptography()
        
        cert_id = self._generate_certificate_id(certificate)
        validation_messages = []

        # Perform validation checks
        validation_result = self._perform_certificate_validation_checks(
            cert_id, country_code, validation_messages
        )

        if not validation_result:
            return False, validation_messages

        # Perform signature verification
        signature_valid = self._verify_certificate_signature(certificate, validation_messages)

        if not signature_valid:
            return False, validation_messages

        validation_messages.append("Certificate verification successful")
        return True, validation_messages

    def _perform_certificate_validation_checks(
        self, cert_id: str, country_code: str | None, validation_messages: list[str]
    ) -> bool:
        """Perform basic validation checks on certificate."""
        # Check if certificate is in trust store
        if cert_id not in self._certificates:
            validation_messages.append("Certificate not found in trust store")
            return False

        metadata = self._metadata[cert_id]

        # Check trust level
        if metadata.trust_level == TrustLevel.BLACKLISTED:
            validation_messages.append("Certificate is blacklisted")
            return False

        if metadata.trust_level == TrustLevel.UNTRUSTED:
            validation_messages.append("Certificate is not trusted")
            return False

        # Check validity
        if not metadata.is_valid:
            validation_messages.append(
                f"Certificate is not valid (Status: {metadata.status.value})"
            )
            return False

        # Check country if specified
        if country_code and metadata.country_code != country_code:
            validation_messages.append(
                f"Country mismatch: expected {country_code}, got {metadata.country_code}"
            )
            return False

        return True

    def _verify_certificate_signature(
        self, certificate: x509.Certificate, validation_messages: list[str]
    ) -> bool:
        """Verify the self-signature of the certificate."""
        try:
            public_key = certificate.public_key()
            if isinstance(public_key, rsa.RSAPublicKey):
                public_key.verify(
                    certificate.signature,
                    certificate.tbs_certificate_bytes,
                    rsa.padding.PKCS1v15(),
                    certificate.signature_hash_algorithm,
                )
            elif isinstance(public_key, ec.EllipticCurvePublicKey):
                public_key.verify(
                    certificate.signature,
                    certificate.tbs_certificate_bytes,
                    ec.ECDSA(certificate.signature_hash_algorithm),
                )
            else:
                validation_messages.append(f"Unsupported key type: {type(public_key)}")
                return False

        except (InvalidSignature, ValueError, AttributeError) as e:
            validation_messages.append(f"Self-signature verification failed: {e}")
            return False

        return True

    def update_certificate_trust_level(
        self, cert_id: str, trust_level: TrustLevel, reason: str | None = None
    ) -> bool:
        """Update trust level for a certificate."""

        if cert_id not in self._certificates:
            return False

        old_trust = self._trust_levels.get(cert_id, TrustLevel.UNKNOWN)
        self._trust_levels[cert_id] = trust_level

        # Update metadata
        if cert_id in self._metadata:
            self._metadata[cert_id].trust_level = trust_level

        # Save changes
        self._save_trust_store_index()

        self.logger.info(
            f"Updated trust level for {cert_id}: {old_trust.value} -> {trust_level.value}"
            f"{f' (Reason: {reason})' if reason else ''}"
        )

        return True

    def get_certificate_metadata(self, cert_id: str) -> CSCACertificateMetadata | None:
        """Get metadata for a specific certificate."""
        return self._metadata.get(cert_id)

    def get_certificates_by_trust_level(
        self, trust_level: TrustLevel
    ) -> list[tuple[str, x509.Certificate]]:
        """Get certificates by trust level."""

        results = []
        for cert_id, cert_trust in self._trust_levels.items():
            if cert_trust == trust_level and cert_id in self._certificates:
                results.append((cert_id, self._certificates[cert_id]))

        return results

    def get_expiring_certificates(self, days_ahead: int = 90) -> list[CSCACertificateMetadata]:
        """Get certificates expiring within specified days."""

        expiring = [
            metadata
            for metadata in self._metadata.values()
            if (metadata.is_valid and 0 < metadata.days_until_expiry <= days_ahead)
        ]

        return sorted(expiring, key=lambda m: m.days_until_expiry)

    def get_trust_store_statistics(self) -> dict[str, Any]:
        """Get comprehensive trust store statistics."""

        total_certs = len(self._certificates)

        # Count by trust level
        trust_counts = {}
        for trust_level in TrustLevel:
            trust_counts[trust_level.value] = sum(
                1 for t in self._trust_levels.values() if t == trust_level
            )

        # Count by status
        status_counts = {}
        for status in CSCAStatus:
            status_counts[status.value] = sum(
                1 for m in self._metadata.values() if m.status == status
            )

        # Count by country
        country_counts = {
            country: len(cert_ids) for country, cert_ids in self._country_mapping.items()
        }

        # Expiry statistics
        valid_certs = [m for m in self._metadata.values() if m.is_valid]
        expiring_soon = len(self.get_expiring_certificates(90))
        expiring_critical = len(self.get_expiring_certificates(30))

        return {
            "total_certificates": total_certs,
            "valid_certificates": len(valid_certs),
            "trust_levels": trust_counts,
            "status_distribution": status_counts,
            "countries": len(self._country_mapping),
            "country_distribution": country_counts,
            "expiry_warnings": {
                "expiring_90_days": expiring_soon,
                "expiring_30_days": expiring_critical,
            },
        }

    def _generate_certificate_id(self, certificate: x509.Certificate) -> str:
        """Generate unique identifier for a certificate."""

        try:
            # Use Subject Key Identifier if available
            ski_ext = certificate.extensions.get_extension_for_oid(
                x509.oid.ExtensionOID.SUBJECT_KEY_IDENTIFIER
            )
            return binascii.hexlify(ski_ext.value.digest).decode().upper()
        except x509.ExtensionNotFound:
            # Fall back to SHA-256 of certificate
            cert_bytes = certificate.public_bytes(serialization.Encoding.DER)
            return hashlib.sha256(cert_bytes).hexdigest().upper()

    def _extract_country_code(self, certificate: x509.Certificate) -> str | None:
        """Extract country code from certificate subject."""

        try:
            # Try to get country from subject
            for attribute in certificate.subject:
                if attribute.oid == NameOID.COUNTRY_NAME:
                    country_2_letter = attribute.value
                    # Convert ISO 3166-1 alpha-2 to alpha-3
                    mapping = {
                        "US": "USA",
                        "GB": "GBR",
                        "DE": "DEU",
                        "FR": "FRA",
                        "IT": "ITA",
                        "ES": "ESP",
                        "CA": "CAN",
                        "AU": "AUS",
                        "NL": "NLD",
                        "BE": "BEL",
                        "CH": "CHE",
                        "AT": "AUT",
                        "SE": "SWE",
                        "NO": "NOR",
                        "DK": "DNK",
                        "FI": "FIN",
                    }
                    return mapping.get(country_2_letter, country_2_letter)

            # Try to extract from organization name
            for attribute in certificate.subject:
                if attribute.oid == NameOID.ORGANIZATION_NAME:
                    org_name = attribute.value.upper()
                    # Look for country patterns
                    if "UNITED STATES" in org_name or "USA" in org_name:
                        return "USA"
                    if "UNITED KINGDOM" in org_name or "BRITAIN" in org_name:
                        return "GBR"
                    if "GERMANY" in org_name or "DEUTSCHLAND" in org_name:
                        return "DEU"
                    # Add more patterns as needed

        except (ValueError, AttributeError):
            pass

        return None

    def _create_certificate_metadata(
        self,
        certificate: x509.Certificate,
        country_code: str | None,
        trust_level: TrustLevel,
        source: str,
    ) -> CSCACertificateMetadata:
        """Create comprehensive metadata for a certificate."""

        # Generate identifiers
        cert_id = self._generate_certificate_id(certificate)
        fingerprint = (
            hashlib.sha256(certificate.public_bytes(serialization.Encoding.DER)).hexdigest().upper()
        )

        # Extract certificate details
        subject_name = certificate.subject.rfc4514_string()
        issuer_name = certificate.issuer.rfc4514_string()

        # Get country information
        country_name = "Unknown"
        if country_code and country_code in self._country_info:
            country_name = self._country_info[country_code].country_name

        # Calculate validity information
        now = datetime.now(timezone.utc)
        # Use cryptography library's attributes (converting to tz-aware)
        valid_from = certificate.not_valid_before_utc
        valid_until = certificate.not_valid_after_utc
        is_expired = now > valid_until
        days_until_expiry = max(0, (valid_until - now).days)

        # Extract cryptographic information
        signature_algorithm = certificate.signature_algorithm_oid.dotted_string

        public_key = certificate.public_key()
        public_key_algorithm = type(public_key).__name__
        key_size = None

        if isinstance(public_key, rsa.RSAPublicKey):
            key_size = public_key.key_size
        elif isinstance(public_key, ec.EllipticCurvePublicKey):
            key_size = public_key.curve.key_size

        # Determine status
        status = CSCAStatus.ACTIVE
        if is_expired:
            status = CSCAStatus.EXPIRED
        elif now < valid_from:
            status = CSCAStatus.PENDING

        return CSCACertificateMetadata(
            subject_key_identifier=cert_id,
            fingerprint_sha256=fingerprint,
            serial_number=str(certificate.serial_number),
            subject_name=subject_name,
            issuer_name=issuer_name,
            country_code=country_code or "UNK",
            country_name=country_name,
            valid_from=valid_from,
            valid_until=valid_until,
            is_expired=is_expired,
            days_until_expiry=days_until_expiry,
            signature_algorithm=signature_algorithm,
            public_key_algorithm=public_key_algorithm,
            key_size=key_size,
            trust_level=trust_level,
            status=status,
            last_verified=None,
            source=source,
            added_date=now,
            pkd_country_list=[],
        )

    def _save_certificate(
        self, cert_id: str, certificate: x509.Certificate, metadata: CSCACertificateMetadata
    ) -> None:
        """Save certificate and metadata to disk."""

        # Save certificate in PEM format
        cert_path = self.trust_store_path / f"{cert_id}.pem"
        with cert_path.open("wb") as f:
            f.write(certificate.public_bytes(serialization.Encoding.PEM))

        # Save metadata as JSON
        metadata_path = self.trust_store_path / f"{cert_id}.json"
        with metadata_path.open("w") as f:
            # Convert datetime objects to ISO strings
            metadata_dict = asdict(metadata)
            for key in ["valid_from", "valid_until", "added_date"]:
                if metadata_dict[key]:
                    metadata_dict[key] = metadata_dict[key].isoformat()
            if metadata_dict.get("last_verified"):
                metadata_dict["last_verified"] = metadata_dict["last_verified"].isoformat()

            json.dump(metadata_dict, f, indent=2)

    def _save_trust_store_index(self) -> None:
        """Save trust store index."""

        index_path = self.trust_store_path / "trust_store_index.json"

        index_data = {
            "version": "1.0",
            "updated": datetime.now(timezone.utc).isoformat(),
            "certificates": {
                cert_id: {
                    "trust_level": trust.value,
                    "country_code": (
                        self._metadata[cert_id].country_code if cert_id in self._metadata else None
                    ),
                }
                for cert_id, trust in self._trust_levels.items()
            },
            "country_mapping": self._country_mapping,
            "statistics": self.get_trust_store_statistics(),
        }

        with index_path.open("w") as f:
            json.dump(index_data, f, indent=2)

    def _load_trust_store(self) -> None:
        """Load existing trust store from disk."""

        if not self.trust_store_path.exists():
            return

        # Load certificates
        for cert_file in self.trust_store_path.glob("*.pem"):
            cert_id = cert_file.stem

            try:
                # Load certificate
                with cert_file.open("rb") as f:
                    certificate = x509.load_pem_x509_certificate(f.read())

                self._certificates[cert_id] = certificate

                # Load metadata if available
                metadata_file = self.trust_store_path / f"{cert_id}.json"
                if metadata_file.exists():
                    with metadata_file.open() as f:
                        metadata_dict = json.load(f)

                    # Convert ISO strings back to datetime objects
                    for key in ["valid_from", "valid_until", "added_date"]:
                        if metadata_dict.get(key):
                            metadata_dict[key] = datetime.fromisoformat(metadata_dict[key])
                    if metadata_dict.get("last_verified"):
                        metadata_dict["last_verified"] = datetime.fromisoformat(
                            metadata_dict["last_verified"]
                        )

                    # Convert enums
                    metadata_dict["trust_level"] = TrustLevel(metadata_dict["trust_level"])
                    metadata_dict["status"] = CSCAStatus(metadata_dict["status"])

                    self._metadata[cert_id] = CSCACertificateMetadata(**metadata_dict)
                    self._trust_levels[cert_id] = self._metadata[cert_id].trust_level

            except Exception:
                self.logger.exception(f"Failed to load certificate {cert_file}")

        # Load index if available
        index_path = self.trust_store_path / "trust_store_index.json"
        if index_path.exists():
            try:
                with index_path.open() as f:
                    index_data = json.load(f)

                # Load country mapping
                self._country_mapping = index_data.get("country_mapping", {})

            except Exception:
                self.logger.exception("Failed to load trust store index")

        self.logger.info(f"Loaded {len(self._certificates)} CSCA certificates from trust store")

    def _load_country_info(self) -> None:
        """Load country information database."""

        # Basic country information (in real implementation, this would come from a database)
        countries = [
            CountryInfo(
                "USA",
                "United States",
                "North America",
                "MRP",
                "Department of State",
                ["RFID", "EAC", "BAC"],
                list(range(1, 17)),
                True,
                True,
            ),
            CountryInfo(
                "GBR",
                "United Kingdom",
                "Europe",
                "MRP",
                "HM Passport Office",
                ["RFID", "EAC", "BAC"],
                list(range(1, 17)),
                True,
                True,
            ),
            CountryInfo(
                "DEU",
                "Germany",
                "Europe",
                "MRP",
                "Federal Foreign Office",
                ["RFID", "EAC", "BAC"],
                list(range(1, 17)),
                True,
                True,
            ),
            CountryInfo(
                "FRA",
                "France",
                "Europe",
                "MRP",
                "Ministry of Interior",
                ["RFID", "EAC", "BAC"],
                list(range(1, 17)),
                True,
                True,
            ),
            CountryInfo(
                "CAN",
                "Canada",
                "North America",
                "MRP",
                "Passport Canada",
                ["RFID", "EAC", "BAC"],
                list(range(1, 17)),
                True,
                True,
            ),
            CountryInfo(
                "AUS",
                "Australia",
                "Oceania",
                "MRP",
                "Australian Passport Office",
                ["RFID", "EAC", "BAC"],
                list(range(1, 17)),
                True,
                True,
            ),
        ]

        for country in countries:
            self._country_info[country.country_code] = country

        self.logger.debug(f"Loaded information for {len(self._country_info)} countries")


# Convenience functions
def create_default_csca_trust_store(trust_store_path: Path | None = None) -> CSCATrustStore:
    """Create a default CSCA trust store with common configurations."""

    return CSCATrustStore(trust_store_path)

    # Add any built-in trusted certificates here
    # (In real implementation, you'd load well-known CSCA certificates)


def load_csca_from_pkd_master_list(
    _master_list_path: Path, _trust_store: CSCATrustStore
) -> list[str]:
    """Load CSCA certificates from ICAO PKD Master List."""

    # This would implement parsing of ICAO PKD Master List format
    # For now, return empty list
    logger.info("PKD Master List loading not yet implemented")
    return []
