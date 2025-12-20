"""
Example demonstrating gRPC Service Factory usage for DRY service creation.

This file shows how services can use the new gRPC Service Factory to
dramatically reduce boilerplate code and standardize service patterns.
"""

# Example 1: Traditional Service Setup (BEFORE - lots of duplication)
"""
def serve_trust_anchor_old():
    service_name = "trust-anchor"
    setup_logging(service_name=service_name)
    logger = get_logger(__name__)

    port = os.environ.get("GRPC_PORT", 50051)
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))

    # Add main service
    servicer = TrustAnchorService()
    add_TrustAnchorServicer_to_server(servicer, server)

    # Add health check
    health_servicer = HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)

    # Add logging streamer
    try:
        logging_streamer = LoggingStreamerServicer()
        common_services_pb2_grpc.add_LoggingStreamerServicer_to_server(
            logging_streamer, server
        )
    except Exception as e:
        logger.error(f"Failed to add logging streamer: {e}")

    # Configure server
    server.add_insecure_port(f"[::]:{port}")

    # Signal handling
    def signal_handler(signum, frame):
        logger.info("Shutting down...")
        server.stop(30)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start server
    server.start()
    logger.info(f"Server started on port {port}")
    server.wait_for_termination()

# ~50 lines of duplicated code per service!
"""

# Example 2: Using gRPC Service Factory (AFTER - DRY patterns)

from marty_plugin.common.grpc_service_factory import (
    create_grpc_service_factory,
    grpc_service,
    run_single_service,
)
from marty_plugin.proto.trust_anchor_pb2_grpc import add_TrustAnchorServicer_to_server
from marty_plugin.trust_anchor.app.services.trust_anchor_service import TrustAnchorService


# Option A: Single service with minimal setup (3 lines!)
def serve_trust_anchor_simple():
    """Run Trust Anchor service with absolute minimal configuration."""
    run_single_service(
        service_name="trust-anchor",
        servicer_factory=lambda: TrustAnchorService(),
        registration_func=add_TrustAnchorServicer_to_server,
    )


# Option B: Factory pattern with configuration (8 lines!)
def serve_trust_anchor_configured():
    """Run Trust Anchor service with custom configuration."""
    factory = create_grpc_service_factory(
        service_name="trust-anchor",
        grpc_port=50051,
        debug=True,
    )

    factory.register_service(
        name="trust_anchor",
        servicer_factory=lambda: TrustAnchorService(),
        registration_func=add_TrustAnchorServicer_to_server,
    )

    factory.serve()


# Option C: Using decorator for automatic registration (cleanest!)
@grpc_service(
    name="trust_anchor",
    registration_func=add_TrustAnchorServicer_to_server,
    health_service_name="trust.TrustAnchor",
)
class TrustAnchorServiceDecorated(TrustAnchorService):
    """Trust Anchor service with automatic registration."""

    pass


def serve_trust_anchor_decorated():
    """Run decorated Trust Anchor service (2 lines!)."""
    factory = create_grpc_service_factory("trust-anchor")
    factory.serve()


# Example 3: Multi-service setup (before would be 150+ lines)
def serve_multi_service():
    """Example of running multiple services in one server."""
    from marty_plugin.pkd_service.app.services.pkd_service import PKDService
    from marty_plugin.proto.pkd_service_pb2_grpc import add_PKDServiceServicer_to_server

    factory = create_grpc_service_factory(
        service_name="multi-service",
        grpc_port=50051,
        reflection_enabled=True,
    )

    # Register multiple services
    factory.register_service(
        name="trust_anchor",
        servicer_factory=lambda: TrustAnchorService(),
        registration_func=add_TrustAnchorServicer_to_server,
        priority=10,
    ).register_service(
        name="pkd_service",
        servicer_factory=lambda: PKDService(),
        registration_func=add_PKDServiceServicer_to_server,
        priority=20,
    )

    factory.serve()


# Example 4: Service with dependencies
def serve_with_dependencies():
    """Example showing dependency injection patterns."""
    try:
        from marty_plugin.pkd_service.app.core.database import get_database  # type: ignore
        from marty_plugin.pkd_service.app.services.pkd_service import PKDService  # type: ignore
        from marty_plugin.proto.pkd_service_pb2_grpc import add_PKDServiceServicer_to_server  # type: ignore

        factory = create_grpc_service_factory("pkd-service")
        factory.register_service(
            name="pkd_service",
            servicer_factory=lambda db=None: PKDService(database=db),
            registration_func=add_PKDServiceServicer_to_server,
            dependencies={"db": get_database()},
        )
        factory.serve()
    except Exception:  # pragma: no cover - example code
        pass


# Example 5: TLS-enabled service
def serve_secure_service():
    """Example of TLS-secured gRPC service."""
    factory = create_grpc_service_factory(
        service_name="secure-trust-anchor",
        tls_enabled=True,
        tls_cert_file="/path/to/cert.pem",
        tls_key_file="/path/to/key.pem",
    )

    factory.register_service(
        name="trust_anchor",
        servicer_factory=lambda: TrustAnchorService(),
        registration_func=add_TrustAnchorServicer_to_server,
    )

    factory.serve()


# Code Reduction Summary:
# ======================
# Traditional setup: ~50 lines per service
# Factory pattern:    ~8 lines per service  (84% reduction)
# Decorator pattern:  ~2 lines per service  (96% reduction)
#
# Benefits:
# - Consistent logging setup across all services
# - Automatic health checks and reflection
# - Standardized error handling and graceful shutdown
# - Easy TLS configuration
# - Service dependency injection
# - Priority-based service registration
# - Multi-service support
# - Signal handling out of the box


if __name__ == "__main__":
    # Example of running the service
    serve_trust_anchor_simple()
