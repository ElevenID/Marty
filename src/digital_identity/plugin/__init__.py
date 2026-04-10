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
    revocation_profile_router,
    application_template_router,
    verification_session_router,
    compliance_profile_router,
    lane_router,
    issuer_router,
    cascade_router,
    device_router,
    trust_anchor_router,
    trust_framework_router,
    org_trust_profile_router,
    organization_router,
    webhook_router,
    subscription_router,
    api_key_router,
    issuance_record_router,
    policy_set_router,
    wallet_profile_router,
    device_registration_router,
    applicant_router,
    reviewer_lock_router,
    vetting_check_router,
    biometric_enrollment_router,
    notification_payload_router,
    signing_key_router,
    status_list_router,
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
from licensing.routes import (
    admin_license_router,
    public_license_router,
    admin_registry_router,
    configure_license_dependencies,
)
from subscription.billing_routes import (
    billing_router,
    payments_router,
    configure_billing_dependencies,
)
from licensing.usage_routes import (
    usage_router,
    admin_usage_router,
    configure_usage_dependencies,
)
from subscription.kms_router import kms_router

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from subscription.kms_router import limiter as kms_limiter
from subscription.metrics import get_metrics as get_kms_metrics
from subscription.tls_middleware import EnforceTLSMiddleware

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
            ("Revocation Profiles", revocation_profile_router),
            ("Application Templates", application_template_router),
            ("Verification Sessions", verification_session_router),
            ("Compliance Profiles", compliance_profile_router),
            ("Lanes", lane_router),
            ("Issuers", issuer_router),
            ("Cascade Operations", cascade_router),
            ("Devices", device_router),
            ("Trust Anchors", trust_anchor_router),
            ("Trust Frameworks", trust_framework_router),
            ("Organization Trust Profiles", org_trust_profile_router),
            ("Organizations", organization_router),
            ("Webhooks", webhook_router),
            ("Subscriptions", subscription_router),
            ("API Keys", api_key_router),
            ("Issuance Records", issuance_record_router),
            ("Policy Sets", policy_set_router),
            ("Wallet Profiles", wallet_profile_router),
            ("Device Registrations", device_registration_router),
            ("Applicants", applicant_router),
            ("Reviewer Locks", reviewer_lock_router),
            ("Vetting Checks", vetting_check_router),
            ("Biometric Enrollments", biometric_enrollment_router),
            ("Notification Payloads", notification_payload_router),
            ("Signing Keys", signing_key_router),
            ("Status List", status_list_router),
            ("License Administration", admin_license_router),
            ("License Validation", public_license_router),
            ("Registry Administration", admin_registry_router),
            ("Billing", billing_router),
            ("Payments", payments_router),
            ("Usage", usage_router),
            ("Usage Administration", admin_usage_router),
            ("KMS Configuration", kms_router),
        ]
        
        for name, router in routers:
            app.include_router(router)
            logger.info(f"Registered {name} router: {router.prefix}")
        
        # Wire slowapi rate limiter
        app.state.limiter = kms_limiter
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        app.add_middleware(SlowAPIMiddleware)

        # Wire TLS enforcement middleware
        app.add_middleware(EnforceTLSMiddleware)

        # KMS metrics endpoint
        from starlette.responses import Response

        @app.get("/metrics/kms", include_in_schema=False)
        async def kms_metrics():
            return Response(
                content=get_kms_metrics(),
                media_type="text/plain; version=0.0.4; charset=utf-8",
            )

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

        # Seed system trust frameworks (idempotent)
        await self._seed_system_trust_frameworks(db_manager)

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
        
        # Wire status list service from marty-credentials
        status_list_svc = self._create_status_list_service(db_manager)
        
        # Wire status list serving endpoint
        from digital_identity.infrastructure.adapters.rest.status_list_router import (
            set_status_list_service,
        )
        if status_list_svc:
            set_status_list_service(status_list_svc)
        
        # Wire JWT issuer via bridge adapter
        jwt_issuer = self._create_jwt_issuer()
        
        issuance_service = CredentialIssuanceService(
            credential_repository=credential_repo,
            credential_template_repository=template_repo,
            revocation_batch_repository=batch_repo,
            status_list_service=status_list_svc,
            jwt_issuer=jwt_issuer,
            mdoc_issuer=None,  # mDoc local signing not yet supported by Rust bindings
        )
        if not status_list_svc or not jwt_issuer:
            stubs = []
            if not status_list_svc:
                stubs.append("status_list_service")
            if not jwt_issuer:
                stubs.append("jwt_issuer")
            logger.warning(
                "Credential issuance initialized with stubs: %s",
                ", ".join(stubs),
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
        
        # Wire licensing dependencies
        await self._configure_licensing()
        
        logger.info("Digital Identity plugin started successfully")
    
    def _create_status_list_service(
        self, db_manager: DigitalIdentityDatabaseManager
    ) -> Any | None:
        """Create StatusListService from marty-credentials, or None on failure."""
        try:
            from status_list.infrastructure.persistence.repository import (
                StatusListRepository,
                StatusEntryRepository,
            )
            from status_list.domain.value_objects import ShardConfig

            session_factory = db_manager.session_factory()
            status_list_repo = StatusListRepository(session_factory)
            status_entry_repo = StatusEntryRepository(session_factory)

            from status_list.application.services.status_list_service import (
                StatusListService,
            )

            svc = StatusListService(
                status_list_repository=status_list_repo,
                status_entry_repository=status_entry_repo,
                event_publisher=None,
                default_config=ShardConfig(),
            )
            logger.info("StatusListService wired successfully")
            return svc
        except Exception as e:
            logger.warning("Could not wire StatusListService: %s", e)
            return None

    def _create_jwt_issuer(self) -> Any | None:
        """Create JWT issuer bridge adapter, or None on failure."""
        try:
            from digital_identity.infrastructure.adapters.jwt_issuer_adapter import (
                JwtIssuerBridgeAdapter,
            )

            adapter = JwtIssuerBridgeAdapter()
            logger.info("JWT issuer bridge adapter wired successfully")
            return adapter
        except Exception as e:
            logger.warning("Could not wire JWT issuer: %s", e)
            return None

    async def _seed_system_trust_frameworks(
        self, db_manager: DigitalIdentityDatabaseManager
    ) -> None:
        """Seed system trust frameworks on startup (idempotent)."""
        from digital_identity.infrastructure.persistence.seed_system_trust_frameworks import (
            seed_system_trust_frameworks,
        )

        try:
            async with db_manager.session_scope() as session:
                await seed_system_trust_frameworks(session)
            logger.info("System trust frameworks seeded")
        except Exception as e:
            logger.warning(f"Failed to seed system trust frameworks: {e}")

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
    
    async def _configure_licensing(self) -> None:
        """Wire license service dependencies for route handlers."""
        try:
            from licensing.keys import LicenseKeyManager
            from licensing.service import LicenseIssuerService
            from licensing.registry import RegistryGatingService

            key_manager = LicenseKeyManager.from_env(allow_dev_keys=True)
            db_manager = get_database_manager()

            async def license_service_factory():
                session = db_manager.session_factory()()
                return LicenseIssuerService(db=session, key_manager=key_manager)

            def key_manager_factory():
                return key_manager

            async def registry_service_factory():
                session = db_manager.session_factory()()
                return RegistryGatingService(db=session)

            configure_license_dependencies(
                license_service_factory=license_service_factory,
                key_manager_factory=key_manager_factory,
                registry_service_factory=registry_service_factory,
            )

            # Wire usage metering
            from licensing.usage import UsageMeter
            usage_meter = UsageMeter()  # in-memory fallback; Redis injected when available
            configure_usage_dependencies(usage_meter)

            logger.info("Licensing dependencies configured")
        except Exception as e:
            logger.warning("Licensing service not available: %s", e)

        # Wire billing routes
        try:
            from subscription.square_service import SquareConfig, SquareService
            from licensing.subscription_bridge import SubscriptionLicenseBridge

            db_manager = get_database_manager()
            billing_config = self.config.get("square", {})
            square_config = SquareConfig(
                access_token=billing_config.get("access_token", ""),
                environment=billing_config.get("environment", "sandbox"),
                location_id=billing_config.get("location_id", ""),
                webhook_signature_key=billing_config.get("webhook_signature_key", ""),
            )

            async def square_service_factory():
                session = db_manager.session_factory()()
                bridge = None
                try:
                    from licensing.keys import LicenseKeyManager as _KM
                    km = _KM.from_env(allow_dev_keys=True)
                    bridge = SubscriptionLicenseBridge(db=session, key_manager=km)
                except Exception:
                    pass
                return SquareService(
                    config=square_config, db_session=session, license_bridge=bridge,
                )

            async def billing_db_session_factory():
                return db_manager.session_factory()()

            configure_billing_dependencies(
                square_service_factory=square_service_factory,
                db_session_factory=billing_db_session_factory,
            )
            logger.info("Billing dependencies configured")
        except Exception as e:
            logger.warning("Billing service not available: %s", e)

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
