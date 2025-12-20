"""
ASN.1 utilities for PKD service
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

import asn1crypto.cms
import asn1crypto.crl
import asn1crypto.pem
import asn1crypto.x509
from app.models.pkd_models import Certificate, CertificateStatus, RevokedCertificate
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.x509.oid import NameOID

logger = logging.getLogger(__name__)


class ASN1Encoder:
    """
    Provides ASN.1 encoding functionality for PKD data structures according to ICAO Doc 9303 standards
    """

    @staticmethod
    def extract_country_code(subject) -> str | None:
        """
        Extract and validate country code from certificate subject.

        Args:
            subject: Certificate subject from asn1crypto

        Returns:
            Valid 2-letter country code or None if not found/invalid
        """
        for rdn in subject.chosen:
            for name in rdn:
                if name["type"].native == "country_name":
                    extracted_code = name["value"].native
                    # Validate country code format (2 letter ISO 3166-1 alpha-2)
                    if (
                        isinstance(extracted_code, str)
                        and len(extracted_code) == 2
                        and extracted_code.isalpha()
                        and extracted_code.isupper()
                    ):
                        return extracted_code
                    logger.warning(f"Invalid country code format: {extracted_code}")
                    break  # Take the first country name found
        return None

    @staticmethod
    def encode_master_list(certificates: list[Certificate]) -> bytes:
        """
        Encode a list of certificates as an ICAO CSCA Master List.

        The Master List is a CMS SignedData structure according to RFC 5652,
        containing a list of CSCA certificates.
        """
        try:
            # Convert certificate data to asn1crypto certificates
            cert_list = []
            for cert in certificates:
                # In a real implementation, we would use the actual certificate data
                # Here we'll create a simple self-signed cert for demo purposes if needed
                if cert.certificate_data:
                    try:
                        # Try to parse existing certificate data
                        asn1crypto.x509.Certificate.load(cert.certificate_data)
                        cert_list.append(cert.certificate_data)
                    except Exception as e:
                        logger.warning(f"Failed to parse certificate: {e}")
                        # Fallback to mock data in case of invalid cert data
                        cert_list.append(ASN1Encoder._create_mock_certificate(cert))
                else:
                    # Create mock certificate for demo
                    cert_list.append(ASN1Encoder._create_mock_certificate(cert))

            # Create CMS SignedData containing the certificates
            signed_data = asn1crypto.cms.SignedData(
                {
                    "version": "v3",
                    "digest_algorithms": [{"algorithm": "sha256"}],
                    "encap_content_info": {
                        "content_type": "data",
                        "content": b"",  # Empty content for Master List
                    },
                    "certificates": cert_list,
                    "signer_infos": [],  # No signers for this example
                }
            )

            # Wrap in ContentInfo
            content_info = asn1crypto.cms.ContentInfo(
                {"content_type": "signed_data", "content": signed_data}
            )

            # Encode to DER
            return content_info.dump()

        except Exception as e:
            logger.exception(f"Failed to encode master list: {e}")
            # Return a minimal placeholder bytes for now
            return b"MOCK_MASTER_LIST_DATA"

    @staticmethod
    def encode_dsc_list(certificates: list[Certificate]) -> bytes:
        """
        Encode a list of certificates as an ICAO DSC List.

        The DSC List is structured similarly to the Master List.
        """
        # For the DSC list, we use the same structure as the Master List
        return ASN1Encoder.encode_master_list(certificates)

    @staticmethod
    def encode_crl(
        issuer: str,
        this_update: datetime,
        next_update: datetime,
        revoked_certs: list[RevokedCertificate],
    ) -> bytes:
        """
        Encode a Certificate Revocation List (CRL) according to RFC 5280.
        """
        try:
            # Parse the revoked certificates
            revoked_list = []

            for revoked_cert in revoked_certs:
                revocation_date = revoked_cert.revocation_date.replace(tzinfo=timezone.utc)

                # Create revoked certificate entry
                revoked = asn1crypto.crl.RevokedCertificate(
                    {
                        "user_certificate": int(revoked_cert.serial_number, 16),
                        "revocation_date": revocation_date,
                        "crl_entry_extensions": [],
                    }
                )

                if revoked_cert.reason_code is not None:
                    # Add reason code if provided
                    reason_extension = asn1crypto.crl.Extension(
                        {
                            "extn_id": "crl_reason",
                            "critical": False,
                            "extn_value": asn1crypto.crl.CRLReason(revoked_cert.reason_code),
                        }
                    )
                    revoked["crl_entry_extensions"].append(reason_extension)

                revoked_list.append(revoked)

            # Create a CRL
            tbs_cert_list = asn1crypto.crl.TbsCertList(
                {
                    "version": "v2",
                    "signature": {"algorithm": "sha256_rsa", "parameters": None},
                    "issuer": asn1crypto.x509.Name.build({"common_name": issuer}),
                    "this_update": this_update.replace(tzinfo=timezone.utc),
                    "next_update": next_update.replace(tzinfo=timezone.utc),
                    "revoked_certificates": revoked_list,
                }
            )

            # In a real implementation, we would sign the TBS CRL with the issuer's key
            # For this example, we'll use a placeholder signature
            signature = b"\x00" * 256  # Placeholder signature

            crl = asn1crypto.crl.CertificateList(
                {
                    "tbs_cert_list": tbs_cert_list,
                    "signature_algorithm": {"algorithm": "sha256_rsa", "parameters": None},
                    "signature": signature,
                }
            )

            # Encode to DER
            return crl.dump()

        except Exception as e:
            logger.exception(f"Failed to encode CRL: {e}")
            # Return a minimal placeholder bytes for now
            return b"MOCK_CRL_DATA"

    @staticmethod
    def _create_mock_certificate(cert_info: Certificate) -> bytes:
        """
        Create a mock certificate for demonstration purposes.
        In a real implementation, you'd use proper certificate generation.
        """
        try:
            # Create a simple self-signed certificate for demo
            builder = x509.CertificateBuilder()

            # Parse subject into X.509 name
            subject_name = x509.Name(
                [
                    x509.NameAttribute(
                        NameOID.COMMON_NAME, cert_info.subject.split(",")[0].split("=")[1]
                    )
                ]
            )

            # Parse issuer into X.509 name
            issuer_name = x509.Name(
                [
                    x509.NameAttribute(
                        NameOID.COMMON_NAME, cert_info.issuer.split(",")[0].split("=")[1]
                    )
                ]
            )

            # Set basic certificate fields
            builder = builder.subject_name(subject_name)
            builder = builder.issuer_name(issuer_name)
            builder = builder.not_valid_before(cert_info.valid_from)
            builder = builder.not_valid_after(cert_info.valid_to)
            builder = builder.serial_number(int(cert_info.serial_number, 16))

            # Add a placeholder public key - in a real implementation, this would be the actual key
            # Just for demo purposes
            from cryptography.hazmat.primitives.asymmetric import rsa

            key = rsa.generate_private_key(
                public_exponent=65537, key_size=2048, backend=default_backend()
            )
            builder = builder.public_key(key.public_key())

            # Add some basic extensions
            builder = builder.add_extension(
                x509.BasicConstraints(ca=True, path_length=None), critical=True
            )

            # Self-sign the certificate with the private key
            certificate = builder.sign(
                private_key=key, algorithm=hashes.SHA256(), backend=default_backend()
            )

            # Convert to DER format
            return certificate.public_bytes(encoding=x509.encoding.DER)

        except Exception as e:
            logger.exception(f"Failed to create mock certificate: {e}")
            # Return minimal mock data
            return b"MOCK_CERTIFICATE_DATA"


class ASN1Decoder:
    """
    Provides ASN.1 decoding functionality for PKD data structures according to ICAO Doc 9303 standards
    """

    @staticmethod
    def decode_master_list(master_list_data: bytes) -> list[Certificate]:
        """
        Decode an ICAO CSCA Master List from ASN.1 DER encoding to a list of certificates.
        """
        try:
            # Check if the data starts with PEM marker
            if master_list_data.startswith(b"-----BEGIN"):
                der_bytes = asn1crypto.pem.unarmor(master_list_data)[2]
            else:
                der_bytes = master_list_data

            # Parse ContentInfo
            content_info = asn1crypto.cms.ContentInfo.load(der_bytes)

            # Extract SignedData
            if content_info["content_type"].native == "signed_data":
                signed_data = content_info["content"]

                # Extract certificates
                certificates = []
                for cert_bytes in signed_data["certificates"]:
                    try:
                        x509_cert = asn1crypto.x509.Certificate.load(cert_bytes.dump())

                        # Extract certificate information
                        subject = x509_cert.subject.human_friendly
                        issuer = x509_cert.issuer.human_friendly
                        serial = format(x509_cert["tbs_certificate"]["serial_number"].native, "X")

                        # Extract validity period
                        valid_from = x509_cert["tbs_certificate"]["validity"]["not_before"].native
                        valid_to = x509_cert["tbs_certificate"]["validity"]["not_after"].native

                        # Extract country from subject with validation
                        country_code = ASN1Encoder.extract_country_code(x509_cert.subject)

                        # Create Certificate object
                        certificate = Certificate(
                            id=uuid4(),
                            subject=subject,
                            issuer=issuer,
                            valid_from=valid_from,
                            valid_to=valid_to,
                            serial_number=serial,
                            certificate_data=cert_bytes.dump(),
                            status=CertificateStatus.ACTIVE,
                            country_code=country_code or "XXX",
                        )
                        certificates.append(certificate)
                    except Exception as e:
                        logger.warning(f"Failed to parse certificate: {e}")

                return certificates
            msg = f"Unexpected content type: {content_info['content_type'].native}"
            raise ValueError(msg)

        except Exception as e:
            logger.exception(f"Failed to decode master list: {e}")
            # Return empty list for now
            return []

    @staticmethod
    def decode_dsc_list(dsc_list_data: bytes) -> list[Certificate]:
        """
        Decode an ICAO DSC List from ASN.1 DER encoding to a list of certificates.
        """
        # DSC list has the same structure as Master List
        return ASN1Decoder.decode_master_list(dsc_list_data)

    @staticmethod
    def decode_crl(crl_data: bytes) -> tuple[str, datetime, datetime, list[RevokedCertificate]]:
        """
        Decode a Certificate Revocation List (CRL) according to RFC 5280.
        """
        try:
            # Check if the data starts with PEM marker
            if crl_data.startswith(b"-----BEGIN"):
                der_bytes = asn1crypto.pem.unarmor(crl_data)[2]
            else:
                der_bytes = crl_data

            # Parse CRL
            crl = asn1crypto.crl.CertificateList.load(der_bytes)
            tbs_cert_list = crl["tbs_cert_list"]

            # Extract issuer
            issuer = tbs_cert_list["issuer"].human_friendly

            # Extract validity period
            this_update = tbs_cert_list["this_update"].native
            next_update = tbs_cert_list["next_update"].native

            # Extract revoked certificates
            revoked_certs = []
            if "revoked_certificates" in tbs_cert_list:
                for revoked in tbs_cert_list["revoked_certificates"]:
                    serial = format(revoked["user_certificate"].native, "X")
                    revocation_date = revoked["revocation_date"].native

                    # Check for reason code
                    reason_code = None
                    if "crl_entry_extensions" in revoked:
                        for extension in revoked["crl_entry_extensions"]:
                            if extension["extn_id"].native == "crl_reason":
                                reason_code = extension["extn_value"].parsed.native

                    # Create RevokedCertificate object
                    revoked_cert = RevokedCertificate(
                        serial_number=serial,
                        revocation_date=revocation_date,
                        reason_code=reason_code,
                    )
                    revoked_certs.append(revoked_cert)
        except Exception as e:
            logger.exception(f"Failed to decode CRL: {e}")
            # Return placeholder data
            now = datetime.now(tz=timezone.utc)
            return "CN=Mock Issuer", now, now, []
        else:
            return issuer, this_update, next_update, revoked_certs
