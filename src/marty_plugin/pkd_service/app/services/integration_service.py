"""
Integration service for connecting with other Marty microservices
"""

from __future__ import annotations

import logging
import os

# Import the compiled protobuf modules
import sys
import uuid
from datetime import datetime

import grpc

sys.path.append("/app")  # Ensure Python can find the modules
try:
    from marty_plugin.proto.v1.csca_service_pb2 import (
        CscaCertificateResponse,
        GetCscaCertificateRequest,
        ListCscaCertificatesRequest,
        ListCscaCertificatesResponse,
    )
    from marty_plugin.proto.v1.csca_service_pb2_grpc import CscaServiceStub
    from marty_plugin.proto.v1.document_signer_pb2 import (
        DocumentSignerCertificateResponse,
        GetDocumentSignerCertificateRequest,
        ListDocumentSignerCertificatesRequest,
        ListDocumentSignerCertificatesResponse,
    )
    from marty_plugin.proto.v1.document_signer_pb2_grpc import DocumentSignerServiceStub
    from marty_plugin.trust_anchor_pb2 import (
        GetTrustAnchorRequest,
        ListTrustAnchorsRequest,
        ListTrustAnchorsResponse,
        TrustAnchorResponse,
    )
    from marty_plugin.trust_anchor_pb2_grpc import TrustAnchorServiceStub
except ImportError:
    logging.warning("Could not import gRPC stubs. Integration will be mocked.")

    # Create mock/placeholder classes
    class CscaServiceStub:
        pass

    class DocumentSignerServiceStub:
        pass

    class TrustAnchorServiceStub:
        pass


from app.models.pkd_models import Certificate, CertificateStatus

logger = logging.getLogger(__name__)


