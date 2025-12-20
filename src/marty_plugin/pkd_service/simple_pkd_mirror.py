"""
Simplified PKD Mirror Service

This module implements a simplified version of the PKD Mirror Service
that doesn't rely on external dependencies. It's meant for demonstration
purposes only.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from datetime import datetime, timezone

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


class SimplePKDMirrorService:
    """
    Simplified service for mirroring certificates from ICAO PKD.

    This service connects to the ICAO Public Key Directory (PKD),
    downloads certificates and certificate revocation lists (CRLs),
    and stores them locally.
    """

    def __init__(self, pkd_url, sync_interval=3600) -> None:
        """
        Initialize the PKD Mirror Service.

        Args:
            pkd_url: URL of the ICAO PKD server
            sync_interval: Interval between synchronizations (in seconds)
        """
        self.pkd_url = pkd_url.rstrip("/")  # Remove trailing slash if present
        self.sync_interval = sync_interval
        self.is_syncing = False
        self.last_sync_time = None
        self.sync_thread = None
        # Create data directory if it doesn't exist
        os.makedirs("data", exist_ok=True)

    def start_sync_scheduler(self) -> None:
        """
        Start the synchronization scheduler.

        This method starts a background thread that periodically synchronizes
        with the ICAO PKD based on the configured sync interval.
        """
        logger.info(
            f"Starting PKD mirror sync scheduler with interval {self.sync_interval} seconds"
        )

        while True:
            try:
                self.sync()
                time.sleep(self.sync_interval)
            except Exception as e:
                logger.exception(f"Error in PKD mirror sync scheduler: {e}")
                # Sleep for a shorter interval before retrying after an error
                time.sleep(min(300, self.sync_interval))  # Sleep for at most 5 minutes

    def start_sync_thread(self) -> None:
        """
        Start the synchronization in a background thread.
        """
        if self.sync_thread and self.sync_thread.is_alive():
            logger.warning("PKD mirror sync thread is already running")
            return

        self.sync_thread = threading.Thread(target=self.start_sync_scheduler, daemon=True)
        self.sync_thread.start()
        logger.info("PKD mirror sync thread started")

    def sync(self):
        """
        Synchronize with the ICAO PKD.

        Returns:
            bool: True if synchronization was successful, False otherwise
        """
        logger.info("Starting PKD mirror synchronization")
        self.is_syncing = True
        success = True

        try:
            # In a real implementation, we would connect to the actual ICAO PKD
            # For demonstration purposes, we'll simulate a successful sync

            # Download CSCA certificates (simulated)
            csca_result = self._download_and_store_certificates("CscaCertificates")
            if not csca_result:
                success = False

            # Download DSC certificates (simulated)
            dsc_result = self._download_and_store_certificates("DscCertificates")
            if not dsc_result:
                success = False

            # Download CRLs (simulated)
            crl_result = self._download_and_store_certificates("CRLs")
            if not crl_result:
                success = False

            # Update last sync time if at least one component was synced successfully
            if success:
                self.last_sync_time = datetime.now(tz=timezone.utc)
                logger.info("PKD mirror synchronization completed successfully")
            else:
                logger.warning("PKD mirror synchronization completed with errors")

        except Exception as e:
            logger.exception(f"Error during PKD mirror synchronization: {e}")
            success = False

        self.is_syncing = False
        return success

    def _download_and_store_certificates(self, endpoint) -> bool | None:
        """
        Download and store certificates from a specific endpoint.

        Args:
            endpoint: PKD endpoint to download from

        Returns:
            bool: True if download and storage were successful, False otherwise
        """
        url = f"{self.pkd_url}/{endpoint}"
        logger.info(f"Downloading from PKD endpoint: {url}")

        try:
            # In a real implementation, we would make an actual HTTP request
            # For demonstration purposes, we'll simulate a response

            # Simulate a successful response
            self._store_data(endpoint, f"Simulated {endpoint} data from {url}")
            logger.info(f"Successfully downloaded and stored {endpoint}")
        except Exception as e:
            logger.exception(f"Error downloading or storing {endpoint}: {e}")
            return False
        else:
            return True

    def _store_data(self, data_type, data) -> None:
        """
        Store data in a local file.

        Args:
            data_type: Type of data (e.g., CscaCertificates, DscCertificates, CRLs)
            data: Data to store
        """
        # Create a unique filename based on the data type and current time
        now = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"data/{data_type}_{now}.txt"

        try:
            with open(filename, "w") as f:
                f.write(data)
            logger.info(f"Data stored in {filename}")
        except Exception as e:
            logger.exception(f"Error storing data: {e}")

    def get_last_sync_time(self):
        """
        Get the time of the last successful synchronization.

        Returns:
            datetime or None: The time of the last successful sync, or None if no sync has occurred
        """
        return self.last_sync_time


def main() -> None:
    """Run the PKD Mirror Service demonstration."""
    logger.info("Starting PKD Mirror Service demonstration")

    # Create a PKD Mirror Service instance
    pkd_mirror = SimplePKDMirrorService(
        pkd_url="https://pkddownloadsg.icao.int",
        sync_interval=3600,  # 1 hour
    )

    # Print the service configuration
    logger.info(f"PKD URL: {pkd_mirror.pkd_url}")
    logger.info(f"Sync interval: {pkd_mirror.sync_interval} seconds")

    # Run a synchronization
    logger.info("Performing PKD sync (simulated for demonstration)...")
    success = pkd_mirror.sync()

    if success:
        logger.info("PKD synchronization completed successfully")
        logger.info(f"Last sync time: {pkd_mirror.get_last_sync_time()}")
    else:
        logger.error("PKD synchronization failed")


if __name__ == "__main__":
    main()
