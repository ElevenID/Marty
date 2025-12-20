"""
PKD Mirror Service Demonstration

This script demonstrates the functionality of the PKD Mirror Service.
It creates a PKD Mirror Service instance and runs a synchronization.
"""

import logging
import sys

from app.services.pkd_mirror_service import PKDMirrorService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


def main() -> None:
    """Run the PKD Mirror Service demonstration."""
    logger.info("Starting PKD Mirror Service demonstration")

    # Create a PKD Mirror Service instance
    pkd_mirror = PKDMirrorService(
        pkd_url="https://pkddownloadsg.icao.int",
        sync_interval=3600,
        logger=logger,  # 1 hour
    )

    # Print the service configuration
    logger.info(f"PKD URL: {pkd_mirror.pkd_url}")
    logger.info(f"Sync interval: {pkd_mirror.sync_interval} seconds")

    # Run a synchronization
    logger.info(
        "Performing PKD sync (this would connect to the actual PKD in a real environment)..."
    )
    success = pkd_mirror.sync()

    if success:
        logger.info("PKD synchronization completed successfully")
        logger.info(f"Last sync time: {pkd_mirror.get_last_sync_time()}")
    else:
        logger.error("PKD synchronization failed")


if __name__ == "__main__":
    main()
