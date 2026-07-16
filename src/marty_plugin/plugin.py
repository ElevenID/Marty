"""Marty plugin implementation for the released MMF plugin contract."""

from __future__ import annotations

from typing import Any

from mmf.core.plugins import MMFPlugin, PluginMetadata, ServiceDefinition

from .config import MartyTrustPKIConfig
from .services import CSCAService, DocumentSignerService, PKDService, TrustAnchorService


class MartyPlugin(MMFPlugin):
    """Expose Marty's public trust and identity services through MMF."""

    def __init__(self) -> None:
        super().__init__()
        self.config: MartyTrustPKIConfig | None = None
        self.services: dict[str, Any] = {}
        self._metadata = PluginMetadata(
            name="marty",
            version="1.0.0",
            description="Marty identity and trust services",
            author="ElevenID",
            dependencies=["marty-msf>=1.0.0"],
            keywords=["identity", "trust", "pki", "icao"],
            homepage="https://github.com/ElevenID/Marty",
            license="AGPL-3.0-only",
        )

    def get_metadata(self) -> PluginMetadata:
        return self._metadata

    def get_service_definitions(self) -> list[ServiceDefinition]:
        definitions = [
            ("trust-anchor", TrustAnchorService),
            ("pkd", PKDService),
            ("document-signer", DocumentSignerService),
            ("csca", CSCAService),
        ]
        return [
            ServiceDefinition(
                name=name,
                description=f"Marty {name} service",
                version=self._metadata.version,
                handler_class=handler,
                tags=["marty", "identity", "trust"],
            )
            for name, handler in definitions
        ]

    async def _do_initialize(self) -> None:
        self.config = MartyTrustPKIConfig(**self.context.config)
        self.services = {
            "trust-anchor": TrustAnchorService(),
            "pkd": PKDService(),
            "document-signer": DocumentSignerService(),
            "csca": CSCAService(),
        }
        configuration = self.config.model_dump()
        for service in self.services.values():
            await service.initialize(configuration)

    async def _do_start(self) -> None:
        for service in self.services.values():
            await service.start()

    async def _do_stop(self) -> None:
        for service in reversed(list(self.services.values())):
            await service.stop()

    async def _do_cleanup(self) -> None:
        self.services.clear()
        self.config = None

    async def health_check(self) -> dict[str, Any]:
        service_health = {
            name: await service.get_health_status()
            for name, service in self.services.items()
        }
        unhealthy = any(
            result.get("status") not in {"healthy", "warning"}
            for result in service_health.values()
        )
        return {
            "status": "unhealthy" if unhealthy else "healthy",
            "plugin": self._metadata.name,
            "version": self._metadata.version,
            "services": service_health,
        }

    def get_service(self, name: str) -> Any | None:
        return self.services.get(name)
