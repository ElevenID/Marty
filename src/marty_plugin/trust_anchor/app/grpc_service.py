#!/usr/bin/env python3
"""
Trust Anchor gRPC service implementation.

This service provides functionality for:
- Verifying trust relationships
- Managing certificate trust stores
- Monitoring certificate expiry
- Importing and querying CSCA master lists
"""

import logging
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

# Add project root to path for imports
# This needs to be done before attempting to import from 'src'
_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from marty_backend_common.logging_config import get_logger, setup_logging
from marty_backend_common.service_config_factory import get_config_manager

# Import shared utilities
from marty_backend_common.services import BaseGrpcService

# Local application/library specific imports
# Import gRPC generated modules
from marty_plugin.proto.trust_anchor_pb2 import (
    CertificateInfo,
    ExpiringCertificate,
    ExpiryCheckResponse,
    MasterListResponse,
    ServiceStats,
    ServiceStatusResponse,
    SyncResponse,
    TrustResponse,
    UploadMasterListResponse,
    VerificationResponse,
)
from marty_plugin.proto.trust_anchor_pb2_grpc import TrustAnchorServicer, add_TrustAnchorServicer_to_server

# Import our services
from marty_plugin.trust_anchor.app.services.certificate_expiry_service import CertificateExpiryService
from marty_plugin.trust_anchor.app.services.openxpki_service import OpenXPKIService

# Configure logging using shared utility
setup_logging(service_name="trust-anchor")
logger = get_logger(__name__)


