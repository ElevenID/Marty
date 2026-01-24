#!/usr/bin/env python3
"""
Certificate Expiry Notification Service.

This service is responsible for:
1. Checking for certificates that are about to expire
2. Sending notifications for these certificates
3. Tracking which certificates have already been notified about
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# Import shared utilities
from marty_common.certificate import CertificateProcessor
from marty_common.service_config_factory import get_config_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class CertificateExpiryService:
    """
    Service for monitoring certificate expiry and sending notifications.

    This service periodically checks for certificates that are about to expire
    and sends notifications based on configured thresholds.
    """

    def __init__(
        self, openxpki_service, check_interval_days=1, notification_days=None, history_file=None
    ) -> None:
        """
        Initialize the Certificate Expiry Notification Service.

        Args:
            openxpki_service: The OpenXPKI service to use for certificate data
            check_interval_days: How often to check for expiring certificates (in days)
            notification_days: List of days before expiry to send notifications
            history_file: Path to the file for storing notification history
        """
        self.openxpki_service = openxpki_service
        self.check_interval_days = check_interval_days
        self.notification_days = notification_days or [30, 15, 7, 3, 1]

        # Initialize shared utilities using DRY factory
        self.config_manager = get_config_manager("trust-anchor")
        self.cert_processor = CertificateProcessor()

        # Use ConfigurationManager for path resolution
        data_dir = self.config_manager.get_env_path("DATA_DIR") or Path("data")
        default_history_path = data_dir / "trust" / "cert_notification_history.json"
        self.history_file = Path(history_file or default_history_path)

        # Ensure history file directory exists
        self.history_file.parent.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"Initialized Certificate Expiry Service with check interval of "
            f"{check_interval_days} days"
        )
        logger.info(f"Notifications will be sent at {self.notification_days} days before expiry")

    def check_for_expiring_certificates(self) -> list[dict[str, Any]]:
        """
        Check for certificates that are about to expire.

        Returns:
            List of certificate dictionaries
        """
        # Get the maximum days to check (largest notification threshold)
        max_days = max(self.notification_days) if self.notification_days else 30

        # Call the OpenXPKI service to get expiring certificates
        result = self.openxpki_service.check_expiring_certificates(days=max_days)

        # Extract the list of certificates
        certificates = result.get("expiring_certificates", [])

        logger.info(f"Found {len(certificates)} certificates expiring within {max_days} days")
        return certificates

    def filter_certificates_by_expiry(
        self, certificates: list[dict[str, Any]], days: int
    ) -> list[dict[str, Any]]:
        """
        Filter certificates to those expiring at exactly the specified days.

        Args:
            certificates: List of certificate dictionaries
            days: The exact number of days before expiry to filter for

        Returns:
            Filtered list of certificate dictionaries
        """
        filtered_certs = []
        for cert in certificates:
            # Check if the certificate expires in exactly the specified number of days
            if cert.get("days_remaining") == days:
                filtered_certs.append(cert)

        return filtered_certs

    def load_notification_history(self) -> dict[str, dict[str, Any]]:
        """
        Load the notification history from file.

        Returns:
            Dictionary mapping certificate serial numbers to notification history
        """
        try:
            if self.history_file.exists():
                content = self.history_file.read_text()
                if content:
                    return json.loads(content)

            logger.info(
                f"No notification history file found at {self.history_file} or file is empty"
            )
        except json.JSONDecodeError:
            logger.exception("Error decoding notification history JSON")
            return {}
        except Exception:
            logger.exception("Error loading notification history")
            return {}
        else:
            return {}

    def save_notification_history(self, history: dict[str, dict[str, Any]]) -> None:
        """
        Save the notification history to file.

        Args:
            history: Dictionary mapping certificate serial numbers to notification history
        """
        try:
            self.history_file.write_text(json.dumps(history, indent=2))
            logger.debug(f"Notification history saved to {self.history_file}")
        except Exception:
            logger.exception("Error saving notification history")

    def check_certificates_need_notification(
        self, certificates: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Check which certificates need notification based on their expiry and notification history.

        Args:
            certificates: List of certificate dictionaries

        Returns:
            List of certificate dictionaries that need notification, with added notification_days field
        """
        # Load notification history
        history = self.load_notification_history()

        # Certificates that need notification
        need_notification = []

        for cert in certificates:
            serial_number = cert.get("serial_number")
            days_remaining = cert.get("days_remaining")

            # Check if this certificate has a notification history
            # Type check for serial_number
            if serial_number is None:
                logger.warning("Certificate with missing serial number found")
                continue

            cert_history = history.get(serial_number, {"notify_days": []})

            # If days_remaining matches one of our notification thresholds
            # and hasn't been notified for this threshold yet
            if days_remaining in self.notification_days and days_remaining not in cert_history.get(
                "notify_days", []
            ):
                # Add the notification_days field to the certificate
                cert_copy = cert.copy()
                cert_copy["notification_days"] = days_remaining
                need_notification.append(cert_copy)

        logger.info(f"Found {len(need_notification)} certificates needing notification")
        return need_notification

    def send_notifications(self, certificates_to_notify: list[dict[str, Any]]) -> None:
        """
        Send notifications for certificates that are about to expire.

        Args:
            certificates_to_notify: List of certificate dictionaries that need notification
        """
        if not certificates_to_notify:
            logger.info("No certificates need notification at this time")
            return

        history = self.load_notification_history()

        for cert in certificates_to_notify:
            serial_number = cert.get("serial_number")
            subject = cert.get("subject", "Unknown")
            country_code = cert.get("country_code", "Unknown")
            days = cert.get("notification_days")
            expiry_date = cert.get("not_after", "Unknown")

            # Log a notification (in a real implementation, this would send an email or other alert)
            logger.warning(
                f"CERTIFICATE EXPIRY NOTIFICATION: Certificate for {country_code} "
                f"(S/N: {serial_number}) will expire in {days} days (on {expiry_date}). "
                f"Subject: {subject}"
            )

            # Update notification history
            if serial_number not in history:
                history[serial_number] = {
                    "last_notified": datetime.now().strftime("%Y-%m-%d"),
                    "notify_days": [days],
                }
            else:
                history[serial_number]["last_notified"] = datetime.now().strftime("%Y-%m-%d")
                if days not in history[serial_number]["notify_days"]:
                    history[serial_number]["notify_days"].append(days)

        # Save updated history
        self.save_notification_history(history)

    def process_expiring_certificates(self) -> None:
        """
        Process expiring certificates - main workflow that:
        1. Checks for expiring certificates
        2. Determines which ones need notification
        3. Sends notifications
        """
        logger.info("Processing expiring certificates...")

        # Get all certificates that might expire within our monitoring window
        certificates = self.check_for_expiring_certificates()

        # Check which certificates need notification
        need_notification = self.check_certificates_need_notification(certificates)

        # Send notifications
        self.send_notifications(need_notification)

        logger.info("Certificate expiry processing complete")

    def run_service(self) -> None:
        """
        Run the service in an infinite loop, checking certificates periodically.
        """
        logger.info("Starting Certificate Expiry Notification Service")

        try:
            while True:
                self.process_expiring_certificates()

                # Sleep for the check interval
                sleep_seconds = self.check_interval_days * 24 * 60 * 60
                logger.info(f"Next check in {self.check_interval_days} days")
                time.sleep(sleep_seconds)

        except KeyboardInterrupt:
            logger.info("Certificate Expiry Notification Service stopped by user")
        except Exception as e:
            logger.exception(f"Error in Certificate Expiry Notification Service: {e!s}")
