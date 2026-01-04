#!/usr/bin/env python3
"""
Mock PKD service components for integration testing.
This module provides mocked versions of PKD service classes to enable testing without actual dependencies.
"""

import struct
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class CertificateStatus(Enum):
    """Mock certificate status enum."""

    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"
    SUSPENDED = "SUSPENDED"


class Certificate:
    """Mock Certificate model class."""

    def __init__(
        self,
        id: str,
        subject: str,
        issuer: str,
        valid_from: datetime,
        valid_to: datetime,
        serial_number: str,
        certificate_data: bytes | None = None,
        status: CertificateStatus = CertificateStatus.ACTIVE,
        country_code: str = None,
    ):
        self.id = id
        self.subject = subject
        self.issuer = issuer
        self.valid_from = valid_from
        self.valid_to = valid_to
        self.serial_number = serial_number
        self.certificate_data = certificate_data
        self.status = status
        self.country_code = country_code
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        """Convert certificate to dictionary representation."""
        return {
            "id": self.id,
            "subject": self.subject,
            "issuer": self.issuer,
            "valid_from": self.valid_from.isoformat(),
            "valid_to": self.valid_to.isoformat(),
            "serial_number": self.serial_number,
            "status": self.status.value,
            "country_code": self.country_code,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class MockASN1Decoder:
    """Mock ASN.1 decoder for testing purposes."""

    @staticmethod
    def decode_master_list(data: bytes) -> list[Certificate]:
        """
        Mock decode master list from ASN.1 DER data.
        This implementation provides a simplified parsing for testing.
        """
        certificates = []

        if len(data) < 10:
            return certificates

        # Check if it starts with ASN.1 SEQUENCE tag (0x30)
        if data[0] != 0x30:
            return certificates

        # Simple parsing - look for certificate patterns in the data
        data_str = data.decode("utf-8", errors="ignore")

        # Extract certificate information from the data
        cert_count = 0
        position = 0

        while position < len(data) - 10:
            # Look for certificate patterns
            if b"Certificate:" in data[position : position + 20]:
                cert_count += 1
                # Extract basic info (this is a simplified mock)
                cert_id = f"mock_cert_{cert_count}"
                subject = f"CN=Mock Certificate {cert_count}"
                issuer = f"CN=Mock Issuer {cert_count}"

                certificate = Certificate(
                    id=cert_id,
                    subject=subject,
                    issuer=issuer,
                    valid_from=datetime.now(timezone.utc),
                    valid_to=datetime.now(timezone.utc),
                    serial_number=f"serial_{cert_count}",
                    status=CertificateStatus.ACTIVE,
                    country_code="US",
                )
                certificates.append(certificate)
                position += 50
            else:
                position += 1

        return certificates

    @staticmethod
    def decode_certificate(data: bytes) -> Certificate | None:
        """Mock decode single certificate from ASN.1 DER data."""
        if len(data) < 10:
            return None

        # Mock certificate creation
        return Certificate(
            id="mock_single_cert",
            subject="CN=Mock Single Certificate",
            issuer="CN=Mock Single Issuer",
            valid_from=datetime.now(timezone.utc),
            valid_to=datetime.now(timezone.utc),
            serial_number="mock_serial",
            status=CertificateStatus.ACTIVE,
            country_code="US",
        )


class MockASN1Encoder:
    """Mock ASN.1 encoder for testing purposes."""

    @staticmethod
    def encode_certificate(certificate: Certificate) -> bytes:
        """Mock encode certificate to ASN.1 DER format."""
        # Create a simple mock ASN.1 structure
        cert_info = f"Certificate: {certificate.subject}".encode()

        # Create ASN.1 SEQUENCE structure (simplified)
        length = len(cert_info)
        if length < 128:
            length_bytes = bytes([length])
        else:
            length_bytes = bytes([0x81, length])

        return bytes([0x30]) + length_bytes + cert_info

    @staticmethod
    def encode_master_list(certificates: list[Certificate]) -> bytes:
        """Mock encode master list to ASN.1 DER format."""
        encoded_certs = []

        for cert in certificates:
            cert_data = MockASN1Encoder.encode_certificate(cert)
            encoded_certs.append(cert_data)

        # Combine all certificates
        total_data = b"".join(encoded_certs)
        total_length = len(total_data)

        # Create outer SEQUENCE
        if total_length < 128:
            length_bytes = bytes([total_length])
        elif total_length < 256:
            length_bytes = bytes([0x81, total_length])
        else:
            length_bytes = bytes([0x82, total_length >> 8, total_length & 0xFF])

        return bytes([0x30]) + length_bytes + total_data


class MockMasterListService:
    """Mock master list service for testing."""

    def __init__(self):
        self.processed_lists = []

    async def process_master_list(self, ml_data: bytes, country: str) -> dict[str, Any]:
        """Mock process master list data."""
        try:
            certificates = MockASN1Decoder.decode_master_list(ml_data)

            result = {
                "country": country,
                "certificates_found": len(certificates),
                "certificates": [cert.to_dict() for cert in certificates],
                "processed_at": datetime.now(timezone.utc).isoformat(),
                "status": "success",
            }

            self.processed_lists.append(result)
            return result

        except Exception as e:
            return {
                "country": country,
                "status": "error",
                "error": str(e),
                "processed_at": datetime.now(timezone.utc).isoformat(),
            }

    async def upload_master_list(self, ml_file_path: str, country: str) -> dict[str, Any]:
        """Mock upload master list from file."""
        try:
            with open(ml_file_path, "rb") as f:
                ml_data = f.read()

            return await self.process_master_list(ml_data, country)

        except Exception as e:
            return {
                "country": country,
                "status": "error",
                "error": f"File read error: {str(e)}",
                "processed_at": datetime.now(timezone.utc).isoformat(),
            }

    def get_processed_lists(self) -> list[dict[str, Any]]:
        """Get all processed master lists."""
        return self.processed_lists.copy()

    def clear_processed_lists(self):
        """Clear processed lists (for testing)."""
        self.processed_lists.clear()


class MockTrustService:
    """Mock trust service for testing master list validation."""

    def __init__(self):
        self.validated_lists = []
        self.master_list_service = MockMasterListService()

    async def validate_master_list(self, ml_data: bytes, country: str) -> dict[str, Any]:
        """Mock validate master list through trust service."""
        try:
            # Process through mock master list service
            ml_result = await self.master_list_service.process_master_list(ml_data, country)

            if ml_result["status"] == "success":
                # Additional trust service validation
                validation_result = {
                    "validation_id": f"trust_validation_{len(self.validated_lists) + 1}",
                    "country": country,
                    "status": "validated",
                    "certificates_validated": ml_result["certificates_found"],
                    "validation_details": {
                        "asn1_parsing": "success",
                        "certificate_structure": "valid",
                        "signature_verification": "mocked_valid",
                        "trust_chain": "mocked_valid",
                    },
                    "master_list_info": ml_result,
                    "validated_at": datetime.now(timezone.utc).isoformat(),
                }
            else:
                validation_result = {
                    "validation_id": f"trust_validation_{len(self.validated_lists) + 1}",
                    "country": country,
                    "status": "failed",
                    "error": ml_result.get("error", "Unknown error"),
                    "validated_at": datetime.now(timezone.utc).isoformat(),
                }

            self.validated_lists.append(validation_result)
            return validation_result

        except Exception as e:
            error_result = {
                "validation_id": f"trust_validation_{len(self.validated_lists) + 1}",
                "country": country,
                "status": "error",
                "error": str(e),
                "validated_at": datetime.now(timezone.utc).isoformat(),
            }
            self.validated_lists.append(error_result)
            return error_result

    def get_validation_history(self) -> list[dict[str, Any]]:
        """Get all validation results."""
        return self.validated_lists.copy()

    def clear_validation_history(self):
        """Clear validation history (for testing)."""
        self.validated_lists.clear()
