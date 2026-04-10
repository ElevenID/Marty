"""
Base gRPC service class providing common patterns for all gRPC services.

This module consolidates duplicate gRPC server setup, lifecycle management,
and error handling patterns across all services.
"""

from __future__ import annotations

import os
import signal
import sys
from abc import ABC, abstractmethod
from concurrent import futures
from typing import Any, Protocol

import grpc
from grpc_health.v1 import health_pb2_grpc
from grpc_health.v1.health import HealthServicer

from marty_plugin.common.grpc_logging import LoggingStreamerServicer
from marty_plugin.common.grpc_server import GrpcServerConfig
from marty_plugin.common.logging import ServiceLogger, configure_service_logging
from marty_plugin.common.services import BaseService
from marty_plugin.proto.v1 import common_services_pb2_grpc


class ServicerProtocol(Protocol):
    """Protocol for gRPC servicer classes."""

    def add_to_server(self, server: grpc.Server) -> None:
        """Add the servicer to a gRPC server."""


class BaseGrpcService(BaseService, ABC):
    """
    Base class for gRPC services providing common patterns.

    Features:
    - Standardized server setup and configuration
    - Consistent logging patterns
    - Common error handling
    - Health check integration
    - Graceful shutdown handling
    - Service lifecycle management
    """

    def __init__(
        self,
        service_name: str,
        default_port: int = 50051,
        max_workers: int = 10,
        **kwargs: Any,
    ) -> None:
        """
        Initialize base gRPC service.

        Args:
            service_name: Name of the service
            default_port: Default port if not specified in environment
            max_workers: Maximum number of worker threads
            **kwargs: Additional arguments passed to BaseService
        """
        super().__init__(service_name=service_name, **kwargs)

        # Configure service logging
        self.logger = configure_service_logging(service_name)

        # gRPC configuration
        self.grpc_port = int(os.environ.get("GRPC_PORT", str(default_port)))
        self.max_workers = max_workers
        self.server: grpc.Server | None = None

        # Service state
        self._is_running = False
        self._shutdown_gracefully = False

        # Setup signal handlers for graceful shutdown
        self._setup_signal_handlers()

    @abstractmethod
    def create_servicer(self) -> ServicerProtocol:
        """
        Create the main servicer instance for this service.

        Returns:
            Servicer instance that implements the service's gRPC interface
        """
        ...

    @abstractmethod
    def get_add_servicer_function(self) -> callable:
        """
        Get the function to add the servicer to the server.

        Returns:
            Function that takes (servicer, server) and adds servicer to server
        """
        ...

    def get_service_config(self) -> GrpcServerConfig:
        """
        Get gRPC server configuration for this service.

        Returns:
            GrpcServerConfig instance with service-specific settings
        """
        return GrpcServerConfig(
            service_name=self.service_name,
            port=self.grpc_port,
            max_workers=self.max_workers,
            enable_health_check=True,
            enable_reflection=True,
        )

    def add_common_services(self, server: grpc.Server) -> None:
        """
        Add common services that all gRPC servers should have.

        Args:
            server: gRPC server instance
        """
        # Add health check service
        health_servicer = HealthServicer()
        health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
        self.logger.info("Added health check service")

        # Add logging streamer service if available
        try:
            logging_streamer_servicer = LoggingStreamerServicer()
            common_services_pb2_grpc.add_LoggingStreamerServicer_to_server(
                logging_streamer_servicer, server
            )
            self.logger.info("Added logging streamer service")
        except AttributeError:
            self.logger.warning(
                "LoggingStreamerServicer not available - ensure common_services.proto is compiled"
            )
        except Exception as e:
            self.logger.error("Failed to add logging streamer service: %s", e)

    def setup_server(self) -> grpc.Server:
        """
        Set up the gRPC server with all services.

        Returns:
            Configured gRPC server instance
        """
        # Create server
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=self.max_workers))

        # Add main servicer
        servicer = self.create_servicer()
        add_servicer_func = self.get_add_servicer_function()
        add_servicer_func(servicer, server)
        self.logger.info("Added main servicer to server")

        # Add common services
        self.add_common_services(server)

        # Add insecure port
        server.add_insecure_port(f"[::]:{self.grpc_port}")

        return server

    def start_server(self) -> None:
        """Start the gRPC server."""
        if self._is_running:
            self.logger.warning("Server is already running")
            return

        self.logger.log_service_startup({"port": self.grpc_port})

        try:
            self.server = self.setup_server()
            self.server.start()
            self._is_running = True

            self.logger.log_service_ready(
                port=self.grpc_port, additional_info={"max_workers": self.max_workers}
            )

            # Wait for termination
            self.server.wait_for_termination()

        except KeyboardInterrupt:
            self.logger.info("Received keyboard interrupt")
            self._shutdown_gracefully = True
        except Exception as e:
            self.logger.exception("Server error: %s", e)
            raise
        finally:
            self.stop_server()

    def stop_server(self, grace_period: int = 30) -> None:
        """
        Stop the gRPC server gracefully.

        Args:
            grace_period: Seconds to wait for graceful shutdown
        """
        if not self._is_running:
            return

        self.logger.log_service_shutdown("Graceful shutdown requested")

        if self.server:
            self.server.stop(grace_period)
            self.logger.info("Server stopped")

        self._is_running = False

    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""

        def signal_handler(signum: int, frame: Any) -> None:
            self.logger.info("Received signal %s, initiating graceful shutdown", signum)
            self._shutdown_gracefully = True
            if self.server:
                self.stop_server()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def run(self) -> None:
        """
        Main entry point to run the service.

        This method starts the server and handles the service lifecycle.
        """
        try:
            self.logger.info("Starting %s service", self.service_name)
            self.start_server()
        except Exception as e:
            self.logger.exception("Failed to start service: %s", e)
            sys.exit(1)

    def get_service_status(self) -> dict[str, Any]:
        """
        Get the current status of the service.

        Returns:
            Dict containing service status information
        """
        return {
            "service_name": self.service_name,
            "is_running": self._is_running,
            "grpc_port": self.grpc_port,
            "max_workers": self.max_workers,
            "shutdown_gracefully": self._shutdown_gracefully,
        }


