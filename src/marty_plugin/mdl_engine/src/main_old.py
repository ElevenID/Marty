"""
MDL Engine Service - Ultra-DRY Implementation
This module uses the auto-service factory for MAXIMUM DRY patterns.
Reduced from ~68 lines to ~10 lines (85% reduction).
"""

import sys
from pathlib import Path

# Ensure we can import from the parent directory
sys.path.append(str(Path(__file__).resolve().parents[3]))

# Import ultra-DRY auto-service utilities
from marty_plugin.common.config import ConfigurationManager
from marty_plugin.common.database import create_service_database_tables
from marty_plugin.common.grpc_service_factory import serve_auto_service
from marty_plugin.common.logging_config import get_logger

# Import database utility
from marty_plugin.shared.database import Base, engine

# Get configuration and logger
config_manager = ConfigurationManager()
logger = get_logger(__name__)


def main() -> None:
    """
    Run MDL Engine gRPC service using Ultra-DRY Auto-Service pattern.

    This achieves 85% code reduction by automatically:
    - Discovering and registering MDLEngineServicer
    - Finding add_MDLEngineServicer_to_server function
    - Setting up health checks, logging, and gRPC reflection
    - Configuring server with standard patterns
    """
    logger.info("Starting MDL Engine service...")

    # Initialize database using shared DRY pattern
    try:
        create_service_database_tables("mdl-engine", Base.metadata, engine)
    except Exception:
        logger.exception("Error initializing database for MDL Engine")
        sys.exit(1)

    try:
        # Ultra-DRY: Single line to start the entire service!
        serve_auto_service(
            service_name="mdl-engine",
            service_module_path="src.services.mdl_engine",
            grpc_port=config_manager.get_env_int("GRPC_PORT", 8085),
            grpc_max_workers=10,
            reflection_enabled=True,
        )

    except Exception:
        logger.exception("Error starting MDL Engine service")
        sys.exit(1)


if __name__ == "__main__":
    main()

import sys
from pathlib import Path

# Ensure we can import from the parent directory
sys.path.append(str(Path(__file__).resolve().parents[3]))

from marty_plugin.common.config import ConfigurationManager

# Import ultra-DRY auto-service utilities
from marty_plugin.common.logging_config import get_logger

# Import database utility

# Get configuration and logger
config_manager = ConfigurationManager()
logger = get_logger(__name__)


def main() -> None:
    """
    Run MDL Engine gRPC service using Ultra-DRY Auto-Service pattern.

    This achieves 85% code reduction by automatically:
    - Discovering and registering MDLEngineServicer
    - Finding add_MDLEngineServicer_to_server function
    - Setting up health checks, logging, and gRPC reflection
    - Configuring server with standard patterns
    """
    logger.info("Starting MDL Engine service...")

    # Initialize database using shared DRY pattern
    try:
        create_service_database_tables("mdl-engine", Base.metadata, engine)
    except Exception:
        logger.exception("Error initializing database for MDL Engine")
        sys.exit(1)

    try:
        # Ultra-DRY: Single line to start the entire service!
        serve_auto_service(
            service_name="mdl-engine",
            service_module_path="src.services.mdl_engine",
            grpc_port=config_manager.get_env_int("GRPC_PORT", 8085),
            grpc_max_workers=10,
            reflection_enabled=True,
        )

    except Exception:
        logger.exception("Error starting MDL Engine service")
        sys.exit(1)


if __name__ == "__main__":
    main()

import sys
import time
from pathlib import Path

# Ensure we can import from the parent directory
sys.path.append(str(Path(__file__).resolve().parents[3]))

# Import DRY utilities
from marty_plugin.common.config import ConfigurationManager
from marty_plugin.common.grpc_service_factory import create_grpc_service_factory
from marty_plugin.common.logging_config import get_logger

# Import the MDL Engine service implementation
from marty_plugin.proto.mdl_engine_pb2_grpc import add_MDLEngineServicer_to_server
from marty_plugin.lib.mdl_engine import MDLEngineServicer

# Import database utility

# Get configuration and logger
config_manager = ConfigurationManager()
logger = get_logger(__name__)


def main() -> None:
    """
    Run MDL Engine gRPC service using DRY Service Factory pattern.

    This replaces ~50 lines of boilerplate with ~8 lines while providing:
    - Automatic health checks and reflection
    - Built-in logging streamer
    - Signal handling and graceful shutdown
    - Consistent configuration patterns
    """
    logger.info("Starting MDL Engine service...")

    # Initialize database using shared DRY pattern
    try:
        create_service_database_tables("mdl-engine", Base.metadata, engine)
    except Exception:
        logger.exception("Error initializing database for MDL Engine")
        sys.exit(1)

    # Wait for dependencies if specified
    wait_for_deps = config_manager.get_env_bool("WAIT_FOR_DEPENDENCIES", False)
    if wait_for_deps:
        wait_time = config_manager.get_env_int("DEPENDENCY_WAIT_TIME", 5)
        logger.info(f"Waiting for dependencies for {wait_time} seconds...")
        time.sleep(wait_time)

    try:
        # Create factory with DRY configuration
        factory = create_grpc_service_factory(
            service_name="mdl-engine",
            config_type="grpc",
            grpc_port=config_manager.get_env_int("GRPC_PORT", 8085),
            grpc_max_workers=10,
            reflection_enabled=True,
        )

        # Register the MDL Engine service
        # Note: MDLEngineServicer requires dependencies parameter
        factory.register_service(
            name="mdl_engine",
            servicer_factory=lambda dependencies=None, **_: MDLEngineServicer(
                channels={}, dependencies=dependencies
            ),
            registration_func=add_MDLEngineServicer_to_server,
            health_service_name="mdl.MDLEngine",
        )

        # Start the server with all DRY patterns
        factory.serve()

    except Exception:
        logger.exception("Error starting MDL Engine service")
        sys.exit(1)


if __name__ == "__main__":
    main()
