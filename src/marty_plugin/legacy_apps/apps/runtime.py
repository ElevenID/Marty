from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import grpc
from grpc import aio as grpc_aio
from grpc_health.v1 import health_pb2, health_pb2_grpc
from grpc_health.v1.health import HealthServicer

from marty_common.auth_interceptor import create_auth_interceptor
from marty_common.config import Config as MartyConfig
from marty_common.grpc_interceptors import AsyncExceptionToStatusInterceptor
from marty_common.grpc_logging import LoggingStreamerServicer
from marty_common.grpc_metrics import create_async_metrics_interceptor
from marty_common.grpc_tls import build_client_credentials, configure_server_security
from marty_common.infrastructure import (
    DatabaseManager,
    EventBusProvider,
    KeyVaultClient,
    ObjectStorageClient,
    OutboxDispatcher,
    build_key_vault_client,
)
from marty_common.logging_config import setup_logging
from marty_common.metrics_server import start_metrics_server
from marty_common.otel import init_tracing, instrument_grpc
from marty_plugin.lib.certificate_lifecycle_monitor import CertificateLifecycleMonitor
from marty_plugin.proto.v1 import common_services_pb2_grpc

logger = logging.getLogger(__name__)


ServiceRegistrar = Callable[
    [grpc_aio.Server, dict[str, grpc_aio.Channel], HealthServicer, "ServiceDependencies"],
    None,
]


@dataclass(slots=True)
class ServiceDefinition:
    """Metadata necessary to bootstrap a Marty microservice."""

    name: str
    default_port: int
    registrar: ServiceRegistrar


@dataclass(slots=True)
class ServiceDependencies:
    database: DatabaseManager
    object_storage: ObjectStorageClient
    key_vault: KeyVaultClient
    event_bus: EventBusProvider
    runtime_config: MartyConfig
    outbox_dispatcher: OutboxDispatcher
    shutdown_hooks: list[Callable[[], Awaitable[None]]] = field(default_factory=list)

    async def shutdown(self) -> None:
        if self.shutdown_hooks:
            await asyncio.gather(
                *(hook() for hook in reversed(self.shutdown_hooks)),
                return_exceptions=True,
            )
        await self.outbox_dispatcher.stop()
        await self.event_bus.stop()
        await self.database.dispose()

    def register_shutdown_hook(self, hook: Callable[[], Awaitable[None]]) -> None:
        self.shutdown_hooks.append(hook)


async def build_dependencies_async(
    runtime_config: MartyConfig | None = None,
    service_name: str | None = None,
) -> ServiceDependencies:
    """Build service dependencies with service-specific database configuration.

    Args:
        runtime_config: Runtime configuration (optional)
        service_name: Name of the service (required for database isolation)

    Raises:
        ValueError: If service_name is not provided
    """
    if service_name is None:
        raise ValueError(
            "service_name is required for dependency injection. "
            "Each service must specify its name for proper database isolation."
        )

    if runtime_config is None:
        runtime_config = MartyConfig()

    database = DatabaseManager(runtime_config.database(service_name))
    await database.create_all()
    object_storage = ObjectStorageClient(runtime_config.object_storage())
    key_vault = build_key_vault_client(runtime_config.key_vault())
    event_bus_config = runtime_config.event_bus()
    event_bus = EventBusProvider(event_bus_config)
    outbox_dispatcher = OutboxDispatcher(database, event_bus)
    if event_bus_config.enabled:
        await outbox_dispatcher.start()
    return ServiceDependencies(
        database=database,
        object_storage=object_storage,
        key_vault=key_vault,
        event_bus=event_bus,
        runtime_config=runtime_config,
        outbox_dispatcher=outbox_dispatcher,
    )


