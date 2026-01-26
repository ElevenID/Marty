"""
Digital Identity MMF Plugin

Registers the Digital Identity API with the Marty Microservices Framework (MMF).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from digital_identity.infrastructure.adapters.rest import (
    trust_profile_router,
    credential_template_router,
    presentation_policy_router,
    deployment_profile_router,
    flow_router,
    credential_router,
)
from digital_identity.infrastructure.persistence.database import (
    DigitalIdentityDatabaseConfig,
    DigitalIdentityDatabaseManager,
    get_database_manager,
    set_database_manager,
    init_database,
    close_database,
)
from digital_identity.infrastructure.adapters.rest.dependencies import configure_dependencies
from digital_identity.infrastructure.adapters.events import (
    DigitalIdentityEventPublisher,
    create_event_publisher,
)

logger = logging.getLogger(__name__)


class DigitalIdentityPlugin:
    """
    MMF Plugin for Digital Identity API.
    
    Registers REST API routers, configures services, and integrates with
    the Marty ecosystem (trust services, workflow engine, event bus).
    """
    
    name = "digital-identity"
    version = "0.1.0"
    description = "Digital Identity API - Trust Profiles, Credential Templates, Presentation Policies, Deployment Profiles, and Flows"
    
    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize the plugin with configuration.
        
        Args:
            config: Plugin configuration from mmf.yaml
        """
        self.config = config or {}
        self.enabled = self.config.get("enabled", True)
        logger.info(f"Digital Identity plugin initialized (enabled={self.enabled})")
    
    def register_routes(self, app: FastAPI) -> None:
        """
        Register API routes with the FastAPI application.
        
        Args:
            app: FastAPI application instance
        """
        if not self.enabled:
            logger.info("Digital Identity plugin disabled - skipping route registration")
            return
        
        # Register all routers
        routers = [
            ("Trust Profiles", trust_profile_router),
            ("Credential Templates", credential_template_router),
            ("Presentation Policies", presentation_policy_router),
            ("Deployment Profiles", deployment_profile_router),
            ("Flows", flow_router),
            ("Credentials", credential_router),
        ]
        
        for name, router in routers:
            app.include_router(router)
            logger.info(f"Registered {name} router: {router.prefix}")
        
        logger.info("Digital Identity API routes registered")
    
    def configure_services(self, container: Any) -> None:
        """
        Configure services and dependencies in the DI container.
        
        Args:
            container: Dependency injection container
        """
        if not self.enabled:
            return
        
        # Configure trust adapters
        self._configure_trust_adapters(container)
        
        # Configure workflow integration
        self._configure_workflow_integration(container)
        
        # Configure event publisher
        self._configure_event_publisher(container)
        
        logger.info("Digital Identity services configured")
    
    def _configure_trust_adapters(self, container: Any) -> None:
        """Configure trust profile adapters based on configuration."""
        trust_config = self.config.get("trust_profiles", {})
        
        # ICAO Trust Profile
        if trust_config.get("icao", {}).get("enabled", True):
            from digital_identity.infrastructure.trust import IcaoTrustProfile
            
            icao_config = trust_config.get("icao", {})
            trust_store_path = Path(icao_config.get("trust_store_path", "data/csca"))
            
            icao_adapter = IcaoTrustProfile(
                trust_store_path=trust_store_path,
                master_list_sources=icao_config.get("master_list_sources", []),
                pkd_urls=icao_config.get("pkd_urls", []),
            )
            
            # Register in container
            container.register("trust_adapter_icao", icao_adapter)
            logger.info(f"Registered ICAO trust adapter (path={trust_store_path})")
        
        # AAMVA Trust Profile
        if trust_config.get("aamva", {}).get("enabled", True):
            from digital_identity.infrastructure.trust import AamvaTrustProfile
            
            aamva_config = trust_config.get("aamva", {})
            iaca_directory = Path(aamva_config.get("iaca_directory", "data/iaca"))
            
            aamva_adapter = AamvaTrustProfile(
                iaca_directory=iaca_directory,
                vical_url=aamva_config.get("vical_url"),
                dts_url=aamva_config.get("dts_url"),
            )
            
            container.register("trust_adapter_aamva", aamva_adapter)
            logger.info(f"Registered AAMVA trust adapter (path={iaca_directory})")
        
        # EUDI Trust Profile
        if trust_config.get("eudi", {}).get("enabled", False):
            from digital_identity.infrastructure.trust import EudiTrustProfile
            
            eudi_config = trust_config.get("eudi", {})
            
            eudi_adapter = EudiTrustProfile(
                trust_list_url=eudi_config.get("trust_list_url"),
                member_state=eudi_config.get("member_state"),
            )
            
            container.register("trust_adapter_eudi", eudi_adapter)
            logger.info("Registered EUDI trust adapter")
    
    def _configure_workflow_integration(self, container: Any) -> None:
        """Configure integration with existing workflow engine."""
        # Workflow engine and saga orchestrator should be resolved from container
        # and registered for use by FlowService
        
        try:
            if hasattr(container, 'resolve'):
                workflow_engine = container.resolve("workflow_engine")
                if workflow_engine:
                    container.register("digital_identity_workflow_engine", workflow_engine)
                    logger.info("Workflow engine integration configured")
        except Exception as e:
            logger.warning(f"Workflow engine not available: {e}")
    
    def _configure_event_publisher(self, container: Any) -> None:
        """Configure domain event publishing."""
        event_config = self.config.get("events", {})
        
        if not event_config.get("enabled", True):
            logger.info("Event publishing disabled")
            return
        
        # Try to get message producer from container
        producer = None
        try:
            if hasattr(container, 'resolve'):
                producer = container.resolve("message_producer")
        except Exception as e:
            logger.warning(f"Message producer not available: {e}")
        
        # Create event publisher
        event_publisher = create_event_publisher(
            producer=producer,
            use_memory=(producer is None),
        )
        
        # Register in container
        if hasattr(container, 'register'):
            container.register("digital_identity_event_publisher", event_publisher)
        
        logger.info(f"Event publisher configured (in_memory={producer is None})")
    
    async def startup(self) -> None:
        """
        Plugin startup hook.
        
        Called when the application starts. Initializes:
        - Database tables
        - Trust anchor refresh
        - Cache warming
        """
        if not self.enabled:
            return
        
        logger.info("Digital Identity plugin starting up...")
        
        # Initialize database
        db_config_dict = self.config.get("database", {})
        db_config = DigitalIdentityDatabaseConfig.from_dict(db_config_dict)
        
        db_manager = DigitalIdentityDatabaseManager(db_config)
        set_database_manager(db_manager)
        
        await init_database(db_config)
        logger.info("Database initialized")
        
        # Initialize credential services
        from digital_identity.application.services.credential_issuance_service import (
            CredentialIssuanceService,
        )
        from digital_identity.infrastructure.persistence.repositories import (
            IssuedCredentialRepository,
            CredentialTemplateRepository,
            RevocationBatchRepository,
        )
        from digital_identity.infrastructure.adapters.rest.credential_router import (
            set_credential_services,
        )
        
        # Create repository and service instances
        # Note: Session will be provided by FastAPI dependency injection
        # For now, create service with None - will be properly injected per-request
        credential_repo = IssuedCredentialRepository(session=None)  # type: ignore
        template_repo = CredentialTemplateRepository(session=None)  # type: ignore
        batch_repo = RevocationBatchRepository(session=None)  # type: ignore
        
        # Create credential issuance service
        # TODO: Initialize status_list_service from marty-credentials
        issuance_service = CredentialIssuanceService(
            credential_repository=credential_repo,
            credential_template_repository=template_repo,
            revocation_batch_repository=batch_repo,
            status_list_service=None,  # TODO: Wire up status list service
            jwt_issuer=None,  # TODO: Wire up JWT issuer from marty-credentials
            mdoc_issuer=None,  # TODO: Wire up mDoc issuer when ready
        )
        
        # Register services with credential router
        set_credential_services(
            issuance_service=issuance_service,
            credential_repository=credential_repo,
        )
        
        logger.info("Credential issuance services initialized")
        
        # Configure dependencies for FastAPI routes
        trust_adapters = self._get_configured_trust_adapters()
        event_publisher = create_event_publisher(use_memory=True)  # Will be replaced in configure_services
        
        configure_dependencies(
            event_publisher=event_publisher,
            trust_adapters=trust_adapters,
        )
        
        logger.info("Digital Identity plugin started successfully")
    
    def _get_configured_trust_adapters(self) -> dict[str, Any]:
        """Build trust adapter dictionary from configuration."""
        trust_config = self.config.get("trust_profiles", {})
        adapters = {}
        
        # ICAO
        if trust_config.get("icao", {}).get("enabled", True):
            try:
                from digital_identity.infrastructure.trust import IcaoTrustProfile
                icao_config = trust_config.get("icao", {})
                adapters["ICAO"] = IcaoTrustProfile(
                    trust_store_path=Path(icao_config.get("trust_store_path", "data/csca")),
                    master_list_sources=icao_config.get("master_list_sources", []),
                    pkd_urls=icao_config.get("pkd_urls", []),
                )
            except Exception as e:
                logger.warning(f"Failed to initialize ICAO adapter: {e}")
        
        # AAMVA
        if trust_config.get("aamva", {}).get("enabled", True):
            try:
                from digital_identity.infrastructure.trust import AamvaTrustProfile
                aamva_config = trust_config.get("aamva", {})
                adapters["AAMVA"] = AamvaTrustProfile(
                    iaca_directory=Path(aamva_config.get("iaca_directory", "data/iaca")),
                    vical_url=aamva_config.get("vical_url"),
                    dts_url=aamva_config.get("dts_url"),
                )
            except Exception as e:
                logger.warning(f"Failed to initialize AAMVA adapter: {e}")
        
        # EUDI
        if trust_config.get("eudi", {}).get("enabled", False):
            try:
                from digital_identity.infrastructure.trust import EudiTrustProfile
                eudi_config = trust_config.get("eudi", {})
                adapters["EUDI"] = EudiTrustProfile(
                    trust_list_url=eudi_config.get("trust_list_url"),
                    member_state=eudi_config.get("member_state"),
                )
            except Exception as e:
                logger.warning(f"Failed to initialize EUDI adapter: {e}")
        
        return adapters
    
    async def shutdown(self) -> None:
        """
        Plugin shutdown hook.
        
        Closes database connections and cleans up resources.
        """
        if not self.enabled:
            return
        
        logger.info("Digital Identity plugin shutting down...")
        
        await close_database()
        
        logger.info("Digital Identity plugin shut down successfully")


# Plugin registration function
def register_plugin(app: FastAPI, config: dict[str, Any] | None = None) -> DigitalIdentityPlugin:
    """
    Register the Digital Identity plugin with the application.
    
    Usage:
        from digital_identity.plugin import register_plugin
        
        app = FastAPI()
        plugin = register_plugin(app, config)
    
    Args:
        app: FastAPI application instance
        config: Plugin configuration
    
    Returns:
        Plugin instance
    """
    plugin = DigitalIdentityPlugin(config)
    plugin.register_routes(app)
    
    # Note: configure_services requires DI container
    # plugin.configure_services(container)
    
    return plugin
