#!/usr/bin/env python3
"""
Comprehensive Synthetic Data Generator for Integration Testing

This script consolidates all synthetic data generation functionality:
- Passport documents (ePassports)
- Certificate hierarchies (CSCA, DS certificates)
- Trust anchors and PKD data
- mDL/mDoc credentials
- DTC documents
- Revocation lists (CRLs)
- Offline master-list fixture files

Replaces and consolidates:
- scripts/testing/generate_test_data.py
- scripts/testing/generate_realistic_test_data.py
- src/trust_svc/dev_job.py (data generation parts)

The generated data is designed for integration testing and includes both
valid and invalid data to test error handling.
"""

import argparse
import asyncio
import base64
import json
import logging
import random
import secrets
import string
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Cryptography imports for ASN.1 DER encoding
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

# Add project root to path
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

# Try to import PKD service components for ASN.1 encoding
try:
    from src.pkd_service.app.models.pkd_models import Certificate, CertificateStatus
    from src.pkd_service.app.utils.asn1_utils import ASN1Encoder

    PKD_SERVICE_AVAILABLE = True
except ImportError:
    PKD_SERVICE_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("PKD service not available - will use simplified .ml format")

# Try to import existing test generators for compatibility
try:
    from tests.generators.passport_generator import PassportGenerator

    PASSPORT_GENERATOR_AVAILABLE = True
except ImportError:
    PASSPORT_GENERATOR_AVAILABLE = False

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

DATABASE_INSERT_UNSUPPORTED = (
    "Synthetic database insertion is unsupported. Generate offline fixtures without "
    "--database-insert; a Rust-owned trust import must validate certificates, "
    "signatures and tenant/trust boundaries before writing data."
)

# Common constants
COUNTRIES = [
    "USA",
    "CAN",
    "GBR",
    "FRA",
    "DEU",
    "AUS",
    "JPN",
    "ITA",
    "ESP",
    "NLD",
    "SWE",
    "NOR",
    "DNK",
    "FIN",
    "CHE",
    "AUT",
    "BEL",
    "PRT",
    "IRL",
    "NZL",
]

SURNAMES = [
    "SMITH",
    "JOHNSON",
    "WILLIAMS",
    "BROWN",
    "JONES",
    "GARCIA",
    "MILLER",
    "DAVIS",
    "RODRIGUEZ",
    "MARTINEZ",
    "HERNANDEZ",
    "LOPEZ",
    "GONZALEZ",
    "WILSON",
    "ANDERSON",
    "THOMAS",
    "TAYLOR",
    "MOORE",
    "JACKSON",
    "MARTIN",
]

GIVEN_NAMES = [
    "JOHN",
    "JAMES",
    "ROBERT",
    "MICHAEL",
    "WILLIAM",
    "DAVID",
    "RICHARD",
    "CHARLES",
    "JOSEPH",
    "THOMAS",
    "MARY",
    "PATRICIA",
    "JENNIFER",
    "LINDA",
    "ELIZABETH",
    "BARBARA",
    "SUSAN",
    "JESSICA",
    "SARAH",
    "KAREN",
]


