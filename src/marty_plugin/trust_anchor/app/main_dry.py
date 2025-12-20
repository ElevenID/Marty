"""
Trust Anchor service using the new gRPC Service Factory.

This demonstrates the ultimate DRY pattern for gRPC services,
reducing the main.py to just a few lines while maintaining full functionality.
"""

from marty_plugin.common.grpc_service_factory import create_grpc_service_factory
from marty_plugin.proto.trust_anchor_pb2_grpc import add_TrustAnchorServicer_to_server
from marty_plugin.trust_anchor.app.grpc_service import TrustAnchorService


def main() -> None:
    """
    Run Trust Anchor service using the new gRPC Service Factory.

    This replaces ~40 lines of server setup code with just 8 lines
    while providing the same functionality plus additional features:
    - Automatic health checks
    - Built-in logging streamer
    - gRPC reflection
    - Consistent configuration patterns
    - Signal handling and graceful shutdown
    - TLS support ready
    """
    # Create factory with configuration from BaseServiceConfig patterns
    factory = create_grpc_service_factory(
        service_name="trust-anchor",
        config_type="grpc",
        grpc_port=50051,
        grpc_max_workers=10,
        reflection_enabled=True,
        debug=True,
    )

    # Register the Trust Anchor service
    factory.register_service(
        name="trust_anchor",
        servicer_factory=lambda **_: TrustAnchorService(),
        registration_func=add_TrustAnchorServicer_to_server,
        health_service_name="trust.TrustAnchor",
        priority=50,  # Custom priority if needed
    )

    # Start the server (includes all the boilerplate: signal handling,
    # health checks, logging setup, etc.)
    factory.serve()


if __name__ == "__main__":
    main()
