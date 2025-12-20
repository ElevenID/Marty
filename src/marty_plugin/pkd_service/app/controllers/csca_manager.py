"""
Controller for managing CSCA and Master List operations
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from datetime import datetime
from typing import Any

from app.core.config import settings
from app.models.pkd_models import (
    Certificate,
    CertificateStatus,
    MasterListResponse,
    VerificationResult,
)
from app.services.certificate_monitor import CertificateMonitor
from app.services.masterlist_service import MasterListService
from app.services.masterlist_sync_service import MasterListSyncService
from app.services.offline_verifier import OfflineVerifier
from app.services.openxpki_service import OpenXPKIService
from app.utils.notification import Notifier

logger = logging.getLogger(__name__)


class CscaManager:
    """
    Controller for managing CSCA and Master List operations.

    This class integrates all the components of the CSCA & Master List Management:
    - OpenXPKI service for certificate storage and lifecycle management
    - Master List Service for format conversion and processing
    - Synchronization service for auto-updating from trusted sources
    - Certificate monitor for detecting expiring or revoked certificates
    """

    def __init__(self) -> None:
        """Initialize the CSCA Manager"""
        # Create component services
        self.openxpki_service = OpenXPKIService()
        self.master_list_service = MasterListService()
        self.notifier = Notifier()
        self.sync_service = MasterListSyncService(self.master_list_service)
        self.certificate_monitor = CertificateMonitor(self.notifier)
        self.offline_verifier = OfflineVerifier()

        # Background tasks
        self.tasks = []

        # Initialize directories
        self._ensure_directories_exist()

    async def start_services(self) -> None:
        """Start all CSCA management services"""
        logger.info("Starting CSCA Manager services")

        # Check OpenXPKI health
        try:
            is_healthy = await self.openxpki_service.health_check()
            if not is_healthy:
                logger.warning(
                    "OpenXPKI service is not healthy, services may not operate correctly"
                )
        except Exception as e:
            logger.exception(f"Error checking OpenXPKI health: {e}")

        # Start sync scheduler as background task
        sync_task = asyncio.create_task(self.sync_service.start_sync_scheduler())
        self.tasks.append(sync_task)

        # Start certificate monitor as background task
        monitor_task = asyncio.create_task(self.certificate_monitor.start_monitoring())
        self.tasks.append(monitor_task)

        # Start OpenXPKI to local sync if enabled
        if getattr(settings, "OPENXPKI", {}).get("sync_to_local", False):
            openxpki_sync_task = asyncio.create_task(self._schedule_openxpki_sync())
            self.tasks.append(openxpki_sync_task)

        logger.info("CSCA Manager services started successfully")

    async def stop_services(self) -> None:
        """Stop all CSCA management services"""
        logger.info("Stopping CSCA Manager services")

        # Cancel all background tasks
        for task in self.tasks:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        self.tasks.clear()
        logger.info("CSCA Manager services stopped")

    async def get_master_list(self, country: str | None = None) -> MasterListResponse:
        """
        Get the CSCA Master List, optionally filtered by country

        Args:
            country: Optional country filter

        Returns:
            MasterListResponse object containing certificates
        """
        try:
            # Get certificates from OpenXPKI
            certificates_data = await self.openxpki_service.get_certificates(
                cert_type="CSCA", country=country
            )

            # Convert to our model format
            certificates = []
            for cert_data in certificates_data:
                cert = Certificate(
                    id=cert_data.get("id"),
                    subject=cert_data.get("subject"),
                    issuer=cert_data.get("issuer"),
                    valid_from=datetime.fromisoformat(cert_data.get("valid_from")),
                    valid_to=datetime.fromisoformat(cert_data.get("valid_to")),
                    serial_number=cert_data.get("serial_number"),
                    certificate_data=cert_data.get("certificate_data", b""),
                    status=CertificateStatus(cert_data.get("status", "ACTIVE")),
                    country_code=cert_data.get("country_code"),
                )
                certificates.append(cert)

            # Get list of unique countries from certificates
            countries = list({cert.country_code for cert in certificates})

            return MasterListResponse(
                id=str(datetime.now().timestamp()),
                version=1,
                created=datetime.now(),
                countries=countries,
                certificates=certificates,
            )

        except Exception as e:
            logger.exception(f"Error getting master list from OpenXPKI: {e}")
            # Fall back to local master list service
            return await self.master_list_service.get_master_list(country)

    async def get_master_list_binary(self, country: str | None = None) -> bytes:
        """
        Get the ASN.1 encoded master list, optionally filtered by country

        Args:
            country: Optional country filter

        Returns:
            ASN.1 encoded master list
        """
        # Get certificates in our model format
        await self.get_master_list(country)

        # Use the master list service to encode as ASN.1
        return await self.master_list_service.get_master_list_binary(country)

    async def upload_master_list(self, master_list_data: bytes):
        """
        Upload and process a master list

        Args:
            master_list_data: ASN.1 encoded master list

        Returns:
            Upload response with status
        """
        try:
            # Import into OpenXPKI first
            openxpki_response = await self.openxpki_service.import_master_list(master_list_data)
            logger.info(f"Master list imported into OpenXPKI: {openxpki_response}")

            # Then also process with our local service for backup
            response = await self.master_list_service.upload_master_list(master_list_data)

            # Rebuild trust store
            await self.openxpki_service.build_trust_store()

        except Exception as e:
            logger.exception(f"Error uploading master list to OpenXPKI: {e}")
            # Fall back to local master list service
            return await self.master_list_service.upload_master_list(master_list_data)
        else:
            return response

    async def trigger_sync(self, source_id: str | None = None) -> dict[str, Any]:
        """
        Trigger synchronization with trusted sources

        Args:
            source_id: Optional specific source to sync with

        Returns:
            Dictionary with sync results
        """
        logger.info(
            f"Triggering synchronization with {'all sources' if source_id is None else source_id}"
        )

        try:
            if source_id:
                # Get the specific source config
                source_config = self.sync_service.sources_config.get(source_id)
                if not source_config:
                    return {
                        "status": "error",
                        "message": f"Source '{source_id}' not found in configuration",
                        "timestamp": str(datetime.now()),
                    }

                # Sync with the specific source
                await self.sync_service.sync_with_source(source_id, source_config)
            else:
                # Sync with all sources
                await self.sync_service.sync_all_sources()

            # Sync with OpenXPKI
            await self._sync_from_openxpki()

            return {
                "status": "success",
                "message": "Synchronization completed successfully",
                "timestamp": str(datetime.now()),
            }

        except Exception as e:
            logger.exception(f"Error triggering synchronization: {e}")
            return {
                "status": "error",
                "message": f"Synchronization failed: {e!s}",
                "timestamp": str(datetime.now()),
            }

    async def verify_certificate(self, certificate_data: bytes) -> VerificationResult:
        """
        Verify a certificate against the trust store

        Args:
            certificate_data: Raw certificate data

        Returns:
            VerificationResult with status and details
        """
        try:
            # Use OpenXPKI for verification
            result = await self.openxpki_service.verify_certificate(certificate_data)

            # Convert to our model format
            return VerificationResult(
                is_valid=result.get("is_valid", False),
                status=result.get("status", "UNKNOWN"),
                details=result.get("details", ""),
            )

        except Exception as e:
            logger.exception(f"Error verifying certificate with OpenXPKI: {e}")
            # Fall back to offline verifier
            return await self.offline_verifier.verify_certificate(certificate_data)

    async def check_for_expiring_certificates(self) -> dict[str, Any]:
        """
        Check for certificates that are expiring soon

        Returns:
            Dictionary with check results
        """
        try:
            # Get expiring certificates from OpenXPKI
            expiring_certs = await self.openxpki_service.get_expiring_certificates(
                days_threshold=settings.CERT_EXPIRY_WARNING_DAYS
            )

            logger.info(f"Found {len(expiring_certs)} expiring certificates")

            # Send notifications for each expiring certificate
            for cert in expiring_certs:
                subject = cert.get("subject", "Unknown")
                cert_id = cert.get("id", "Unknown")
                valid_to = cert.get("valid_to", "Unknown")
                days_left = cert.get("days_until_expiry", 0)

                await self.notifier.send_expiry_notification(
                    cert_id=cert_id, subject=subject, expiry_date=valid_to, days_left=days_left
                )

            return {
                "status": "success",
                "message": f"Certificate expiry check completed. Found {len(expiring_certs)} expiring certificates.",
                "expiring_count": len(expiring_certs),
                "timestamp": str(datetime.now()),
            }

        except Exception as e:
            logger.exception(f"Error checking for expiring certificates with OpenXPKI: {e}")
            # Fall back to local certificate monitor
            await self.certificate_monitor.check_certificates()
            return {
                "status": "success",
                "message": "Certificate expiry check completed using local monitor",
                "timestamp": str(datetime.now()),
            }

    async def _schedule_openxpki_sync(self) -> None:
        """
        Schedule regular synchronization with OpenXPKI
        """
        sync_interval = (
            getattr(settings, "OPENXPKI", {}).get("trust_sync_interval_hours", 6) * 3600
        )  # Convert to seconds

        try:
            while True:
                await self._sync_from_openxpki()
                await asyncio.sleep(sync_interval)
        except asyncio.CancelledError:
            logger.info("OpenXPKI sync task cancelled")
        except Exception as e:
            logger.exception(f"Error in OpenXPKI sync task: {e}")
            raise

    async def _sync_from_openxpki(self) -> int:
        """
        Synchronize certificates from OpenXPKI to local storage

        Returns:
            Number of certificates synchronized
        """
        try:
            logger.info("Synchronizing certificates from OpenXPKI to local storage")

            # Get certificates from OpenXPKI
            certificates = await self.openxpki_service.get_certificates()

            # Ensure the local store directory exists
            local_store_path = getattr(settings, "OPENXPKI", {}).get(
                "local_store_path", "data/trust/openxpki_sync"
            )
            os.makedirs(local_store_path, exist_ok=True)

            # Save each certificate to the local store
            count = 0
            for cert in certificates:
                try:
                    cert_id = cert.get("id")
                    cert_data = cert.get("certificate_data")
                    country = cert.get("country_code", "XX")

                    if not cert_data:
                        logger.warning(f"No certificate data for {cert_id}")
                        continue

                    # Write certificate to local store
                    cert_path = os.path.join(local_store_path, f"{country}_{cert_id}.cer")
                    with open(cert_path, "wb") as f:
                        f.write(cert_data)

                    count += 1

                except Exception as e:
                    logger.exception(f"Error exporting certificate {cert.get('id')}: {e}")

            logger.info(f"Synchronized {count} certificates from OpenXPKI")

        except Exception as e:
            logger.exception(f"Error synchronizing from OpenXPKI: {e}")
            return 0
        else:
            return count

    def _ensure_directories_exist(self) -> None:
        """Ensure all required directories exist"""
        os.makedirs(settings.LOCAL_TRUST_STORE_PATH, exist_ok=True)
        os.makedirs(settings.LOCAL_CRL_PATH, exist_ok=True)

        # Directory for storing uploaded master lists
        os.makedirs(settings.MASTERLIST_PATH, exist_ok=True)

        # Directory for OpenXPKI sync
        openxpki_sync_path = getattr(settings, "OPENXPKI", {}).get(
            "local_store_path", "data/trust/openxpki_sync"
        )
        os.makedirs(openxpki_sync_path, exist_ok=True)