class SyntheticDataGenerator:
    """Generate offline synthetic fixtures, not trusted database records."""

    def __init__(self, output_dir: Path, database_insert: bool = False):
        if database_insert:
            raise ValueError(DATABASE_INSERT_UNSUPPORTED)
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(__name__)

        # Track generated data for consistency
        self.generated_certificates = {}
        self.generated_countries = set()
        self.generated_document_numbers = set()



    def random_string(self, length: int = 10) -> str:
        """Generate random alphanumeric string."""
        return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))

    def random_hex(self, length: int = 32) -> str:
        """Generate random hex string."""
        return secrets.token_hex(length // 2)

    def random_base64(self, length: int = 256) -> str:
        """Generate random base64 encoded data."""
        random_bytes = secrets.token_bytes(length)
        return base64.b64encode(random_bytes).decode("ascii")

    def generate_pem_certificate(self, subject: str, issuer: str) -> str:
        """Generate a synthetic PEM certificate."""
        # This is a placeholder - in a real implementation you'd use cryptography
        cert_data = f"SYNTHETIC_CERT_{self.random_hex(64)}"
        encoded_data = base64.b64encode(cert_data.encode()).decode("ascii")

        # Format as PEM
        pem_lines = []
        pem_lines.append("-----BEGIN CERTIFICATE-----")

        # Split base64 into 64-character lines
        for i in range(0, len(encoded_data), 64):
            pem_lines.append(encoded_data[i : i + 64])

        pem_lines.append("-----END CERTIFICATE-----")
        return "\n".join(pem_lines)

    def generate_passport_data(
        self, country: str = None, document_type: str = "P", validity_years: int = 10
    ) -> dict[str, Any]:
        """Generate realistic passport data."""
        if country is None:
            country = random.choice(COUNTRIES)

        # Ensure unique document number
        while True:
            document_number = f"{document_type}{self.random_string(8)}"
            if document_number not in self.generated_document_numbers:
                self.generated_document_numbers.add(document_number)
                break

        surname = random.choice(SURNAMES)
        given_names = random.choice(GIVEN_NAMES)

        # Generate realistic dates
        birth_years_ago = random.randint(18, 80)
        birth_date = datetime.now(timezone.utc) - timedelta(days=birth_years_ago * 365)
        issue_date = datetime.now(timezone.utc) - timedelta(days=random.randint(0, 365))
        expiry_date = issue_date + timedelta(days=validity_years * 365)

        return {
            "header": {
                "documentCode": document_type,
                "issuingCountry": country,
                "documentNumber": document_number,
                "checkDigit": str(random.randint(0, 9)),
                "issuingDate": issue_date.strftime("%Y%m%d"),
                "expiryDate": expiry_date.strftime("%Y%m%d"),
            },
            "dataGroup1": {
                "surname": surname,
                "givenNames": given_names,
                "documentNumber": document_number,
                "nationality": country,
                "dateOfBirth": birth_date.strftime("%Y%m%d"),
                "sex": random.choice(["M", "F"]),
                "dateOfExpiry": expiry_date.strftime("%Y%m%d"),
                "personalNumber": self.random_string(12),
            },
            "dataGroup2": {"photo": self.random_base64(2048)},  # Simulated photo data
            "security": {
                "documentSecurityObject": self.random_base64(512),
                "signatureValid": random.choice([True, True, True, False]),  # 75% valid
                "integrityCheck": "PASSED" if random.random() > 0.1 else "FAILED",
            },
            "metadata": {
                "generatedAt": datetime.now(timezone.utc).isoformat(),
                "generator": "Marty Synthetic Data Generator",
                "version": "1.0.0",
            },
        }

    def generate_csca_certificate(self, country: str) -> dict[str, Any]:
        """Generate CSCA (Country Signing Certificate Authority) certificate."""
        cert_id = f"CSCA_{country}_{self.random_string(8)}"
        subject = f"CN={country} CSCA,O={country} Government,C={country}"
        issuer = subject  # Self-signed root certificate

        valid_from = datetime.now(timezone.utc) - timedelta(days=random.randint(0, 365))
        valid_to = valid_from + timedelta(days=random.randint(3650, 7300))  # 10-20 years

        certificate_pem = self.generate_pem_certificate(subject, issuer)
        thumbprint = self.random_hex(40)  # SHA-1 thumbprint

        cert_data = {
            "id": cert_id,
            "country": country,
            "subject": subject,
            "issuer": issuer,
            "serialNumber": self.random_hex(16),
            "validFrom": valid_from.isoformat(),
            "validTo": valid_to.isoformat(),
            "certificatePem": certificate_pem,
            "thumbprint": thumbprint,
            "keyUsage": ["keyCertSign", "cRLSign"],
            "isCA": True,
            "isSelfSigned": True,
            "status": "ACTIVE",
            "metadata": {
                "generatedAt": datetime.now(timezone.utc).isoformat(),
                "purpose": "Country Signing Certificate Authority",
            },
        }

        self.generated_certificates[cert_id] = cert_data
        return cert_data

    def generate_ds_certificate(self, country: str, csca_id: str) -> dict[str, Any]:
        """Generate Document Signer certificate."""
        cert_id = f"DS_{country}_{self.random_string(8)}"
        subject = f"CN={country} Document Signer,O={country} Government,C={country}"

        # Get CSCA certificate for issuer
        csca_cert = self.generated_certificates.get(csca_id)
        issuer = (
            csca_cert["subject"]
            if csca_cert
            else f"CN={country} CSCA,O={country} Government,C={country}"
        )

        valid_from = datetime.now(timezone.utc) - timedelta(days=random.randint(0, 180))
        valid_to = valid_from + timedelta(days=random.randint(1095, 1825))  # 3-5 years

        certificate_pem = self.generate_pem_certificate(subject, issuer)
        thumbprint = self.random_hex(40)

        # Some certificates are revoked
        is_revoked = random.random() < 0.1  # 10% revoked
        revocation_date = None
        if is_revoked:
            revocation_date = valid_from + timedelta(days=random.randint(30, 365))

        cert_data = {
            "id": cert_id,
            "country": country,
            "subject": subject,
            "issuer": issuer,
            "issuerCertificateId": csca_id,
            "serialNumber": self.random_hex(16),
            "validFrom": valid_from.isoformat(),
            "validTo": valid_to.isoformat(),
            "certificatePem": certificate_pem,
            "thumbprint": thumbprint,
            "keyUsage": ["digitalSignature", "nonRepudiation"],
            "isCA": False,
            "status": "REVOKED" if is_revoked else "ACTIVE",
            "revocationDate": revocation_date.isoformat() if revocation_date else None,
            "metadata": {
                "generatedAt": datetime.now(timezone.utc).isoformat(),
                "purpose": "Document Signer Certificate",
            },
        }

        self.generated_certificates[cert_id] = cert_data
        return cert_data

    def generate_crl(
        self, country: str, issuer_cert_id: str, revoked_certs: list[str]
    ) -> dict[str, Any]:
        """Generate Certificate Revocation List."""
        issuer_cert = self.generated_certificates.get(issuer_cert_id)
        issuer = issuer_cert["subject"] if issuer_cert else f"CN={country} CSCA"

        crl_number = random.randint(1000, 9999)
        this_update = datetime.now(timezone.utc)
        next_update = this_update + timedelta(days=7)  # Weekly updates

        # Create revoked certificate entries
        revoked_entries = []
        for cert_id in revoked_certs:
            cert = self.generated_certificates.get(cert_id)
            if cert and cert.get("status") == "REVOKED":
                revoked_entries.append(
                    {
                        "serialNumber": cert["serialNumber"],
                        "revocationDate": cert["revocationDate"],
                        "reason": random.choice(
                            [
                                "keyCompromise",
                                "certificateHold",
                                "superseded",
                                "cessationOfOperation",
                            ]
                        ),
                    }
                )

        return {
            "issuer": issuer,
            "issuerCertificateId": issuer_cert_id,
            "crlNumber": crl_number,
            "thisUpdate": this_update.isoformat(),
            "nextUpdate": next_update.isoformat(),
            "revokedCertificates": revoked_entries,
            "signature": self.random_base64(128),
            "signatureAlgorithm": "sha256WithRSAEncryption",
            "metadata": {
                "generatedAt": datetime.now(timezone.utc).isoformat(),
                "totalRevoked": len(revoked_entries),
            },
        }

    def generate_master_list(self, country: str, certificates: list[str]) -> dict[str, Any]:
        """Generate Master List for a country."""
        sequence_number = random.randint(1, 999)
        issue_date = datetime.now(timezone.utc)
        next_update = issue_date + timedelta(days=30)

        # Include certificate references
        cert_refs = []
        for cert_id in certificates:
            cert = self.generated_certificates.get(cert_id)
            if cert:
                cert_refs.append(
                    {
                        "certificateId": cert_id,
                        "thumbprint": cert["thumbprint"],
                        "subject": cert["subject"],
                        "validFrom": cert["validFrom"],
                        "validTo": cert["validTo"],
                    }
                )

        return {
            "country": country,
            "sequenceNumber": sequence_number,
            "version": "1.0.0",
            "issueDate": issue_date.isoformat(),
            "nextUpdate": next_update.isoformat(),
            "certificates": cert_refs,
            "signer": f"{country} CSCA",
            "signature": self.random_base64(256),
            "dataHash": self.random_hex(64),
            "metadata": {
                "generatedAt": datetime.now(timezone.utc).isoformat(),
                "certificateCount": len(cert_refs),
            },
        }

    async def generate_master_lists_only(self, countries: list[str]) -> dict[str, Any]:
        """Generate only master lists for testing trust service without database insertion."""
        logger.info("🔑 Generating master lists only for trust service testing...")

        master_lists = []

        for country in countries:
            logger.info(f"Generating master list for {country}")

            # Generate some mock certificates for the master list
            # We'll create certificate references without full certificate data
            mock_cert_refs = []
            num_certs = random.randint(3, 8)  # 3-8 certificates per country

            for i in range(num_certs):
                cert_id = f"{country}_CSCA_{i+1}"
                issue_date = datetime.now(timezone.utc) - timedelta(days=random.randint(30, 365))
                valid_to = issue_date + timedelta(days=random.randint(365, 1095))  # 1-3 years

                mock_cert_refs.append(
                    {
                        "certificateId": cert_id,
                        "thumbprint": self.random_hex(40),  # SHA-1 thumbprint
                        "subject": f"CN={country} CSCA {i+1}, O={country} Government, C={country}",
                        "validFrom": issue_date.isoformat(),
                        "validTo": valid_to.isoformat(),
                    }
                )

            # Generate master list
            sequence_number = random.randint(1, 999)
            issue_date = datetime.now(timezone.utc)
            next_update = issue_date + timedelta(days=30)

            master_list = {
                "country": country,
                "sequenceNumber": sequence_number,
                "version": "1.0.0",
                "issueDate": issue_date.isoformat(),
                "nextUpdate": next_update.isoformat(),
                "certificates": mock_cert_refs,
                "signer": f"{country} CSCA",
                "signature": self.random_base64(256),
                "dataHash": self.random_hex(64),
                "metadata": {
                    "generatedAt": datetime.now(timezone.utc).isoformat(),
                    "certificateCount": len(mock_cert_refs),
                    "testingOnly": True,
                    "note": "Generated for trust service testing - no database insertion",
                },
            }

            master_lists.append(master_list)

        return {
            "masterLists": master_lists,
            "metadata": {
                "generatedAt": datetime.now(timezone.utc).isoformat(),
                "totalCountries": len(countries),
                "totalMasterLists": len(master_lists),
                "purpose": "Trust service testing without database insertion",
            },
        }

    def _convert_to_certificate_objects(self, master_list: dict) -> list:
        """Convert master list certificate references to Certificate objects for ASN.1 encoding."""
        if not PKD_SERVICE_AVAILABLE:
            return []

        certificates = []
        for cert_ref in master_list.get("certificates", []):
            # Create Certificate object with mock data
            cert = Certificate(
                id=cert_ref["certificateId"],
                subject=cert_ref["subject"],
                issuer=f"{master_list['country']} CSCA Root",
                valid_from=datetime.fromisoformat(cert_ref["validFrom"].replace("Z", "+00:00")),
                valid_to=datetime.fromisoformat(cert_ref["validTo"].replace("Z", "+00:00")),
                serial_number=cert_ref["thumbprint"][:16],  # Use part of thumbprint as serial
                certificate_data=None,  # Will be generated by ASN1Encoder
                status=CertificateStatus.ACTIVE,
                country_code=master_list["country"],
            )
            certificates.append(cert)

        return certificates

    def _generate_asn1_ml_format(self, master_list: dict) -> bytes:
        """Generate ASN.1 DER encoded master list compatible with ICAO standards."""
        try:
            # Generate a temporary self-signed certificate for the master list issuer
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
            )

            # Create issuer name
            issuer_name = x509.Name(
                [
                    x509.NameAttribute(NameOID.COUNTRY_NAME, master_list["country"]),
                    x509.NameAttribute(NameOID.ORGANIZATION_NAME, "ICAO PKD"),
                    x509.NameAttribute(
                        NameOID.COMMON_NAME, f"Master List Signer {master_list['country']}"
                    ),
                ]
            )

            # Parse dates
            issue_date = datetime.fromisoformat(master_list["issueDate"].replace("Z", "+00:00"))
            next_update = datetime.fromisoformat(master_list["nextUpdate"].replace("Z", "+00:00"))

            # Create certificate list as DER-encoded certificates
            certificates = []
            for cert_info in master_list["certificates"]:
                try:
                    # Generate a mock certificate for each entry
                    cert_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

                    # Parse the subject string and create proper X.509 name
                    subject_str = cert_info["subject"]

                    # Simple parsing of DN string (CN=..., O=..., C=...)
                    subject_parts = []
                    for part in subject_str.split(","):
                        part = part.strip()
                        if part.startswith("CN="):
                            subject_parts.append(
                                x509.NameAttribute(NameOID.COMMON_NAME, part[3:].strip())
                            )
                        elif part.startswith("O="):
                            subject_parts.append(
                                x509.NameAttribute(NameOID.ORGANIZATION_NAME, part[2:].strip())
                            )
                        elif part.startswith("C="):
                            subject_parts.append(
                                x509.NameAttribute(NameOID.COUNTRY_NAME, part[2:].strip())
                            )

                    cert_subject = x509.Name(subject_parts)

                    # Use a simple issuer for all certificates (the country CSCA)
                    issuer_name = x509.Name(
                        [
                            x509.NameAttribute(NameOID.COUNTRY_NAME, master_list["country"]),
                            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Government"),
                            x509.NameAttribute(
                                NameOID.COMMON_NAME, f"{master_list['country']} CSCA"
                            ),
                        ]
                    )

                    valid_from = datetime.fromisoformat(
                        cert_info["validFrom"].replace("Z", "+00:00")
                    )
                    valid_to = datetime.fromisoformat(cert_info["validTo"].replace("Z", "+00:00"))

                    certificate = (
                        x509.CertificateBuilder()
                        .subject_name(cert_subject)
                        .issuer_name(issuer_name)
                        .public_key(cert_key.public_key())
                        .serial_number(
                            # Safely handle certificate ID - ensure it exists and convert appropriately
                            int(
                                cert_info.get("certificateId", f"0x{random.randint(1, 2**31):08x}"),
                                16,
                            )
                            if cert_info.get("certificateId", "").startswith("0x")
                            else hash(
                                cert_info.get("certificateId", f"cert_{random.randint(1, 999999)}")
                            )
                            % (2**31)
                        )
                        .not_valid_before(valid_from)
                        .not_valid_after(valid_to)
                        .sign(private_key, hashes.SHA256())
                    )

                    certificates.append(certificate.public_bytes(serialization.Encoding.DER))

                except Exception as cert_error:
                    logger.warning(
                        f"Failed to generate certificate for {cert_info.get('certificateId', 'unknown')}: {cert_error}"
                    )
                    # Continue with other certificates even if one fails
                    continue

            # Create a simple ASN.1 structure for the master list
            # This is a simplified PKCS#7 SignedData structure

            # For now, create a simple SEQUENCE containing the certificates
            # This approximates the ICAO master list format

            # Create a basic DER sequence containing all certificates
            total_length = sum(len(cert) for cert in certificates)

            # ASN.1 SEQUENCE tag (0x30) + length + certificates
            if total_length < 128:
                length_bytes = bytes([total_length])
            elif total_length < 256:
                length_bytes = bytes([0x81, total_length])
            elif total_length < 65536:
                length_bytes = bytes([0x82, total_length >> 8, total_length & 0xFF])
            else:
                length_bytes = bytes(
                    [0x83, total_length >> 16, (total_length >> 8) & 0xFF, total_length & 0xFF]
                )

            asn1_data = b"\x30" + length_bytes + b"".join(certificates)

            return asn1_data

        except Exception as e:
            self.logger.warning(f"Failed to generate ASN.1 master list: {e}")
            # Fallback to basic ASN.1 structure if certificate generation fails
            certificates_data = b""
            for cert_info in master_list["certificates"]:
                # Create a minimal DER certificate placeholder
                cert_placeholder = f"Certificate: {cert_info['subject']}".encode()
                cert_len = len(cert_placeholder)
                if cert_len < 128:
                    cert_der = b"\x04" + bytes([cert_len]) + cert_placeholder
                else:
                    cert_der = b"\x04\x81" + bytes([cert_len]) + cert_placeholder
                certificates_data += cert_der

            # Wrap in ASN.1 SEQUENCE
            total_len = len(certificates_data)
            if total_len < 128:
                length_bytes = bytes([total_len])
            elif total_len < 256:
                length_bytes = bytes([0x81, total_len])
            else:
                length_bytes = bytes([0x82, total_len >> 8, total_len & 0xFF])

            return b"\x30" + length_bytes + certificates_data

    def generate_mdl_credential(self) -> dict[str, Any]:
        """Generate mobile Driving License (mDL) credential."""
        issue_date = datetime.now(timezone.utc) - timedelta(days=random.randint(0, 365))
        expiry_date = issue_date + timedelta(days=random.randint(1095, 2555))  # 3-7 years
        birth_date = datetime.now(timezone.utc) - timedelta(
            days=random.randint(6570, 25550)
        )  # 18-70 years

        return {
            "docType": "org.iso.18013.5.1.mDL",
            "issuer": "State Department of Motor Vehicles",
            "issuingCountry": random.choice(COUNTRIES),
            "issuingAuthority": "DMV",
            "documentNumber": f"DL{self.random_string(8)}",
            "issuanceDate": issue_date.strftime("%Y-%m-%d"),
            "expiryDate": expiry_date.strftime("%Y-%m-%d"),
            "drivingPrivileges": [
                {
                    "vehicleCategory": "A",
                    "issueDate": issue_date.strftime("%Y-%m-%d"),
                    "expiryDate": expiry_date.strftime("%Y-%m-%d"),
                },
                {
                    "vehicleCategory": "B",
                    "issueDate": issue_date.strftime("%Y-%m-%d"),
                    "expiryDate": expiry_date.strftime("%Y-%m-%d"),
                },
            ],
            "personalData": {
                "familyName": random.choice(SURNAMES),
                "givenName": random.choice(GIVEN_NAMES),
                "birthDate": birth_date.strftime("%Y-%m-%d"),
                "sex": random.choice(["M", "F"]),
                "height": random.randint(150, 200),  # cm
                "weight": random.randint(50, 120),  # kg
                "eyeColor": random.choice(["blue", "brown", "green", "hazel"]),
                "hairColor": random.choice(["black", "brown", "blonde", "red", "gray"]),
            },
            "portrait": self.random_base64(1024),
            "signature": self.random_base64(64),
            "metadata": {"generatedAt": datetime.now(timezone.utc).isoformat(), "version": "1.0.0"},
        }

    def generate_mdoc_credential(self) -> dict[str, Any]:
        """Generate mobile document (mDoc) credential."""
        doc_types = [
            "org.iso.18013.5.1.pid",  # Personal ID
            "org.iso.18013.5.1.eid",  # Electronic ID
            "org.example.university.degree",  # University degree
            "org.example.health.insurance",  # Health insurance
        ]

        doc_type = random.choice(doc_types)
        issue_date = datetime.now(timezone.utc) - timedelta(days=random.randint(0, 365))

        base_data = {
            "docType": doc_type,
            "issuer": f"Issuing Authority {self.random_string(4)}",
            "issuingCountry": random.choice(COUNTRIES),
            "documentNumber": f"DOC{self.random_string(10)}",
            "issuanceDate": issue_date.isoformat(),
            "personalData": {
                "familyName": random.choice(SURNAMES),
                "givenName": random.choice(GIVEN_NAMES),
                "birthDate": (
                    datetime.now(timezone.utc) - timedelta(days=random.randint(6570, 25550))
                ).strftime("%Y-%m-%d"),
            },
            "signature": self.random_base64(128),
            "metadata": {"generatedAt": datetime.now(timezone.utc).isoformat(), "version": "1.0.0"},
        }

        # Add doc-type specific data
        if "degree" in doc_type:
            base_data["academicData"] = {
                "institution": "University of Example",
                "degree": random.choice(["Bachelor", "Master", "PhD"]),
                "field": random.choice(["Computer Science", "Engineering", "Medicine", "Law"]),
                "graduationDate": issue_date.strftime("%Y-%m-%d"),
            }
        elif "insurance" in doc_type:
            base_data["insuranceData"] = {
                "policyNumber": f"INS{self.random_string(8)}",
                "provider": "Example Insurance Co.",
                "coverage": random.choice(["Basic", "Premium", "Comprehensive"]),
            }

        return base_data

    def generate_dtc_document(self) -> dict[str, Any]:
        """Generate Digital Travel Credential (DTC) document."""
        issue_date = datetime.now(timezone.utc) - timedelta(days=random.randint(0, 180))
        expiry_date = issue_date + timedelta(days=random.randint(365, 1095))

        return {
            "docType": "org.icao.dtc.1",
            "issuingCountry": random.choice(COUNTRIES),
            "issuingAuthority": "Immigration Authority",
            "documentNumber": f"DTC{self.random_string(9)}",
            "documentType": random.choice(["VISA", "PERMIT", "AUTHORIZATION"]),
            "issuanceDate": issue_date.isoformat(),
            "expiryDate": expiry_date.isoformat(),
            "holder": {
                "familyName": random.choice(SURNAMES),
                "givenName": random.choice(GIVEN_NAMES),
                "nationality": random.choice(COUNTRIES),
                "passportNumber": f"P{self.random_string(8)}",
            },
            "travelAuthorization": {
                "purpose": random.choice(["TOURISM", "BUSINESS", "STUDY", "WORK"]),
                "duration": random.randint(30, 365),
                "entriesAllowed": random.choice([1, 2, "MULTIPLE"]),
                "territories": [random.choice(COUNTRIES)],
            },
            "portrait": self.random_base64(1024),
            "signature": self.random_base64(128),
            "metadata": {"generatedAt": datetime.now(timezone.utc).isoformat(), "version": "1.0.0"},
        }

    async def generate_all_data(
        self,
        countries: list[str] = None,
        passport_count: int = 100,
        mdl_count: int = 50,
        mdoc_count: int = 50,
        dtc_count: int = 30,
    ) -> dict[str, Any]:
        """Generate comprehensive test data set."""
        if countries is None:
            countries = random.sample(COUNTRIES, 10)

        logger.info(f"Generating synthetic data for {len(countries)} countries")

        generated_data = {
            "passports": [],
            "certificates": {"csca": [], "ds": [], "crls": [], "masterLists": []},
            "credentials": {"mdl": [], "mdoc": [], "dtc": []},
            "metadata": {
                "generatedAt": datetime.now(timezone.utc).isoformat(),
                "generator": "Marty Synthetic Data Generator",
                "version": "1.0.0",
                "countries": countries,
                "counts": {
                    "passports": passport_count,
                    "mdl": mdl_count,
                    "mdoc": mdoc_count,
                    "dtc": dtc_count,
                },
            },
        }

        # Generate certificate hierarchy for each country
        country_cert_map = {}
        for country in countries:
            logger.info(f"Generating certificates for {country}")

            # Generate CSCA certificate
            csca_cert = self.generate_csca_certificate(country)
            generated_data["certificates"]["csca"].append(csca_cert)

            # Generate DS certificates (2-5 per country)
            ds_count = random.randint(2, 5)
            ds_certs = []
            for _ in range(ds_count):
                ds_cert = self.generate_ds_certificate(country, csca_cert["id"])
                generated_data["certificates"]["ds"].append(ds_cert)
                ds_certs.append(ds_cert["id"])

            country_cert_map[country] = {"csca": csca_cert["id"], "ds": ds_certs}

            # Generate CRL
            revoked_certs = [
                cert_id
                for cert_id in ds_certs
                if self.generated_certificates[cert_id]["status"] == "REVOKED"
            ]
            crl = self.generate_crl(country, csca_cert["id"], revoked_certs)
            generated_data["certificates"]["crls"].append(crl)

            # Generate Master List
            all_certs = [csca_cert["id"]] + ds_certs
            master_list = self.generate_master_list(country, all_certs)
            generated_data["certificates"]["masterLists"].append(master_list)

        # Generate passports
        logger.info(f"Generating {passport_count} passports")
        for i in range(passport_count):
            country = random.choice(countries)
            # Mix of regular and special passports
            doc_type = "P" if i % 10 != 0 else random.choice(["PM", "IS"])
            passport = self.generate_passport_data(country, doc_type)
            generated_data["passports"].append(passport)

        # Generate mDL credentials
        logger.info(f"Generating {mdl_count} mDL credentials")
        for _ in range(mdl_count):
            mdl = self.generate_mdl_credential()
            generated_data["credentials"]["mdl"].append(mdl)

        # Generate mDoc credentials
        logger.info(f"Generating {mdoc_count} mDoc credentials")
        for _ in range(mdoc_count):
            mdoc = self.generate_mdoc_credential()
            generated_data["credentials"]["mdoc"].append(mdoc)

        # Generate DTC documents
        logger.info(f"Generating {dtc_count} DTC documents")
        for _ in range(dtc_count):
            dtc = self.generate_dtc_document()
            generated_data["credentials"]["dtc"].append(dtc)

        return generated_data

    async def save_data(self, data: dict[str, Any], format_type: str = "json") -> None:
        """Save generated data to files."""
        if format_type == "json":
            # Save comprehensive data file
            output_file = self.output_dir / "synthetic_test_data.json"
            with open(output_file, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved comprehensive data to {output_file}")

            # Handle different data structures
            if "masterLists" in data and "passports" not in data:
                # Master list only mode
                master_lists = data["masterLists"]
                if master_lists:
                    # Save JSON format
                    category_file = self.output_dir / "master_lists.json"
                    with open(category_file, "w") as f:
                        json.dump(master_lists, f, indent=2, ensure_ascii=False)
                    logger.info(f"Saved {len(master_lists)} master lists to {category_file}")

                    # Save .ml format files
                    for master_list in master_lists:
                        country = master_list["country"]

                        try:
                            if PKD_SERVICE_AVAILABLE:
                                # Use proper ASN.1 encoding if available
                                certificates = self._convert_to_certificate_objects(master_list)
                                if certificates:
                                    ml_data = ASN1Encoder.encode_master_list(certificates)
                                else:
                                    # Fallback to simplified format
                                    ml_data = self._generate_asn1_ml_format(master_list)
                            else:
                                # Use ASN.1 DER format
                                ml_data = self._generate_asn1_ml_format(master_list)

                            # Save .ml file
                            ml_file = self.output_dir / f"master_list_{country.lower()}.ml"
                            with open(ml_file, "wb") as f:
                                f.write(ml_data)
                            logger.info(
                                f"Saved {country} master list to {ml_file} ({len(ml_data)} bytes)"
                            )
                        except Exception as e:
                            logger.warning(f"Failed to generate .ml file for {country}: {e}")
            else:
                # Full data mode - save individual category files
                categories = [
                    ("passports", data.get("passports", [])),
                    ("csca_certificates", data.get("certificates", {}).get("csca", [])),
                    ("ds_certificates", data.get("certificates", {}).get("ds", [])),
                    ("crls", data.get("certificates", {}).get("crls", [])),
                    ("master_lists", data.get("certificates", {}).get("masterLists", [])),
                    ("mdl_credentials", data.get("credentials", {}).get("mdl", [])),
                    ("mdoc_credentials", data.get("credentials", {}).get("mdoc", [])),
                    ("dtc_documents", data.get("credentials", {}).get("dtc", [])),
                ]

                for category, items in categories:
                    if items:
                        category_file = self.output_dir / f"{category}.json"
                        with open(category_file, "w") as f:
                            json.dump(items, f, indent=2, ensure_ascii=False)
                        logger.info(f"Saved {len(items)} {category} to {category_file}")

        # Generate summary report
        if "masterLists" in data and "passports" not in data:
            # Master list only mode
            summary = {
                "summary": {
                    "totalItems": len(data["masterLists"]),
                    "breakdown": {"masterLists": len(data["masterLists"])},
                    "countries": data["metadata"]["totalCountries"],
                    "generatedAt": data["metadata"]["generatedAt"],
                    "mode": "master-lists-only",
                }
            }
        else:
            # Full data mode
            summary = {
                "summary": {
                    "totalItems": sum(
                        [
                            len(data.get("passports", [])),
                            len(data.get("certificates", {}).get("csca", [])),
                            len(data.get("certificates", {}).get("ds", [])),
                            len(data.get("credentials", {}).get("mdl", [])),
                            len(data.get("credentials", {}).get("mdoc", [])),
                            len(data.get("credentials", {}).get("dtc", [])),
                        ]
                    ),
                    "breakdown": {
                        "passports": len(data.get("passports", [])),
                        "cscaCertificates": len(data.get("certificates", {}).get("csca", [])),
                        "dsCertificates": len(data.get("certificates", {}).get("ds", [])),
                        "crls": len(data.get("certificates", {}).get("crls", [])),
                        "masterLists": len(data.get("certificates", {}).get("masterLists", [])),
                        "mdlCredentials": len(data.get("credentials", {}).get("mdl", [])),
                        "mdocCredentials": len(data.get("credentials", {}).get("mdoc", [])),
                        "dtcDocuments": len(data.get("credentials", {}).get("dtc", [])),
                    },
                    "countries": data.get("metadata", {}).get("countries", []),
                    "generatedAt": data.get("metadata", {}).get("generatedAt", ""),
                    "mode": "full-data",
                }
            }

        summary_file = self.output_dir / "data_summary.json"
        with open(summary_file, "w") as f:
            json.dump(summary, f, indent=2)
        logger.info(f"Saved summary to {summary_file}")







async def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Comprehensive synthetic test data generator for Marty",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate standard test dataset
  python generate_synthetic_data.py --output-dir data/synthetic

  # Generate a large offline fixture dataset
  python generate_synthetic_data.py --passports 1000 --countries 50

  # Generate minimal dataset for CI/CD
  python generate_synthetic_data.py --passports 20 --countries 5

  # Generate only master lists for trust service testing (no database insertion)
  python generate_synthetic_data.py --master-list-only --countries 10
        """,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("./data/synthetic"),
        help="Output directory for generated data",
    )
    parser.add_argument(
        "--countries", type=int, default=10, help="Number of countries to generate data for"
    )
    parser.add_argument(
        "--passports", type=int, default=100, help="Number of passport documents to generate"
    )
    parser.add_argument("--mdl", type=int, default=50, help="Number of mDL credentials to generate")
    parser.add_argument(
        "--mdoc", type=int, default=50, help="Number of mDoc credentials to generate"
    )
    parser.add_argument("--dtc", type=int, default=30, help="Number of DTC documents to generate")
    parser.add_argument(
        "--database-insert",
        action="store_true",
        help="Unsupported legacy mode; requires a qualified Rust-owned trust import",
    )
    parser.add_argument(
        "--master-list-only",
        action="store_true",
        help="Generate only master lists without database insertion",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducible results")
    parser.add_argument("--format", choices=["json"], default="json", help="Output format")

    args = parser.parse_args()

    # Set random seed for reproducible results
    random.seed(args.seed)

    # Validate mutually exclusive options
    if args.master_list_only and args.database_insert:
        logger.error("❌ --master-list-only and --database-insert are mutually exclusive")
        sys.exit(1)

    if args.database_insert:
        parser.error(DATABASE_INSERT_UNSUPPORTED)

    # Create generator only after rejecting unsupported modes.
    generator = SyntheticDataGenerator(args.output_dir)

    # Select countries
    selected_countries = random.sample(COUNTRIES, min(args.countries, len(COUNTRIES)))

    try:
        if args.master_list_only:
            # Generate only master lists for trust service testing
            logger.info("🔑 Master list only mode - generating for trust service testing")
            data = await generator.generate_master_lists_only(selected_countries)
        else:
            # Generate all data
            data = await generator.generate_all_data(
                countries=selected_countries,
                passport_count=args.passports,
                mdl_count=args.mdl,
                mdoc_count=args.mdoc,
                dtc_count=args.dtc,
            )

        # Save data to files
        await generator.save_data(data, args.format)

        logger.info("✅ Synthetic data generation completed successfully!")

        # Print summary
        print("\n" + "=" * 60)
        if args.master_list_only:
            print("MASTER LISTS GENERATION SUMMARY")
            print("=" * 60)
            print(f"Output Directory: {args.output_dir}")
            print(f"Countries: {len(selected_countries)}")
            print(f"Master Lists: {len(data.get('masterLists', []))}")
            print("Mode: Trust service testing (no database insertion)")
        else:
            print("SYNTHETIC DATA GENERATION SUMMARY")
            print("=" * 60)
            print(f"Output Directory: {args.output_dir}")
            print(f"Countries: {len(selected_countries)}")
            print(f"Passports: {len(data['passports'])}")
            print(f"CSCA Certificates: {len(data['certificates']['csca'])}")
            print(f"DS Certificates: {len(data['certificates']['ds'])}")
            print(f"CRLs: {len(data['certificates']['crls'])}")
            print(f"Master Lists: {len(data['certificates']['masterLists'])}")
            print(f"mDL Credentials: {len(data['credentials']['mdl'])}")
            print(f"mDoc Credentials: {len(data['credentials']['mdoc'])}")
            print(f"DTC Documents: {len(data['credentials']['dtc'])}")

        print("=" * 60)

    except Exception:
        logger.exception("❌ Error generating synthetic data")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