class TrustAnchorService(TrustAnchorServicer):
    """
    Implementation of the Trust Anchor gRPC service.

    This service handles trust verification, certificate management,
    and integration with OpenXPKI for CSCA and master list operations.
    """

    def __init__(self) -> None:
        """Initialize the Trust Anchor service."""
        logger.info("Initializing Trust Anchor Service")

        # Initialize configuration using DRY factory
        self.config_manager = get_config_manager("trust-anchor")

        # Initialize OpenXPKI service
        self.openxpki_service = OpenXPKIService()

        # Initialize Certificate Expiry Service
        self.certificate_expiry_service = CertificateExpiryService(
            openxpki_service=self.openxpki_service,
            check_interval_days=self.config_manager.get_env_int("CERT_CHECK_INTERVAL_DAYS", 1),
            notification_days=self._get_notification_days(),
            history_file=self.config_manager.get_env_path("CERT_HISTORY_FILE"),
        )

        # Additional service initialization can go here

    def _get_notification_days(self) -> list[int]:
        """
        Get notification days from environment variable or use defaults.

        Returns:
            List of days before expiry to send notifications
        """
        notification_days_str = self.config_manager.get_env_list(
            "CERT_NOTIFICATION_DAYS", default=["30", "15", "7", "5", "3", "1"]
        )
        try:
            return [int(days) for days in notification_days_str]
        except (ValueError, TypeError):
            logger.warning("Invalid CERT_NOTIFICATION_DAYS format, using defaults")
            return [30, 15, 7, 5, 3, 1]

    def VerifyTrust(self, request, context):
        """
        Verify if an entity is trusted.

        Args:
            request: The VerifyTrust request
            context: gRPC context

        Returns:
            TrustResponse with verification results
        """
        logger.info("Received trust verification request for entity: %s", request.entity)

        # For now, implement simple verification (expand this in a real implementation)
        # A real implementation would check against trust stores or PKI
        trusted = request.entity in ["known_trusted_entity", "test_entity"]

        return TrustResponse(is_trusted=trusted)

    def GetMasterList(self, request, context):
        """
        Get the current master list.

        Args:
            request: The GetMasterList request
            context: gRPC context

        Returns:
            MasterListResponse with master list data and metadata
        """
        logger.info("Received master list request in format: %s", request.format)

        # Get master list from OpenXPKI service
        ml_result = self.openxpki_service.get_master_list(request.format)

        # Convert to bytes if needed
        if isinstance(ml_result.get("master_list_data"), str):
            master_list_data = ml_result.get("master_list_data", "").encode("utf-8")
        else:
            master_list_data = ml_result.get("master_list_data", b"")

        # Build response
        return MasterListResponse(
            master_list_data=master_list_data,
            format=request.format,
            certificate_count=ml_result.get("certificate_count", 0),
            is_valid=ml_result.get("is_valid", False),
            last_updated=ml_result.get("last_updated", ""),
        )

    def UploadMasterList(self, request, context):
        """
        Upload a master list to the system.

        Args:
            request: The UploadMasterList request
            context: gRPC context

        Returns:
            UploadMasterListResponse with import results
        """
        logger.info("Received master list upload in format: %s", request.format)

        # Import master list to OpenXPKI
        import_result = self.openxpki_service.import_master_list(
            request.master_list_data, request.format
        )

        # Build certificate info list for response
        certificates = []
        for cert_data in import_result.get("certificates", []):
            certificates.append(
                CertificateInfo(
                    subject=cert_data.get("subject", ""),
                    issuer=cert_data.get("issuer", ""),
                    serial_number=cert_data.get("serial_number", ""),
                    not_before=cert_data.get("not_before", ""),
                    not_after=cert_data.get("not_after", ""),
                    country_code=cert_data.get("country_code", ""),
                    fingerprint=cert_data.get("fingerprint", ""),
                )
            )

        # Build response
        return UploadMasterListResponse(
            success=import_result.get("success", False),
            certificates_imported=import_result.get("certificates_imported", 0),
            errors=import_result.get("error", []),
            certificates=certificates,
        )

    def VerifyCertificate(self, request, context):
        """
        Verify a certificate against trusted certificates.

        Args:
            request: The VerifyCertificate request
            context: gRPC context

        Returns:
            VerificationResponse with verification results
        """
        logger.info("Received certificate verification request in format: %s", request.format)

        # Verify the certificate
        verify_result = self.openxpki_service.verify_certificate(
            request.certificate, request.format, request.check_revocation
        )

        # Build response
        return VerificationResponse(
            is_valid=verify_result.get("is_valid", False),
            subject=verify_result.get("subject", ""),
            issuer=verify_result.get("issuer", ""),
            validation_errors=verify_result.get("validation_errors", []),
            is_trusted=verify_result.get("is_trusted", False),
            is_revoked=verify_result.get("is_revoked", False),
            revocation_reason=verify_result.get("revocation_reason", ""),
        )

    def SyncCertificateStore(self, request, context):
        """
        Synchronize certificates from OpenXPKI to the local trust store.

        Args:
            request: The SyncRequest
            context: gRPC context

        Returns:
            SyncResponse with synchronization results
        """
        logger.info("Received certificate store sync request, force=%s", request.force)

        # Sync certificates to local store
        sync_result = self.openxpki_service.sync_to_local_store(request.force)

        # Build response
        return SyncResponse(
            success=sync_result.get("success", False),
            certificates_synced=sync_result.get("certificates_synced", 0),
            sync_timestamp=sync_result.get("sync_timestamp", ""),
            errors=sync_result.get("errors", []),
        )

    def CheckExpiringCertificates(self, request, context):
        """
        Check for certificates that will expire within the specified number of days.

        Args:
            request: The ExpiryCheckRequest
            context: gRPC context

        Returns:
            ExpiryCheckResponse with list of expiring certificates
        """
        days = request.days if request.days > 0 else 90
        logger.info("Received expiring certificates check request for %s days", days)

        # Check for expiring certificates
        expiry_result = self.openxpki_service.check_expiring_certificates(days)

        # Build the list of expiring certificates for the response
        expiring_certificates = []
        for cert in expiry_result.get("expiring_certificates", []):
            expiring_certificates.append(
                ExpiringCertificate(
                    subject=cert.get("subject", ""),
                    issuer=cert.get("issuer", ""),
                    serial_number=cert.get("serial_number", ""),
                    not_after=cert.get("not_after", ""),
                    days_remaining=cert.get("days_remaining", 0),
                    country_code=cert.get("country_code", ""),
                )
            )

        # Build response
        return ExpiryCheckResponse(expiring_certificates=expiring_certificates)

    def GetServiceStatus(self, request, context):
        """
        Get the status of the Trust Anchor and OpenXPKI services.

        Args:
            request: The StatusRequest
            context: gRPC context

        Returns:
            ServiceStatusResponse with service status information
        """
        logger.info("Received service status request")

        # Get OpenXPKI status
        status = self.openxpki_service.get_server_status()

        # Process expiring certificates to get count
        expiring_certs = self.openxpki_service.check_expiring_certificates(90)
        expiring_count = len(expiring_certs.get("expiring_certificates", []))

        # Get unique countries
        countries = set()
        for cert in expiring_certs.get("expiring_certificates", []):
            country = cert.get("country_code")
            if country:
                countries.add(country)

        # Build stats
        stats = ServiceStats(
            total_certificates=status.get("total_certificates", 0),
            trusted_countries=len(countries),
            last_sync_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            expiring_soon=expiring_count,
        )

        # Build response
        return ServiceStatusResponse(
            is_healthy=status.get("healthy", False),
            stats=stats,
            version="1.0.0",  # Replace with actual version
            openxpki_status=status.get("status", "unknown"),
        )


class TrustAnchorGrpcService(BaseGrpcService):
    """Trust Anchor gRPC service using BaseGrpcService."""

    def create_servicer(self) -> TrustAnchorService:
        """Create the TrustAnchor servicer instance."""
        return TrustAnchorService()

    def get_add_servicer_function(self) -> Callable:
        """Get the function to add the servicer to the server."""
        return add_TrustAnchorServicer_to_server


def start_server(server_port=50051, max_workers=10) -> None:
    """
    Run the gRPC server using BaseGrpcService.

    Args:
        server_port: The port to listen on
        max_workers: Maximum number of worker threads
    """
    # Create the service
    service = TrustAnchorGrpcService(
        service_name="trust-anchor", default_port=server_port, max_workers=max_workers
    )

    # Start the server
    service.start_server()


if __name__ == "__main__":
    # Get port from environment using ConfigurationManager
    config_manager = get_config_manager("trust-anchor")
    port_env = config_manager.get_env_int("GRPC_PORT", 50051)

    # Start the server
    start_server(server_port=port_env)
