#!/usr/bin/env python3
"""
Mock test for CSCA certificate lifecycle management.

This script tests certificate lifecycle management without relying on proto files.
It creates a mock implementation of both the service and the proto messages.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Mock proto message classes
@dataclass
class MockCreateCertificateRequest:
    subject_name: str = ""
    validity_days: int = 365
    key_algorithm: str = "RSA"
    key_size: int = 2048
    extensions: dict[str, str] = None


@dataclass
class MockCreateCertificateResponse:
    certificate_id: str = ""
    certificate_data: str = ""
    status: str = ""
    error_message: str = ""


@dataclass
class MockRenewCertificateRequest:
    certificate_id: str = ""
    validity_days: int = 365
    reuse_key: bool = False


@dataclass
class MockRevokeCertificateRequest:
    certificate_id: str = ""
    reason: str = ""


@dataclass
class MockRevokeCertificateResponse:
    certificate_id: str = ""
    success: bool = False
    status: str = ""
    error_message: str = ""


@dataclass
class MockCertificateStatusRequest:
    certificate_id: str = ""


@dataclass
class MockCertificateStatusResponse:
    certificate_id: str = ""
    status: str = ""
    not_before: str = ""
    not_after: str = ""
    revocation_reason: str | None = None
    subject: str = ""
    issuer: str = ""


@dataclass
class MockListCertificatesRequest:
    status_filter: str = ""
    subject_filter: str = ""


@dataclass
class MockCertificateSummary:
    certificate_id: str = ""
    subject: str = ""
    status: str = ""
    not_before: str = ""
    not_after: str = ""
    revocation_reason: str | None = None


@dataclass
class MockListCertificatesResponse:
    certificates: list[MockCertificateSummary] = None

    def __post_init__(self):
        if self.certificates is None:
            self.certificates = []


@dataclass
class MockCheckExpiringCertificatesRequest:
    days_threshold: int = 30


# Mock CSCA Service implementation
class MockCscaService:
    """Mock implementation of the CSCA service for testing certificate lifecycle management."""

    def __init__(self):
        """Initialize the service with test data."""
        self.certificates = {}
        self.revoked_certificates = {}
        self.test_dir = os.path.join(os.path.dirname(__file__), "data", "mock_csca")
        os.makedirs(self.test_dir, exist_ok=True)
        logger.info(f"Initialized MockCscaService with test directory: {self.test_dir}")

    def CreateCertificate(self, request):
        """Create a new certificate."""
        certificate_id = str(uuid.uuid4())
        not_before = datetime.now(timezone.utc)
        not_after = not_before + timedelta(days=request.validity_days)

        certificate_data = {
            "certificate_id": certificate_id,
            "subject": request.subject_name,
            "status": "VALID",
            "not_before": not_before.isoformat(),
            "not_after": not_after.isoformat(),
            "certificate_data": f"MOCK_CERTIFICATE_FOR_{request.subject_name}",
            "key_algorithm": request.key_algorithm,
            "key_size": request.key_size,
        }

        self.certificates[certificate_id] = certificate_data

        with open(os.path.join(self.test_dir, f"{certificate_id}.json"), "w") as f:
            json.dump(certificate_data, f)

        logger.info(f"Created certificate with ID: {certificate_id}")

        return MockCreateCertificateResponse(
            certificate_id=certificate_id,
            certificate_data=certificate_data["certificate_data"],
            status="ISSUED",
        )

    def RenewCertificate(self, request):
        """Renew an existing certificate."""
        if request.certificate_id not in self.certificates:
            logger.error(f"Certificate with ID {request.certificate_id} not found")
            return MockCreateCertificateResponse(
                status="FAILED",
                error_message=f"Certificate with ID {request.certificate_id} not found",
            )

        cert_data = self.certificates[request.certificate_id]
        new_certificate_id = str(uuid.uuid4())

        not_before = datetime.now(timezone.utc)
        not_after = not_before + timedelta(days=request.validity_days)

        new_certificate_data = {
            "certificate_id": new_certificate_id,
            "subject": cert_data["subject"],
            "status": "VALID",
            "not_before": not_before.isoformat(),
            "not_after": not_after.isoformat(),
            "certificate_data": f"RENEWED_CERTIFICATE_FOR_{cert_data['subject']}",
            "key_algorithm": cert_data["key_algorithm"],
            "key_size": cert_data["key_size"],
            "renewed_from": request.certificate_id,
        }

        self.certificates[new_certificate_id] = new_certificate_data
        self.certificates[request.certificate_id]["status"] = "SUPERSEDED"
        self.certificates[request.certificate_id]["superseded_by"] = new_certificate_id

        with open(os.path.join(self.test_dir, f"{new_certificate_id}.json"), "w") as f:
            json.dump(new_certificate_data, f)

        with open(os.path.join(self.test_dir, f"{request.certificate_id}.json"), "w") as f:
            json.dump(self.certificates[request.certificate_id], f)

        logger.info(f"Renewed certificate with new ID: {new_certificate_id}")

        return MockCreateCertificateResponse(
            certificate_id=new_certificate_id,
            certificate_data=new_certificate_data["certificate_data"],
            status="RENEWED",
        )

    def RevokeCertificate(self, request):
        """Revoke a certificate."""
        if request.certificate_id not in self.certificates:
            logger.error(f"Certificate with ID {request.certificate_id} not found")
            return MockRevokeCertificateResponse(
                certificate_id=request.certificate_id,
                success=False,
                status="FAILED",
                error_message=f"Certificate with ID {request.certificate_id} not found",
            )

        cert_data = self.certificates[request.certificate_id]

        if cert_data["status"] == "REVOKED":
            logger.warning(f"Certificate with ID {request.certificate_id} is already revoked")
            return MockRevokeCertificateResponse(
                certificate_id=request.certificate_id, success=True, status="REVOKED"
            )

        cert_data["status"] = "REVOKED"
        cert_data["revocation_date"] = datetime.now(timezone.utc).isoformat()
        cert_data["revocation_reason"] = request.reason

        self.revoked_certificates[request.certificate_id] = {
            "certificate_id": request.certificate_id,
            "revocation_date": cert_data["revocation_date"],
            "revocation_reason": request.reason,
        }

        with open(os.path.join(self.test_dir, f"{request.certificate_id}.json"), "w") as f:
            json.dump(cert_data, f)

        with open(os.path.join(self.test_dir, "revoked.json"), "w") as f:
            json.dump(self.revoked_certificates, f)

        logger.info(f"Revoked certificate with ID: {request.certificate_id}")

        return MockRevokeCertificateResponse(
            certificate_id=request.certificate_id, success=True, status="REVOKED"
        )

    def GetCertificateStatus(self, request):
        """Get the status of a certificate."""
        if request.certificate_id not in self.certificates:
            logger.warning(f"Certificate with ID {request.certificate_id} not found")
            return MockCertificateStatusResponse(
                certificate_id=request.certificate_id, status="NOT_FOUND"
            )

        cert_data = self.certificates[request.certificate_id]

        if cert_data["status"] == "REVOKED":
            return MockCertificateStatusResponse(
                certificate_id=request.certificate_id,
                status="REVOKED",
                not_before=cert_data.get("not_before", ""),
                not_after=cert_data.get("not_after", ""),
                revocation_reason=cert_data.get("revocation_reason", ""),
                subject=cert_data.get("subject", ""),
                issuer=cert_data.get("issuer", "Self"),
            )

        not_after = datetime.fromisoformat(
            cert_data.get("not_after", datetime.now(timezone.utc).isoformat())
        )
        if not_after < datetime.now(timezone.utc):
            return MockCertificateStatusResponse(
                certificate_id=request.certificate_id,
                status="EXPIRED",
                not_before=cert_data.get("not_before", ""),
                not_after=cert_data.get("not_after", ""),
                subject=cert_data.get("subject", ""),
                issuer=cert_data.get("issuer", "Self"),
            )

        return MockCertificateStatusResponse(
            certificate_id=request.certificate_id,
            status=cert_data.get("status", "VALID"),
            not_before=cert_data.get("not_before", ""),
            not_after=cert_data.get("not_after", ""),
            subject=cert_data.get("subject", ""),
            issuer=cert_data.get("issuer", "Self"),
        )

    def ListCertificates(self, request):
        """List certificates with optional filtering."""
        certificates = []

        for cert_id, cert_data in self.certificates.items():
            # Apply status filter if provided
            if request.status_filter and cert_data.get("status") != request.status_filter:
                continue

            # Apply subject filter if provided
            if (
                request.subject_filter
                and request.subject_filter.lower() not in cert_data.get("subject", "").lower()
            ):
                continue

            # Add to result list
            certificates.append(
                MockCertificateSummary(
                    certificate_id=cert_id,
                    subject=cert_data.get("subject", ""),
                    status=cert_data.get("status", ""),
                    not_before=cert_data.get("not_before", ""),
                    not_after=cert_data.get("not_after", ""),
                    revocation_reason=cert_data.get("revocation_reason", None),
                )
            )

        logger.info(
            f"Listing certificates with filter '{request.status_filter}', found: {len(certificates)}"
        )
        return MockListCertificatesResponse(certificates=certificates)

    def CheckExpiringCertificates(self, request):
        """Check for certificates nearing expiration."""
        expiry_date = datetime.now(timezone.utc) + timedelta(days=request.days_threshold)
        expiring_certificates = []

        for cert_id, cert_data in self.certificates.items():
            # Skip certificates that are not valid
            if cert_data.get("status") != "VALID":
                continue

            # Check expiration date
            not_after = datetime.fromisoformat(
                cert_data.get("not_after", datetime.now(timezone.utc).isoformat())
            )
            if not_after <= expiry_date:
                expiring_certificates.append(
                    MockCertificateSummary(
                        certificate_id=cert_id,
                        subject=cert_data.get("subject", ""),
                        status=cert_data.get("status", ""),
                        not_before=cert_data.get("not_before", ""),
                        not_after=cert_data.get("not_after", ""),
                    )
                )

        logger.info(
            f"Found {len(expiring_certificates)} certificates expiring within {request.days_threshold} days"
        )
        return MockListCertificatesResponse(certificates=expiring_certificates)


def test_certificate_lifecycle():
    """Test the complete certificate lifecycle."""
    service = MockCscaService()

    # Generate a unique test ID
    test_id = uuid.uuid4().hex[:8]
    logger.info(f"Starting certificate lifecycle test with ID: {test_id}")

    # Step 1: Create a new certificate
    logger.info("Step 1: Creating a new certificate")
    create_request = MockCreateCertificateRequest(
        subject_name=f"CN=Test CSCA {test_id}, O=Mock Test",
        validity_days=365,
        key_algorithm="RSA",
        key_size=2048,
    )
    create_response = service.CreateCertificate(create_request)

    assert create_response.certificate_id, "Certificate ID should not be empty"
    assert (
        create_response.status == "ISSUED"
    ), f"Expected status ISSUED, got {create_response.status}"
    certificate_id = create_response.certificate_id
    logger.info(f"Created certificate with ID: {certificate_id}")

    # Step 2: Check certificate status
    logger.info("Step 2: Checking certificate status")
    status_request = MockCertificateStatusRequest(certificate_id=certificate_id)
    status_response = service.GetCertificateStatus(status_request)

    assert status_response.status == "VALID", f"Expected status VALID, got {status_response.status}"
    logger.info(f"Certificate status: {status_response.status}")

    # Step 3: List certificates
    logger.info("Step 3: Listing certificates")
    list_request = MockListCertificatesRequest(status_filter="VALID")
    list_response = service.ListCertificates(list_request)

    # Find our test certificate in the list
    found = False
    for cert in list_response.certificates:
        if cert.certificate_id == certificate_id:
            found = True
            assert cert.status == "VALID"
            break

    assert found, "Certificate not found in the list"
    logger.info(
        f"Found certificate in the list with total count: {len(list_response.certificates)}"
    )

    # Step 4: Renew certificate
    logger.info("Step 4: Renewing certificate")
    renew_request = MockRenewCertificateRequest(
        certificate_id=certificate_id,
        validity_days=730,
        reuse_key=True,  # 2 years
    )
    renew_response = service.RenewCertificate(renew_request)

    assert (
        renew_response.certificate_id != certificate_id
    ), "Renewed certificate should have a new ID"
    assert (
        renew_response.status == "RENEWED"
    ), f"Expected status RENEWED, got {renew_response.status}"
    renewed_certificate_id = renew_response.certificate_id
    logger.info(f"Renewed certificate with new ID: {renewed_certificate_id}")

    # Step 5: Check original certificate status
    logger.info("Step 5: Checking original certificate status")
    original_status_request = MockCertificateStatusRequest(certificate_id=certificate_id)
    original_status_response = service.GetCertificateStatus(original_status_request)

    assert (
        original_status_response.status == "SUPERSEDED"
    ), f"Expected status SUPERSEDED, got {original_status_response.status}"
    logger.info(f"Original certificate status: {original_status_response.status}")

    # Step 6: Revoke renewed certificate
    logger.info("Step 6: Revoking renewed certificate")
    revoke_request = MockRevokeCertificateRequest(
        certificate_id=renewed_certificate_id, reason="KEY_COMPROMISE"
    )
    revoke_response = service.RevokeCertificate(revoke_request)

    assert revoke_response.success, "Revocation should be successful"
    assert (
        revoke_response.status == "REVOKED"
    ), f"Expected status REVOKED, got {revoke_response.status}"
    logger.info(f"Revoked certificate with ID: {renewed_certificate_id}")

    # Step 7: Check revoked certificate status
    logger.info("Step 7: Checking revoked certificate status")
    revoked_status_request = MockCertificateStatusRequest(certificate_id=renewed_certificate_id)
    revoked_status_response = service.GetCertificateStatus(revoked_status_request)

    assert (
        revoked_status_response.status == "REVOKED"
    ), f"Expected status REVOKED, got {revoked_status_response.status}"
    assert (
        revoked_status_response.revocation_reason == "KEY_COMPROMISE"
    ), f"Expected reason KEY_COMPROMISE, got {revoked_status_response.revocation_reason}"
    logger.info(f"Revoked certificate status: {revoked_status_response.status}")

    # Step 8: Create a certificate that will expire soon
    logger.info("Step 8: Creating a certificate that will expire soon")
    expiring_create_request = MockCreateCertificateRequest(
        subject_name=f"CN=Expiring CSCA {test_id}, O=Mock Test",
        validity_days=10,  # Short validity to test expiring soon
    )
    expiring_create_response = service.CreateCertificate(expiring_create_request)
    expiring_certificate_id = expiring_create_response.certificate_id
    logger.info(f"Created expiring certificate with ID: {expiring_certificate_id}")

    # Step 9: Check for certificates expiring soon
    logger.info("Step 9: Checking for certificates expiring soon")
    expiry_request = MockCheckExpiringCertificatesRequest(days_threshold=30)
    expiry_response = service.CheckExpiringCertificates(expiry_request)

    # Find our expiring certificate in the list
    found = False
    for cert in expiry_response.certificates:
        if cert.certificate_id == expiring_certificate_id:
            found = True
            break

    assert found, "Expiring certificate not found in the expiring list"
    logger.info(
        f"Found expiring certificate in the list with total count: {len(expiry_response.certificates)}"
    )

    logger.info("All tests passed! Certificate lifecycle management is working correctly.")


if __name__ == "__main__":
    test_certificate_lifecycle()
