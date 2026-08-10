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
    from marty_plugin.trust_anchor_pb2 import (
        GetTrustAnchorRequest,
        ListTrustAnchorsRequest,
        ListTrustAnchorsResponse,
        TrustAnchorResponse,
    )
    from marty_plugin.trust_anchor_pb2_grpc import TrustAnchorServiceStub

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
except ImportError as exc:
    logging.warning("Could not import gRPC stubs: %s", exc)
    CscaServiceStub = None
    DocumentSignerServiceStub = None
    TrustAnchorServiceStub = None


from app.models.pkd_models import Certificate, CertificateStatus

logger = logging.getLogger(__name__)


class IntegrationUnavailable(RuntimeError):
    """Raised when a required PKD service integration cannot be constructed."""


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
            if CscaServiceStub is None:
                raise IntegrationUnavailable("CSCA gRPC bindings are unavailable")
            try:
                self._csca_channel = grpc.aio.insecure_channel(self.csca_endpoint)
                self._csca_stub = CscaServiceStub(self._csca_channel)
            except Exception as e:
                logger.exception(f"Failed to create CSCA service stub: {e}")
                raise IntegrationUnavailable("CSCA service is unavailable") from e
        return self._csca_stub

    async def _get_ds_stub(self):
        """Get or create the Document Signer service stub"""
        if self._ds_stub is None:
            if DocumentSignerServiceStub is None:
                raise IntegrationUnavailable(
                    "Document Signer gRPC bindings are unavailable"
                )
            try:
                self._ds_channel = grpc.aio.insecure_channel(self.ds_endpoint)
                self._ds_stub = DocumentSignerServiceStub(self._ds_channel)
            except Exception as e:
                logger.exception(f"Failed to create Document Signer service stub: {e}")
                raise IntegrationUnavailable(
                    "Document Signer service is unavailable"
                ) from e
        return self._ds_stub

    async def _get_ta_stub(self):
        """Get or create the Trust Anchor service stub"""
        if self._ta_stub is None:
            if TrustAnchorServiceStub is None:
                raise IntegrationUnavailable(
                    "Trust Anchor gRPC bindings are unavailable"
                )
            try:
                self._ta_channel = grpc.aio.insecure_channel(self.ta_endpoint)
                self._ta_stub = TrustAnchorServiceStub(self._ta_channel)
            except Exception as e:
                logger.exception(f"Failed to create Trust Anchor service stub: {e}")
                raise IntegrationUnavailable(
                    "Trust Anchor service is unavailable"
                ) from e
        return self._ta_stub

    async def get_csca_certificates(
        self, country: str | None = None
    ) -> list[Certificate]:
        """
        Get CSCA certificates from the CSCA service.

        Raises IntegrationUnavailable if the upstream service cannot be reached.
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

        except IntegrationUnavailable:
            raise
        except Exception as e:
            raise IntegrationUnavailable(
                f"Failed to get CSCA certificates from service: {e}"
            ) from e
        else:
            return certificates

    async def get_document_signer_certificates(
        self, country: str | None = None
    ) -> list[Certificate]:
        """
        Get Document Signer certificates from the Document Signer service.

        Raises IntegrationUnavailable if the upstream service cannot be reached.
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

        except IntegrationUnavailable:
            raise
        except Exception as e:
            raise IntegrationUnavailable(
                f"Failed to get DS certificates from service: {e}"
            ) from e
        else:
            return certificates

    # Additional integration methods would be implemented here
