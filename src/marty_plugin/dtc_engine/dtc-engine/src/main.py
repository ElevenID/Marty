import logging
import sys
from collections.abc import Callable
from pathlib import Path

# Add the parent directory to sys.path
sys.path.append(str(Path(__file__).resolve().parents[3]))

# Import DTC engine servicer
from dtc_engine_service import DTCEngineService

from marty_plugin.common.config import Config
from marty_plugin.common.service_config_factory import get_config_manager

# Import shared utilities
from marty_plugin.common.services import BaseGrpcService
from marty_plugin.proto.v1 import dtc_engine_pb2_grpc


class DTCGrpcService(BaseGrpcService):
    """DTC Engine gRPC service using BaseGrpcService."""

    def __init__(self, config) -> None:
        """Initialize with config."""
        self.config = config
        super().__init__(service_name="dtc-engine", default_port=8087, max_workers=10)

    def create_servicer(self) -> DTCEngineService:
        """Create the DTC Engine servicer instance."""
        return DTCEngineService(self.config)

    def get_add_servicer_function(self) -> Callable:
        """Get the function to add the servicer to the server."""
        return dtc_engine_pb2_grpc.add_DTCEngineServicer_to_server


def serve() -> None:
    """Start the gRPC server using BaseGrpcService."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Initialize configuration manager using DRY factory
    config_manager = get_config_manager("dtc-engine")
    port = config_manager.get_env_int("GRPC_PORT", 8087)

    # Load configuration
    config_env = config_manager.get_env_list("ENV", default=["development"])[0]
    config = Config(config_env)

    # Create the service
    service = DTCGrpcService(config)
    service.grpc_port = port

    # Start the server
    service.start_server()


if __name__ == "__main__":
    serve()
