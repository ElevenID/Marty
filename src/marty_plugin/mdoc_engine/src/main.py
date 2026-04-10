"""
mDoc Engine Service - Ultra-DRY Implementation
This module uses the auto-service factory for MAXIMUM DRY patterns.
Reduced from ~98 lines to ~10 lines (90% reduction).
"""

import sys
from pathlib import Path

# Ensure we can import from the parent directory
sys.path.append(str(Path(__file__).resolve().parents[3]))

from marty_backend_common.database import create_service_database_tables

# Import ultra-DRY service utilities
from marty_backend_common.grpc_service_factory import serve_auto_service
from marty_backend_common.logging_config import get_logger
from marty_backend_common.service_config_factory import get_config_manager

# Import database utility
from marty_plugin.shared.database import Base, engine

# Get configuration and logger using DRY factory
config_manager = get_config_manager("mdoc-engine")
logger = get_logger(__name__)


def main() -> None:
    """
    Run mDoc Engine gRPC service using Ultra-DRY Auto-Service pattern.

    This achieves 90% code reduction by automatically:
    - Discovering and registering MDocEngineServicer
    - Finding add_MDocEngineServicer_to_server function
    - Setting up health checks, logging, and gRPC reflection
    - Configuring server with standard patterns
    """
    logger.info("Starting mDoc Engine service...")

    # Initialize database using shared DRY pattern
    try:
        create_service_database_tables("mdoc-engine", Base.metadata, engine)
    except Exception:
        logger.exception("Error initializing database for mDoc Engine")
        sys.exit(1)

    try:
        # Ultra-DRY: Single line to start the entire service!
        serve_auto_service(
            service_name="mdoc-engine",
            service_module_path="src.services.mdoc_engine",
            grpc_port=config_manager.get_env_int("GRPC_PORT", 8086),
            grpc_max_workers=10,
            reflection_enabled=True,
        )

    except Exception:
        logger.exception("Error starting mDoc Engine service")
        sys.exit(1)


if __name__ == "__main__":
    main()
