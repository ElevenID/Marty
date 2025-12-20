"""
Centralized service configuration for Marty platform.

This module provides a single source of truth for all service configurations,
eliminating duplication across test files, environment configs, and deployment scripts.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional


class ServiceType(Enum):
    """Service types in the Marty platform."""

    GRPC = "grpc"
    HTTP = "http"
    UI = "ui"
    INFRASTRUCTURE = "infrastructure"


@dataclass
class ServiceDefinition:
    """Complete service definition with all port mappings."""

    name: str
    service_type: ServiceType
    base_port: int
    description: str = ""

    @property
    def grpc_port(self) -> int:
        """gRPC service port (base port)."""
        return self.base_port

    @property
    def health_port(self) -> int:
        """Health check port (base + 1)."""
        return self.base_port + 1

    @property
    def metrics_port(self) -> int:
        """Metrics port (base + 1000)."""
        return self.base_port + 1000

    @property
    def http_endpoint(self) -> str:
        """HTTP endpoint URL for local development."""
        return f"http://localhost:{self.base_port}"

    @property
    def grpc_endpoint(self) -> str:
        """gRPC endpoint for local development."""
        return f"localhost:{self.grpc_port}"

    @property
    def metrics_endpoint(self) -> str:
        """Metrics endpoint URL."""
        return f"http://localhost:{self.metrics_port}/metrics"

    @property
    def health_endpoint(self) -> str:
        """Health endpoint URL."""
        return f"http://localhost:{self.health_port}/health"


class ServiceRegistry:
    """Centralized registry of all Marty services."""

    # Core microservices
    SERVICES = {
        "trust-svc": ServiceDefinition(
            name="trust-svc",
            service_type=ServiceType.GRPC,
            base_port=8090,
            description="Trust service for certificate management",
        ),
        "trust-anchor": ServiceDefinition(
            name="trust-anchor",
            service_type=ServiceType.GRPC,
            base_port=9080,
            description="Trust anchor service",
        ),
        "csca-service": ServiceDefinition(
            name="csca-service",
            service_type=ServiceType.GRPC,
            base_port=8081,
            description="CSCA certificate authority service",
        ),
        "document-signer": ServiceDefinition(
            name="document-signer",
            service_type=ServiceType.GRPC,
            base_port=8082,
            description="Document signing service",
        ),
        "inspection-system": ServiceDefinition(
            name="inspection-system",
            service_type=ServiceType.GRPC,
            base_port=8083,
            description="Document inspection service",
        ),
        "passport-engine": ServiceDefinition(
            name="passport-engine",
            service_type=ServiceType.GRPC,
            base_port=8084,
            description="Passport processing engine",
        ),
        "mdl-engine": ServiceDefinition(
            name="mdl-engine",
            service_type=ServiceType.GRPC,
            base_port=8085,
            description="Mobile driver's license engine",
        ),
        "mdoc-engine": ServiceDefinition(
            name="mdoc-engine",
            service_type=ServiceType.GRPC,
            base_port=8086,
            description="Mobile document engine",
        ),
        "dtc-engine": ServiceDefinition(
            name="dtc-engine",
            service_type=ServiceType.GRPC,
            base_port=8087,
            description="Digital travel credential engine",
        ),
        "pkd-service": ServiceDefinition(
            name="pkd-service",
            service_type=ServiceType.GRPC,
            base_port=8088,
            description="Public key directory service",
        ),
        "credential-ledger": ServiceDefinition(
            name="credential-ledger",
            service_type=ServiceType.GRPC,
            base_port=8089,
            description="Credential ledger service",
        ),
        "ui-app": ServiceDefinition(
            name="ui-app",
            service_type=ServiceType.UI,
            base_port=8000,
            description="Web user interface application",
        ),
    }

    @classmethod
    def get_service(cls, service_name: str) -> ServiceDefinition | None:
        """Get service definition by name."""
        return cls.SERVICES.get(service_name)

    @classmethod
    def get_all_services(cls) -> dict[str, ServiceDefinition]:
        """Get all service definitions."""
        return cls.SERVICES.copy()

    @classmethod
    def get_services_by_type(cls, service_type: ServiceType) -> dict[str, ServiceDefinition]:
        """Get services filtered by type."""
        return {
            name: service
            for name, service in cls.SERVICES.items()
            if service.service_type == service_type
        }

    @classmethod
    def get_service_ports(cls) -> dict[str, int]:
        """Get base ports for all services (backward compatibility)."""
        return {name: service.base_port for name, service in cls.SERVICES.items()}

    @classmethod
    def get_grpc_ports(cls) -> dict[str, int]:
        """Get gRPC ports for all services (backward compatibility)."""
        return {name: service.grpc_port for name, service in cls.SERVICES.items()}

    @classmethod
    def get_metrics_ports(cls) -> dict[str, int]:
        """Get metrics ports for all services (backward compatibility)."""
        return {name: service.metrics_port for name, service in cls.SERVICES.items()}

    @classmethod
    def get_health_ports(cls) -> dict[str, int]:
        """Get health check ports for all services."""
        return {name: service.health_port for name, service in cls.SERVICES.items()}

    @classmethod
    def get_service_endpoints(cls, environment: str = "local") -> dict[str, str]:
        """Get service endpoints for a given environment."""
        endpoints = {}
        for name, service in cls.SERVICES.items():
            if environment == "local":
                endpoints[name] = service.http_endpoint
            elif environment.startswith("k8s"):
                namespace = environment.split(":")[-1] if ":" in environment else "marty"
                endpoints[name] = f"http://{name}.{namespace}.svc.cluster.local:{service.base_port}"
            else:
                # Default to service name as hostname
                endpoints[name] = f"http://{name}:{service.base_port}"
        return endpoints


# Convenience functions for backward compatibility
def get_service_port(service_name: str, default: int = 8080) -> int:
    """Get base port for a service."""
    service = ServiceRegistry.get_service(service_name)
    return service.base_port if service else default


def get_grpc_port(service_name: str, default: int = 9090) -> int:
    """Get gRPC port for a service."""
    service = ServiceRegistry.get_service(service_name)
    return service.grpc_port if service else default


def get_metrics_port(service_name: str, default: int = 8081) -> int:
    """Get metrics port for a service."""
    service = ServiceRegistry.get_service(service_name)
    return service.metrics_port if service else default


def get_service_endpoint(service_name: str, environment: str = "local") -> str | None:
    """Get service endpoint URL."""
    return ServiceRegistry.get_service_endpoints(environment).get(service_name)


# Export for easy imports
__all__ = [
    "ServiceDefinition",
    "ServiceType",
    "ServiceRegistry",
    "get_service_port",
    "get_grpc_port",
    "get_metrics_port",
    "get_service_endpoint",
]