def create_service_channels(
    config: dict[str, Any], tls_options: dict[str, Any]
) -> dict[str, grpc_aio.Channel]:
    """Create gRPC channels to other services based on discovery config.

    TLS is ALWAYS required for all inter-service communication.
    """
    channels: dict[str, grpc_aio.Channel] = {}

    # TLS is always required
    channel_credentials = build_client_credentials(tls_options)

    for service_name, address in config["service_discovery"].items():
        if service_name != config["service_name"].replace("-", "_"):
            logger.info("Creating secure channel to %s at %s", service_name, address)
            try:
                channels[service_name] = grpc_aio.secure_channel(address, channel_credentials)
            except grpc.RpcError:
                logger.exception("Failed to create secure channel to %s", service_name)

    return channels


def get_service_config(service_name: str, default_port: int) -> dict[str, Any]:
    """Build the runtime configuration for a specific service."""
    overridden_name = os.environ.get("SERVICE_NAME")
    if overridden_name and overridden_name != service_name:
        logger.warning(
            "Ignoring SERVICE_NAME=%s because entrypoint is fixed for %s",
            overridden_name,
            service_name,
        )

    grpc_port = int(os.environ.get("GRPC_PORT", str(default_port)))
    env = os.environ.get("ENV", "development")

    service_discovery = {
        "trust_anchor": (
            f"{os.environ.get('TRUST_ANCHOR_HOST', 'trust-anchor')}:"
            f"{os.environ.get('TRUST_ANCHOR_PORT', '9080')}"
        ),
        "csca_service": (
            f"{os.environ.get('CSCA_SERVICE_HOST', 'csca-service')}:"
            f"{os.environ.get('CSCA_SERVICE_PORT', '8081')}"
        ),
        "document_signer": (
            f"{os.environ.get('DOCUMENT_SIGNER_HOST', 'document-signer')}:"
            f"{os.environ.get('DOCUMENT_SIGNER_PORT', '8082')}"
        ),
        "inspection_system": (
            f"{os.environ.get('INSPECTION_SYSTEM_HOST', 'inspection-system')}:"
            f"{os.environ.get('INSPECTION_SYSTEM_PORT', '8083')}"
        ),
        "passport_engine": (
            f"{os.environ.get('PASSPORT_ENGINE_HOST', 'passport-engine')}:"
            f"{os.environ.get('PASSPORT_ENGINE_PORT', '8084')}"
        ),
        "mdl_engine": (
            f"{os.environ.get('MDL_ENGINE_HOST', 'mdl-engine')}:"
            f"{os.environ.get('MDL_ENGINE_PORT', '50051')}"
        ),
        "mdoc_engine": (
            f"{os.environ.get('MDOC_ENGINE_HOST', 'mdoc-engine')}:"
            f"{os.environ.get('MDOC_ENGINE_PORT', '50054')}"
        ),
        "pkd_service": (
            f"{os.environ.get('PKD_SERVICE_HOST', 'pkd-service')}:"
            f"{os.environ.get('PKD_SERVICE_PORT', '9090')}"
        ),
    }

    return {
        "service_name": service_name,
        "grpc_port": grpc_port,
        "env": env,
        "service_discovery": service_discovery,
    }


def init_certificate_lifecycle_monitor(
    config: dict[str, Any],
) -> CertificateLifecycleMonitor:
    """Initialize the Certificate Lifecycle Monitor."""
    csca_endpoint = config["service_discovery"].get("csca_service")

    if config["service_name"] == "csca-service":
        csca_endpoint = f"localhost:{config['grpc_port']}"

    config_file = Path("config") / "certificate_lifecycle_monitor.json"

    logger.info(
        "Initializing Certificate Lifecycle Monitor with endpoint %s and config %s",
        csca_endpoint,
        config_file,
    )

    return CertificateLifecycleMonitor(csca_endpoint=csca_endpoint, config_file=str(config_file))


CERT_MONITOR_SERVICES = {
    "csca-service",
    "document-signer",
    "trust-anchor",
    "passport-engine",
}


def should_enable_cert_monitor(service_name: str) -> bool:
    return service_name in CERT_MONITOR_SERVICES


def setup_health_service(server: grpc_aio.Server) -> HealthServicer:
    health = HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health, server)
    health.set("", health_pb2.HealthCheckResponse.SERVING)
    return health


