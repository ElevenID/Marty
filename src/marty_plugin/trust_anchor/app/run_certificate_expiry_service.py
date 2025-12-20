#!/usr/bin/env python3
"""
Demo script to run the Certificate Expiry Notification Service.

This script demonstrates how to use the CertificateExpiryService
to monitor certificate expiration and send notifications.

Usage:
    python run_certificate_expiry_service.py

Environment Variables:
    CHECK_INTERVAL_DAYS: How often to check certificates (in days)
    NOTIFICATION_DAYS: Comma-separated list of days before expiry to send notifications
    HISTORY_FILE: Path to the notification history file

    Plus all environment variables required by OpenXPKIService.
"""

import logging
import os
import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).resolve().parents[3]
sys.path.append(str(project_root))

# Import required services
from marty_plugin.trust_anchor.app.services.certificate_expiry_service import CertificateExpiryService
from marty_plugin.trust_anchor.app.services.openxpki_service import OpenXPKIService

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main() -> int:
    """Run the Certificate Expiry Notification Service."""
    logger.info("Starting Certificate Expiry Notification Service Demo")

    try:
        # Get configuration from environment variables
        check_interval_days = int(os.environ.get("CHECK_INTERVAL_DAYS", "1"))

        notification_days_str = os.environ.get("NOTIFICATION_DAYS", "30,15,7,5,3,1")
        notification_days = [int(days) for days in notification_days_str.split(",")]

        history_file = os.environ.get("HISTORY_FILE")

        # Create OpenXPKI service instance
        openxpki_service = OpenXPKIService()

        # Create and run the Certificate Expiry Notification Service
        service = CertificateExpiryService(
            openxpki_service=openxpki_service,
            check_interval_days=check_interval_days,
            notification_days=notification_days,
            history_file=history_file,
        )

        logger.info("Running certificate expiry check once...")
        # Process expiring certificates once
        service.process_expiring_certificates()

        # If you want to run the service continuously, uncomment the following:
        # service.run_service()

        logger.info("Demo completed successfully")

    except KeyboardInterrupt:
        logger.info("Service stopped by user")
    except Exception:
        logger.exception("Error running Certificate Expiry Notification Service")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
