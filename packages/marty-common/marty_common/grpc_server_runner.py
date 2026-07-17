"""
Generic service runner using shared gRPC server utilities.

This module provides a standardized way to run any Marty service
using the shared gRPC server framework.
"""

import os
import sys
from importlib import import_module

from marty_common.config_manager import get_service_config, validate_service_config
from marty_common.grpc_server import create_standard_server


def main() -> None:
    """Run a Marty service based on environment configuration."""
    service_name = os.environ.get("SERVICE_NAME")
    if not service_name:
        print("ERROR: SERVICE_NAME environment variable is required", file=sys.stderr)
        sys.exit(1)

    try:
        # Load service configuration
        config = get_service_config(service_name)
        validate_service_config(config)

        # Import service-specific modules dynamically
        service_module = import_module(f"src.services.{service_name}")
        servicer_class = getattr(service_module, f"{service_name.title().replace('_', '')}Servicer")

        # Import the protobuf add_servicer function
        proto_module = import_module(f"src.proto.{service_name}_pb2_grpc")
        add_servicer_func = getattr(proto_module, f"add_{servicer_class.__name__}_to_server")

        # Create and run the server
        server = create_standard_server(
            service_name=service_name,
            servicer_class=servicer_class,
            add_servicer_func=add_servicer_func,
            port=config.grpc_port,
            max_workers=config.grpc_max_workers,
            enable_health_check=config.grpc_enable_health_check,
            enable_logging_streamer=config.grpc_enable_logging_streamer,
        )

        server.serve()

    except Exception as e:
        print(f"ERROR: Failed to start {service_name} service: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