def setup_logging_streamer_service(server: grpc_aio.Server, health: HealthServicer) -> None:
    try:
        logging_streamer_servicer = LoggingStreamerServicer()
        common_services_pb2_grpc.add_LoggingStreamerServicer_to_server(
            logging_streamer_servicer, server
        )
        logger.info("Added LoggingStreamerServicer to gRPC server")
        health.set(
            "common_services.LoggingStreamer",
            health_pb2.HealthCheckResponse.SERVING,
        )
    except Exception:
        logger.exception("Failed to add LoggingStreamerServicer")
        health.set(
            "common_services.LoggingStreamer",
            health_pb2.HealthCheckResponse.NOT_SERVING,
        )


# Individual registrar helpers -------------------------------------------------


def add_csca_service(
    server: grpc_aio.Server,
    channels: dict[str, grpc_aio.Channel],
    health: HealthServicer,
    dependencies: ServiceDependencies,
) -> None:
    from marty_plugin.lib.csca import CscaService
    from marty_plugin.proto.v1 import csca_service_pb2_grpc

    logger.info("Registering CSCA service")
    csca_service_pb2_grpc.add_CscaServiceServicer_to_server(
        CscaService(channels, dependencies), server
    )
    health.set("csca.CscaService", health_pb2.HealthCheckResponse.SERVING)


def add_document_signer_service(
    server: grpc_aio.Server,
    channels: dict[str, grpc_aio.Channel],
    health: HealthServicer,
    dependencies: ServiceDependencies,
) -> None:
    from marty_plugin.lib.document_signer import DocumentSigner
    from marty_plugin.proto.v1 import document_signer_pb2_grpc

    logger.info("Registering Document Signer service")
    document_signer_pb2_grpc.add_DocumentSignerServicer_to_server(
        DocumentSigner(channels, dependencies), server
    )
    health.set("document_signer.DocumentSigner", health_pb2.HealthCheckResponse.SERVING)


def add_trust_anchor_service(
    server: grpc_aio.Server,
    channels: dict[str, grpc_aio.Channel],
    health: HealthServicer,
    dependencies: ServiceDependencies,
) -> None:
    from marty_plugin.lib.trust_anchor import TrustAnchor
    from marty_plugin.proto.v1 import trust_anchor_pb2_grpc

    logger.info("Registering Trust Anchor service")
    trust_anchor_pb2_grpc.add_TrustAnchorServicer_to_server(
        TrustAnchor(channels, dependencies), server
    )
    health.set("trust.TrustAnchor", health_pb2.HealthCheckResponse.SERVING)


def add_inspection_system_service(
    server: grpc_aio.Server,
    channels: dict[str, grpc_aio.Channel],
    health: HealthServicer,
    dependencies: ServiceDependencies,
) -> None:
    from marty_plugin.lib.inspection_system import InspectionSystem
    from marty_plugin.proto.v1 import inspection_system_pb2_grpc

    logger.info("Registering Inspection System service")
    inspection_system_pb2_grpc.add_InspectionSystemServicer_to_server(
        InspectionSystem(channels, dependencies), server
    )
    health.set("inspection.InspectionSystem", health_pb2.HealthCheckResponse.SERVING)


def add_passport_engine_service(
    server: grpc_aio.Server,
    channels: dict[str, grpc_aio.Channel],
    health: HealthServicer,
    dependencies: ServiceDependencies,
) -> None:
    from marty_plugin.lib.passport_engine import PassportEngine
    from marty_plugin.proto.v1 import passport_engine_pb2_grpc

    logger.info("Registering Passport Engine service")
    passport_engine_pb2_grpc.add_PassportEngineServicer_to_server(
        PassportEngine(channels, dependencies), server
    )
    health.set("passport.PassportEngine", health_pb2.HealthCheckResponse.SERVING)


