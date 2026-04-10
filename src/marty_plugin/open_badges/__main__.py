"""Standalone entrypoint for the Open Badges gRPC service.

Usage:
    python -m marty_plugin.open_badges

Replaces the legacy ``apps.open_badges`` entrypoint and eliminates the
PYTHONPATH hack that pointed into ``legacy_apps/``.
"""

from __future__ import annotations

import asyncio
import logging
import os

import grpc
from grpc import aio as grpc_aio
from grpc_health.v1 import health_pb2, health_pb2_grpc
from grpc_health.v1.health import HealthServicer

from marty_backend_common.auth_interceptor import create_auth_interceptor
from marty_backend_common.config import Config
from marty_backend_common.grpc_interceptors import AsyncExceptionToStatusInterceptor
from marty_backend_common.grpc_logging import LoggingStreamerServicer
from marty_backend_common.grpc_metrics import create_async_metrics_interceptor
from marty_backend_common.grpc_tls import configure_server_security
from marty_backend_common.logging_config import setup_logging
from marty_backend_common.metrics_server import start_metrics_server
from marty_backend_common.otel import init_tracing, instrument_grpc
from marty_plugin.lib.open_badges import OpenBadgesService
from marty_plugin.proto.v1 import (
    common_services_pb2_grpc,
    open_badges_service_pb2_grpc,
)

logger = logging.getLogger(__name__)

SERVICE_NAME = "open-badges"
DEFAULT_PORT = 8091


async def serve() -> None:
    """Bootstrap and run the Open Badges gRPC server."""

    setup_logging(SERVICE_NAME)
    init_tracing(SERVICE_NAME)
    instrument_grpc()

    grpc_port = int(os.environ.get("GRPC_PORT", str(DEFAULT_PORT)))
    metrics_port = grpc_port + 1000  # 9091

    logger.info("Starting %s on port %s (metrics %s)", SERVICE_NAME, grpc_port, metrics_port)

    # Metrics
    metrics_server = await start_metrics_server(
        service_name=SERVICE_NAME,
        version="1.0.0",
        host="0.0.0.0",
        port=metrics_port,
    )

    # Interceptors
    interceptors: list[grpc_aio.ServerInterceptor] = [
        AsyncExceptionToStatusInterceptor(),
        create_async_metrics_interceptor(SERVICE_NAME),
        create_auth_interceptor(),
    ]

    # Optional resilience
    if os.environ.get("MARTY_RESILIENCE_ENABLED", "true").lower() in {"1", "true", "yes"}:
        from marty_backend_common.resilience import ResilienceServerInterceptor
        interceptors.append(ResilienceServerInterceptor())

    server = grpc_aio.server(interceptors=interceptors)

    # Health service
    health = HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health, server)
    health.set("", health_pb2.HealthCheckResponse.SERVING)

    # Logging streamer
    try:
        common_services_pb2_grpc.add_LoggingStreamerServicer_to_server(
            LoggingStreamerServicer(), server
        )
    except Exception:
        logger.exception("Failed to add LoggingStreamerServicer")

    # Register Open Badges service
    config = Config()
    open_badges_service_pb2_grpc.add_OpenBadgesServiceServicer_to_server(
        OpenBadgesService(config), server
    )
    health.set("open_badges.OpenBadgesService", health_pb2.HealthCheckResponse.SERVING)
    logger.info("Registered OpenBadgesService")

    # TLS
    runtime_config = Config()
    tls_options = runtime_config.grpc_tls()
    server_address = f"[::]:{grpc_port}"
    creds = configure_server_security(tls_options)
    if creds:
        server.add_secure_port(server_address, creds)
        logger.info("TLS configured on %s", server_address)
    else:
        logger.error("TLS configuration failed — server cannot start without security")
        raise RuntimeError("TLS is required but configuration failed")

    # Start
    metrics_server.health.add_check("grpc_server", True)

    try:
        await server.start()
        logger.info("%s gRPC server started on %s", SERVICE_NAME, server_address)
        await server.wait_for_termination()
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Shutdown signal received")
    finally:
        await metrics_server.stop()
        await server.stop(grace=0)


def main() -> None:
    asyncio.run(serve())


if __name__ == "__main__":
    main()
