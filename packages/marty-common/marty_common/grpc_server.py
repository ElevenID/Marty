"""
Shared gRPC server utilities for Marty services.

This module provides a standardized way to create and configure gRPC servers,
reducing duplication across all services.
"""

from __future__ import annotations

import logging
import os
import signal
from collections.abc import Callable
from concurrent import futures
from types import FrameType
from typing import Any, Protocol

import grpc
from grpc_health.v1 import health_pb2_grpc
from grpc_health.v1.health import HealthServicer

from marty_common.grpc_logging import LoggingStreamerServicer
from marty_common.logging_config import setup_logging
from marty_plugin.proto.v1 import common_services_pb2_grpc

logger = logging.getLogger(__name__)


class ServerNotInitializedError(RuntimeError):
    """Raised when server operations are attempted before initialization."""

    def __init__(self) -> None:
        super().__init__("Server not initialized. Call setup() first.")


class ServiceProtocol(Protocol):
    """Protocol for gRPC service classes."""

    def add_to_server(self, server: grpc.Server) -> None:
        """Add the service to a gRPC server."""
        ...


class GrpcServerConfig:
    """Configuration for gRPC server setup."""

    def __init__(
        self,
        service_name: str,
        port: int | None = None,
        max_workers: int = 10,
        enable_logging_streamer: bool = True,
        enable_health_check: bool = True,
        wait_for_dependencies: bool = False,
        dependency_check_timeout: int = 30,
        graceful_shutdown_timeout: int = 10,
    ) -> None:
        self.service_name = service_name
        self.port = port or int(os.environ.get("GRPC_PORT", "50051"))
        self.max_workers = max_workers
        self.enable_logging_streamer = enable_logging_streamer
        self.enable_health_check = enable_health_check
        self.wait_for_dependencies = wait_for_dependencies
        self.dependency_check_timeout = dependency_check_timeout
        self.graceful_shutdown_timeout = graceful_shutdown_timeout


class MartyGrpcServer:
    """Standardized gRPC server for Marty services."""

    def __init__(self, config: GrpcServerConfig) -> None:
        self.config = config
        self.server: grpc.Server | None = None
        self.health_servicer: HealthServicer | None = None
        self._services: list[ServiceProtocol] = []
        self._shutdown_requested = False

    def add_service(self, service: ServiceProtocol) -> None:
        """Add a service to the server."""
        self._services.append(service)

    def add_servicer_to_server(
        self, servicer: object, add_servicer_func: Callable[[object, grpc.Server], None]
    ) -> None:
        """Add a servicer using the generated add_servicer_to_server function."""
        if self.server is None:
            raise ServerNotInitializedError

        add_servicer_func(servicer, self.server)
        logger.info(f"Added {servicer.__class__.__name__} to gRPC server")

    def setup(self) -> None:
        """Set up the gRPC server with all configured services."""
        # Setup logging first
        setup_logging(service_name=self.config.service_name)
        logger.info(f"Starting {self.config.service_name} gRPC server...")

        # Create server
        self.server = grpc.server(futures.ThreadPoolExecutor(max_workers=self.config.max_workers))

        # Add health check service
        if self.config.enable_health_check:
            self.health_servicer = HealthServicer()
            health_pb2_grpc.add_HealthServicer_to_server(self.health_servicer, self.server)
            logger.info("Added HealthServicer to gRPC server")

        # Add logging streamer service
        if self.config.enable_logging_streamer:
            try:
                logging_streamer_servicer = LoggingStreamerServicer()
                common_services_pb2_grpc.add_LoggingStreamerServicer_to_server(
                    logging_streamer_servicer, self.server
                )
                logger.info("Successfully added LoggingStreamerServicer to gRPC server")
            except Exception as e:
                logger.error(f"Failed to add LoggingStreamerServicer: {e}", exc_info=True)

        # Add all registered services
        for service in self._services:
            service.add_to_server(self.server)

        # Configure server port
        self.server.add_insecure_port(f"[::]:{self.config.port}")

    def start(self) -> None:
        """Start the gRPC server."""
        if self.server is None:
            raise ServerNotInitializedError

        self.server.start()
        logger.info(
            f"{self.config.service_name} server started successfully on port {self.config.port}"
        )

        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def serve(self) -> None:
        """Start the server and wait for termination."""
        self.setup()
        self.start()

        try:
            self.server.wait_for_termination()
        except KeyboardInterrupt:
            logger.info("Shutting down server due to KeyboardInterrupt...")
        except Exception as e:
            logger.error(f"Server termination error: {e}", exc_info=True)
        finally:
            self._shutdown()

    def _signal_handler(self, signum: int, frame: FrameType | None) -> None:
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self._shutdown_requested = True
        if self.server:
            self.server.stop(self.config.graceful_shutdown_timeout)

    def _shutdown(self) -> None:
        """Perform graceful shutdown."""
        logger.info("Stopping gRPC server...")
        if self.server:
            self.server.stop(0)
        logger.info(f"{self.config.service_name} server shut down")


def create_standard_server(
    service_name: str,
    servicer_class: type,
    add_servicer_func: Callable[[object, grpc.Server], None],
    servicer_kwargs: dict[str, Any] | None = None,
    **config_kwargs: Any,
) -> MartyGrpcServer:
    """
    Create a standard gRPC server with minimal configuration.

    Args:
        service_name: Name of the service
        servicer_class: Class of the main servicer
        add_servicer_func: Function to add servicer to server
        servicer_kwargs: Keyword arguments for servicer initialization
        **config_kwargs: Additional configuration for GrpcServerConfig

    Returns:
        Configured MartyGrpcServer instance
    """
    config = GrpcServerConfig(service_name=service_name, **config_kwargs)
    server = MartyGrpcServer(config)

    # Create and add the main servicer
    servicer_kwargs = servicer_kwargs or {}
    servicer = servicer_class(**servicer_kwargs)
    server.add_servicer_to_server(servicer, add_servicer_func)

    return server


# Utility function for simple service main() functions
def run_grpc_service(
    service_name: str,
    servicer_class: type,
    add_servicer_func: Callable[[object, grpc.Server], None],
    servicer_kwargs: dict[str, Any] | None = None,
    **config_kwargs: Any,
) -> None:
    """
    Run a gRPC service with standard configuration.
    This is a convenience function for simple service entry points.
    """
    server = create_standard_server(
        service_name=service_name,
        servicer_class=servicer_class,
        add_servicer_func=add_servicer_func,
        servicer_kwargs=servicer_kwargs,
        **config_kwargs,
    )
    server.serve()