def add_mdl_engine_service(
    server: grpc_aio.Server,
    channels: dict[str, grpc_aio.Channel],
    health: HealthServicer,
    dependencies: ServiceDependencies | None = None,
) -> None:
    from mdl_engine.service import MDLEngineServicer
    from marty_plugin.proto.v1 import mdl_engine_pb2_grpc

    logger.info("Registering MDL Engine service")
    document_signer_channel = channels.get("document_signer")
    if not document_signer_channel:
        logger.error(
            "Document Signer channel not found for MDL Engine. MDL Engine may not function correctly."
        )
    mdl_engine_pb2_grpc.add_MDLEngineServicer_to_server(
        MDLEngineServicer(document_signer_channel), server
    )
    health.set("mdl.MDLEngine", health_pb2.HealthCheckResponse.SERVING)


def add_mdoc_engine_service(
    server: grpc_aio.Server,
    channels: dict[str, grpc_aio.Channel],
    health: HealthServicer,
    dependencies: ServiceDependencies | None = None,
) -> None:
    from mdoc_engine.service import MDocEngineServicer
    from marty_plugin.proto.v1 import mdoc_engine_pb2_grpc

    logger.info("Registering MDoc Engine service")
    mdoc_engine_pb2_grpc.add_MDocEngineServicer_to_server(MDocEngineServicer(channels), server)
    health.set("mdoc.MDocEngine", health_pb2.HealthCheckResponse.SERVING)


def add_pkd_service(
    server: grpc_aio.Server,
    channels: dict[str, grpc_aio.Channel],
    health: HealthServicer,
    dependencies: ServiceDependencies,
) -> None:
    from marty_plugin.lib.pkd_service import PKDService
    from marty_plugin.proto.v1 import pkd_service_pb2_grpc

    logger.info("Registering PKD service")
    pkd_service_pb2_grpc.add_PKDServiceServicer_to_server(
        PKDService(channels, dependencies), server
    )
    health.set("pkd.PKDService", health_pb2.HealthCheckResponse.SERVING)


def add_open_badges_service(
    server: grpc_aio.Server,
    channels: dict[str, grpc_aio.Channel],
    health: HealthServicer,
    dependencies: ServiceDependencies,
) -> None:
    from marty_common.config import Config
    from marty_plugin.lib.open_badges import OpenBadgesService
    from marty_plugin.proto.v1 import open_badges_service_pb2_grpc

    logger.info("Registering Open Badges service")
    config = Config()
    open_badges_service_pb2_grpc.add_OpenBadgesServiceServicer_to_server(
        OpenBadgesService(config), server
    )
    health.set(
        "open_badges.OpenBadgesService",
        health_pb2.HealthCheckResponse.SERVING,
    )


SERVICE_REGISTRARS: dict[str, ServiceRegistrar] = {
    "csca-service": add_csca_service,
    "document-signer": add_document_signer_service,
    "trust-anchor": add_trust_anchor_service,
    "inspection-system": add_inspection_system_service,
    "passport-engine": add_passport_engine_service,
    "mdl-engine": add_mdl_engine_service,
    "mdoc-engine": add_mdoc_engine_service,
    "pkd-service": add_pkd_service,
    "open-badges": add_open_badges_service,
}

SERVICE_DEFAULT_PORTS: dict[str, int] = {
    "csca-service": 8081,
    "document-signer": 8082,
    "trust-anchor": 9080,
    "inspection-system": 8083,
    "passport-engine": 8084,
    "mdl-engine": 8085,
    "mdoc-engine": 8086,
    "pkd-service": 9090,
    "open-badges": 8091,
}

SERVICE_DEFINITIONS: dict[str, ServiceDefinition] = {
    name: ServiceDefinition(
        name=name, default_port=SERVICE_DEFAULT_PORTS[name], registrar=registrar
    )
    for name, registrar in SERVICE_REGISTRARS.items()
}