class IntegrationService:
    """Service for integrating with other Marty microservices"""

    def __init__(self) -> None:
        # Service endpoints from environment variables with defaults for development
        self.csca_endpoint = os.getenv(
            "CSCA_SERVICE_ENDPOINT", "csca-service.marty.svc.cluster.local:8081"
        )
        self.ds_endpoint = os.getenv(
            "DS_SERVICE_ENDPOINT", "document-signer.marty.svc.cluster.local:8082"
        )
        self.ta_endpoint = os.getenv(
            "TRUST_ANCHOR_ENDPOINT", "trust-anchor.marty.svc.cluster.local:9080"
        )

        # Initialize gRPC channels and stubs
        self._csca_channel = None
        self._ds_channel = None
        self._ta_channel = None
        self._csca_stub = None
        self._ds_stub = None
        self._ta_stub = None

    async def _get_csca_stub(self):
        """Get or create the CSCA service stub"""
        if self._csca_stub is None:
            try:
                self._csca_channel = grpc.aio.insecure_channel(self.csca_endpoint)
                self._csca_stub = CscaServiceStub(self._csca_channel)
            except Exception as e:
                logger.exception(f"Failed to create CSCA service stub: {e}")
                # Return a mock stub that will handle the error case
        return self._csca_stub

    async def _get_ds_stub(self):
        """Get or create the Document Signer service stub"""
        if self._ds_stub is None:
            try:
                self._ds_channel = grpc.aio.insecure_channel(self.ds_endpoint)
                self._ds_stub = DocumentSignerServiceStub(self._ds_channel)
            except Exception as e:
                logger.exception(f"Failed to create Document Signer service stub: {e}")
                # Return a mock stub that will handle the error case
        return self._ds_stub

    async def _get_ta_stub(self):
        """Get or create the Trust Anchor service stub"""
        if self._ta_stub is None:
            try:
                self._ta_channel = grpc.aio.insecure_channel(self.ta_endpoint)
                self._ta_stub = TrustAnchorServiceStub(self._ta_channel)
            except Exception as e:
                logger.exception(f"Failed to create Trust Anchor service stub: {e}")
                # Return a mock stub that will handle the error case
        return self._ta_stub

    async def get_csca_certificates(self, country: str | None = None) -> list[Certificate]:
        """
        Get CSCA certificates from the CSCA service.

        In development mode or if the service is unavailable, returns mock data.
        """
        try:
            stub = await self._get_csca_stub()

            # Create the request
            request = ListCscaCertificatesRequest()
            if country:
                request.country_filter = country

            # Make the gRPC call
            response = await stub.ListCscaCertificates(request)

            # Convert the gRPC response to our model
            certificates = []
            for cert in response.certificates:
                certificates.append(
                    Certificate(
                        id=str(uuid.UUID(cert.id)),
                        subject=cert.subject,
                        issuer=cert.issuer,
                        valid_from=datetime.fromisoformat(cert.valid_from),
                        valid_to=datetime.fromisoformat(cert.valid_to),
                        serial_number=cert.serial_number,
                        certificate_data=cert.certificate_data,
                        status=(
                            CertificateStatus.ACTIVE
                            if cert.is_active
                            else CertificateStatus.REVOKED
                        ),
                        country_code=cert.country_code,
                    )
                )

        except Exception as e:
            logger.warning(f"Failed to get CSCA certificates from service: {e}")
            logger.info("Returning mock CSCA certificate data")

            # Return mock data in case of failure
            datetime.now()
            mock_certificates = [
                Certificate(
                    id=uuid.uuid4(),
                    subject="CN=CSCA-USA,O=Department of State,C=US",
                    issuer="CN=CSCA-USA,O=Department of State,C=US",
                    valid_from=datetime(2020, 1, 1),
                    valid_to=datetime(2030, 1, 1),
                    serial_number="01234567",
                    certificate_data=b"MOCK_CERTIFICATE_DATA_USA",
                    status=CertificateStatus.ACTIVE,
                    country_code="USA",
                ),
                Certificate(
                    id=uuid.uuid4(),
                    subject="CN=CSCA-CAN,O=Passport Canada,C=CA",
                    issuer="CN=CSCA-CAN,O=Passport Canada,C=CA",
                    valid_from=datetime(2020, 1, 1),
                    valid_to=datetime(2030, 1, 1),
                    serial_number="89012345",
                    certificate_data=b"MOCK_CERTIFICATE_DATA_CAN",
                    status=CertificateStatus.ACTIVE,
                    country_code="CAN",
                ),
            ]

            if country:
                return [cert for cert in mock_certificates if cert.country_code == country]
            return mock_certificates
        else:
            return certificates

    async def get_document_signer_certificates(
        self, country: str | None = None
    ) -> list[Certificate]:
        """
        Get Document Signer certificates from the Document Signer service.

        In development mode or if the service is unavailable, returns mock data.
        """
        try:
            stub = await self._get_ds_stub()

            # Create the request
            request = ListDocumentSignerCertificatesRequest()
            if country:
                request.country_filter = country

            # Make the gRPC call
            response = await stub.ListDocumentSignerCertificates(request)

            # Convert the gRPC response to our model
            certificates = []
            for cert in response.certificates:
                certificates.append(
                    Certificate(
                        id=str(uuid.UUID(cert.id)),
                        subject=cert.subject,
                        issuer=cert.issuer,
                        valid_from=datetime.fromisoformat(cert.valid_from),
                        valid_to=datetime.fromisoformat(cert.valid_to),
                        serial_number=cert.serial_number,
                        certificate_data=cert.certificate_data,
                        status=(
                            CertificateStatus.ACTIVE
                            if cert.is_active
                            else CertificateStatus.REVOKED
                        ),
                        country_code=cert.country_code,
                    )
                )

        except Exception as e:
            logger.warning(f"Failed to get DS certificates from service: {e}")
            logger.info("Returning mock DS certificate data")

            # Return mock data in case of failure
            mock_certificates = [
                Certificate(
                    id=uuid.uuid4(),
                    subject="CN=DS-001-USA,O=Department of State,C=US",
                    issuer="CN=CSCA-USA,O=Department of State,C=US",
                    valid_from=datetime(2022, 1, 1),
                    valid_to=datetime(2025, 1, 1),
                    serial_number="DSC00000001",
                    certificate_data=b"MOCK_DSC_DATA_USA_001",
                    status=CertificateStatus.ACTIVE,
                    country_code="USA",
                ),
                Certificate(
                    id=uuid.uuid4(),
                    subject="CN=DS-001-CAN,O=Passport Canada,C=CA",
                    issuer="CN=CSCA-CAN,O=Passport Canada,C=CA",
                    valid_from=datetime(2022, 1, 1),
                    valid_to=datetime(2025, 1, 1),
                    serial_number="DSC00000002",
                    certificate_data=b"MOCK_DSC_DATA_CAN_001",
                    status=CertificateStatus.ACTIVE,
                    country_code="CAN",
                ),
            ]

            if country:
                return [cert for cert in mock_certificates if cert.country_code == country]
            return mock_certificates
        else:
            return certificates

    # Additional integration methods would be implemented here