def create_service_main(
    service_class: type[BaseGrpcService],
    service_name: str,
    default_port: int = 50051,
    **kwargs: Any,
) -> None:
    """
    Create a standardized main function for a gRPC service.

    Args:
        service_class: The service class to instantiate
        service_name: Name of the service
        default_port: Default port if not specified in environment
        **kwargs: Additional arguments passed to service constructor
    """
    # Debug information
    service_name_env = os.environ.get(
        f"{service_name.upper().replace('-', '_')}_SERVICE_NAME", service_name
    )
    grpc_port_env = os.environ.get("GRPC_PORT", str(default_port))

    print(
        f"DEBUG: {service_name} execution started. "
        f"SERVICE_NAME='{service_name_env}', "
        f"GRPC_PORT='{grpc_port_env}'",
        file=sys.stdout,
    )
    sys.stdout.flush()

    # Create and run service
    service = service_class(
        service_name=service_name_env,
        default_port=int(grpc_port_env),
        **kwargs,
    )
    service.run()


# Error handling utilities for gRPC methods
def handle_grpc_errors(logger: ServiceLogger):
    """
    Decorator to standardize error handling in gRPC methods.

    Args:
        logger: Service logger instance
    """

    def decorator(func):
        def wrapper(self, request, context):
            try:
                # Log request start
                method_name = func.__name__
                logger.debug("gRPC method %s called", method_name)

                # Call the actual method
                result = func(self, request, context)

                # Log successful completion
                logger.debug("gRPC method %s completed successfully", method_name)
                return result

            except Exception as e:
                # Log the error
                logger.exception("Error in gRPC method %s: %s", func.__name__, e)

                # Set gRPC error status
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details(f"Internal server error: {e}")

                # Return error response based on method return type
                # This is a simplified approach - real implementation would
                # need to handle different response types properly
                return None

        return wrapper

    return decorator


def validate_grpc_request(required_fields: list[str]):
    """
    Decorator to validate required fields in gRPC requests.

    Args:
        required_fields: List of field names that must be present and non-empty
    """

    def decorator(func):
        def wrapper(self, request, context):
            # Validate required fields
            for field in required_fields:
                if not hasattr(request, field) or not getattr(request, field):
                    context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                    context.set_details(f"Required field '{field}' is missing or empty")
                    return None

            # Call the actual method if validation passes
            return func(self, request, context)

        return wrapper

    return decorator