async def serve_service_async(
    service: ServiceDefinition,
    *,
    runtime_config: MartyConfig | None = None,
) -> None:
    """Async entrypoint for a dedicated microservice."""
    setup_logging(service.name)

    # Initialize OpenTelemetry tracing
    init_tracing(service.name)

    # Instrument gRPC for tracing
    instrument_grpc()

    config = get_service_config(service.name, service.default_port)
    logger.info(
        "Starting %s with config: env=%s port=%s", service.name, config["env"], config["grpc_port"]
    )

    runtime_config = runtime_config or MartyConfig()
    tls_options = runtime_config.grpc_tls()

    # Start metrics server
    metrics_port = config["grpc_port"] + 1000  # e.g., if gRPC is 8081, metrics is 9081
    logger.info("Starting metrics server for %s on port %s", service.name, metrics_port)

    metrics_server = await start_metrics_server(
        service_name=service.name,
        version="1.0.0",
        host="0.0.0.0",
        port=metrics_port,
    )

    channels = create_service_channels(config, tls_options)
    # Resilience interceptor (circuit breaker, failure injection) can be toggled via env
    # Local import to avoid circular dependencies
    from marty_common.resilience import ResilienceServerInterceptor

    enable_resilience = os.environ.get("MARTY_RESILIENCE_ENABLED", "true").lower() in {
        "1",
        "true",
        "yes",
    }
    interceptors: list[grpc_aio.ServerInterceptor] = [AsyncExceptionToStatusInterceptor()]

    # Add metrics interceptor
    metrics_interceptor = create_async_metrics_interceptor(service.name)
    interceptors.append(metrics_interceptor)

    # Add authentication interceptor (ALWAYS ENABLED)
    auth_interceptor = create_auth_interceptor()
    interceptors.append(auth_interceptor)
    logger.info("Added authentication interceptor (REQUIRED)")

    if enable_resilience:
        interceptors.append(ResilienceServerInterceptor())
    server = grpc_aio.server(interceptors=interceptors)

    health = setup_health_service(server)
    setup_logging_streamer_service(server, health)

    dependencies = await build_dependencies_async(runtime_config, service_name=service.name)

    registrar = SERVICE_REGISTRARS.get(service.name)
    if not registrar:
        msg = f"Unknown service name: {service.name}"
        raise ValueError(msg)

    registrar(server, channels, health, dependencies)

    # Set up basic health checks
    metrics_server.health.add_check("grpc_server", True)
    metrics_server.health.add_check("database", True)  # Will be updated by service implementations

    cert_monitor: CertificateLifecycleMonitor | None = None
    if should_enable_cert_monitor(service.name):
        cert_monitor = init_certificate_lifecycle_monitor(config)

    server_address = f"[::]:{config['grpc_port']}"
    creds = configure_server_security(tls_options)
    if creds:
        server.add_secure_port(server_address, creds)
        logger.info("%s gRPC server configured with TLS on %s", service.name, server_address)
    else:
        logger.error("TLS configuration failed - server cannot start without security")
        raise RuntimeError("TLS is required but configuration failed")

    server_started = False
    try:
        await server.start()
        server_started = True
        logger.info("%s gRPC server started on %s", service.name, server_address)
        logger.info("%s metrics server available at http://0.0.0.0:%s", service.name, metrics_port)

        if cert_monitor:
            await cert_monitor.start()
            logger.info("Certificate Lifecycle Monitor started")

        await server.wait_for_termination()
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Shutdown signal received; terminating %s", service.name)
    finally:
        if cert_monitor:
            await cert_monitor.stop()
            logger.info("Certificate Lifecycle Monitor stopped")

        # Stop metrics server
        await metrics_server.stop()
        logger.info("Metrics server stopped")

        if server_started:
            await server.stop(grace=0)

        await asyncio.gather(
            *(channel.close() for channel in channels.values()),
            return_exceptions=True,
        )

        await dependencies.shutdown()


def serve_service(service: ServiceDefinition) -> None:
    """Start the service using asyncio."""
    asyncio.run(serve_service_async(service))


__all__ = [
    "SERVICE_DEFAULT_PORTS",
    "SERVICE_DEFINITIONS",
    "ServiceDefinition",
    "ServiceDependencies",
    "build_dependencies_async",
    "serve_service",
    "serve_service_async",
]
