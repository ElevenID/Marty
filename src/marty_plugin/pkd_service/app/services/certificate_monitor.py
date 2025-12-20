"""
Service for monitoring certificates and providing alerts for expiring or revoked certificates
"""

import asyncio
import logging
from datetime import datetime, timedelta

from app.core.config import settings
from app.db.database import DatabaseManager
from app.models.pkd_models import CertificateStatus
from app.utils.notification import Notifier

logger = logging.getLogger(__name__)


class CertificateMonitor:
    """
    Service for monitoring certificates and providing alerts for:
    - Expiring certificates
    - Revoked certificates
    - Compromised or untrustworthy certificates
    """

    def __init__(self, notification_service: Notifier = None) -> None:
        """
        Initialize the certificate monitor

        Args:
            notification_service: Service for sending notifications
        """
        self.notification_service = notification_service or Notifier()
        self.check_interval = settings.CERT_CHECK_INTERVAL_HOURS * 3600  # Convert to seconds
        self.expiry_warning_days = settings.CERT_EXPIRY_WARNING_DAYS
        self.running = False
        self.notified_certificates = (
            set()
        )  # Track certificates that have already triggered notifications

    async def start_monitoring(self) -> None:
        """
        Start the certificate monitoring scheduler
        """
        if self.running:
            logger.warning("Certificate monitor is already running")
            return

        self.running = True
        logger.info(f"Starting certificate monitor (interval: {self.check_interval}s)")

        try:
            while self.running:
                await self.check_certificates()
                await asyncio.sleep(self.check_interval)
        except asyncio.CancelledError:
            logger.info("Certificate monitor was cancelled")
            self.running = False
        except Exception as e:
            logger.exception(f"Error in certificate monitor: {e}")
            self.running = False
            raise

    async def check_certificates(self) -> None:
        """
        Check all certificates for expiry and revocation
        """
        logger.info("Checking certificates for expiry and revocation")

        try:
            # Get all certificates from the database
            cert_dicts = await DatabaseManager.get_certificates(cert_type="CSCA")

            # Check for expiring certificates
            await self._check_expiring_certificates(cert_dicts)

            # Check for revoked certificates
            await self._check_revoked_certificates(cert_dicts)

            # Reset notification tracking for certificates no longer of concern
            self._cleanup_notification_tracking(cert_dicts)

            logger.info("Certificate check completed successfully")

        except Exception as e:
            logger.exception(f"Error checking certificates: {e}")
            raise

    async def _check_expiring_certificates(self, cert_dicts: list[dict]) -> None:
        """
        Check for certificates that are about to expire

        Args:
            cert_dicts: List of certificate dictionaries from the database
        """
        now = datetime.now()
        warning_date = now + timedelta(days=self.expiry_warning_days)

        for cert_dict in cert_dicts:
            try:
                cert_id = cert_dict.get("id")
                valid_to = cert_dict.get("valid_to")
                status = cert_dict.get("status")

                # Skip inactive certificates
                if status != CertificateStatus.ACTIVE:
                    continue

                # Check if certificate is expiring
                if valid_to and valid_to < warning_date:
                    # Calculate days until expiry
                    days_until_expiry = (valid_to - now).days

                    if days_until_expiry < 0:
                        # Certificate has already expired
                        logger.warning(f"Certificate {cert_id} has expired on {valid_to}")

                        # Update status in database if it's still marked as active
                        if status == CertificateStatus.ACTIVE:
                            await DatabaseManager.update_certificate_status(
                                cert_id, CertificateStatus.EXPIRED
                            )

                        # Send notification if we haven't already
                        notification_key = f"expired:{cert_id}"
                        if notification_key not in self.notified_certificates:
                            subject = f"Certificate Expired: {cert_dict.get('subject')}"
                            message = f"Certificate with ID {cert_id} has expired on {valid_to}."
                            await self._send_notification(subject, message)
                            self.notified_certificates.add(notification_key)

                    elif days_until_expiry <= self.expiry_warning_days:
                        # Certificate is about to expire
                        logger.warning(
                            f"Certificate {cert_id} will expire in {days_until_expiry} days"
                        )

                        # Send notification if we haven't already for this threshold
                        # Use thresholds at 30, 14, 7, 3, 1 days
                        thresholds = [30, 14, 7, 3, 1]
                        for threshold in thresholds:
                            if days_until_expiry <= threshold:
                                notification_key = f"expiring:{cert_id}:{threshold}"
                                if notification_key not in self.notified_certificates:
                                    subject = (
                                        f"Certificate Expiring Soon: {cert_dict.get('subject')}"
                                    )
                                    message = (
                                        f"Certificate with ID {cert_id} will expire in {days_until_expiry} days "
                                        f"(on {valid_to}). Please plan for certificate renewal."
                                    )
                                    await self._send_notification(subject, message)
                                    self.notified_certificates.add(notification_key)
                                break  # Only notify for the closest threshold

            except Exception as e:
                logger.exception(
                    f"Error checking certificate {cert_dict.get('id')} for expiry: {e}"
                )

    async def _check_revoked_certificates(self, cert_dicts: list[dict]) -> None:
        """
        Check for certificates that have been revoked via CRLs or other mechanisms

        Args:
            cert_dicts: List of certificate dictionaries from the database
        """
        # In a real implementation, this would check Certificate Revocation Lists (CRLs)
        # and Online Certificate Status Protocol (OCSP) responders

        # For CSCA certificates, CRLs are the primary mechanism for revocation
        # This implementation would:
        # 1. Download and parse CRLs from trusted sources
        # 2. Check certificates against the CRLs
        # 3. Mark revoked certificates and send notifications

        # For now, we just log a placeholder message
        logger.info("Checking for revoked certificates (placeholder implementation)")

        # Example of what the real implementation would do:
        for cert_dict in cert_dicts:
            cert_id = cert_dict.get("id")

            # Skip non-active certificates
            if cert_dict.get("status") != CertificateStatus.ACTIVE:
                continue

            # In a real implementation, we would check if the certificate is in a CRL
            is_revoked = await self._check_certificate_in_crl(cert_dict)

            if is_revoked:
                logger.warning(f"Certificate {cert_id} has been revoked")

                # Update status in database
                await DatabaseManager.update_certificate_status(cert_id, CertificateStatus.REVOKED)

                # Send notification
                notification_key = f"revoked:{cert_id}"
                if notification_key not in self.notified_certificates:
                    subject = f"Certificate Revoked: {cert_dict.get('subject')}"
                    message = f"Certificate with ID {cert_id} has been revoked."
                    await self._send_notification(subject, message)
                    self.notified_certificates.add(notification_key)

    async def _check_certificate_in_crl(self, cert_dict: dict) -> bool:
        """
        Check if a certificate is in a Certificate Revocation List (CRL)

        Args:
            cert_dict: Certificate dictionary

        Returns:
            True if the certificate is revoked, False otherwise
        """
        # This is a placeholder implementation
        # In a real implementation, this would:
        # 1. Download CRLs from trusted sources
        # 2. Parse the CRLs using cryptographic libraries
        # 3. Check if the certificate's serial number is in the CRL

        # For demonstration purposes, we return False (not revoked)
        return False

    def _cleanup_notification_tracking(self, cert_dicts: list[dict]) -> None:
        """
        Clean up the notification tracking set by removing entries for certificates
        that no longer need to be tracked

        Args:
            cert_dicts: List of certificate dictionaries from the database
        """
        # Get all certificate IDs
        cert_ids = {cert_dict.get("id") for cert_dict in cert_dicts}

        # Create a set of notification keys to keep
        keys_to_keep = set()
        for cert_id in cert_ids:
            # Keep all notification keys for existing certificates
            for key in self.notified_certificates:
                if f":{cert_id}" in key or key.startswith(f"{cert_id}:"):
                    keys_to_keep.add(key)

        # Update the notified_certificates set
        self.notified_certificates = keys_to_keep

    async def _send_notification(self, subject: str, message: str) -> None:
        """
        Send a notification using the notification service

        Args:
            subject: Notification subject
            message: Notification message
        """
        try:
            if self.notification_service:
                await self.notification_service.send_notification(subject, message)
            else:
                logger.warning(
                    f"No notification service configured. Would send: {subject}: {message}"
                )

        except Exception as e:
            logger.exception(f"Error sending notification: {e}")
