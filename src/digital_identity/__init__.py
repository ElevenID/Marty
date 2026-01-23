"""
Digital Identity API Layer

Implements the five core identity primitives:
- Trust Profile (TP): Who is trusted and how crypto validation occurs
- Credential Template (CT): What is issued (schema + semantics)
- Presentation Policy (PP): What must be shown (minimum disclosure)
- Deployment Profile (DP): Where it runs (device/site behavior)
- Flow (F): How identity moves (apply → issue → verify)

This module follows hexagonal architecture with:
- domain/: Entities, value objects, events
- application/: Ports (interfaces) and services
- infrastructure/: Adapters (REST, persistence, trust)
- plugin/: MMF integration

Quick Start:
    from digital_identity.plugin import register_plugin
    from fastapi import FastAPI
    
    app = FastAPI()
    plugin = register_plugin(app, config={"enabled": True})
    
    # In lifespan:
    await plugin.startup()
    # ... on shutdown:
    await plugin.shutdown()
"""

__version__ = "0.1.0"

# Main plugin registration
from digital_identity.plugin import DigitalIdentityPlugin, register_plugin

# Domain entities
from digital_identity.domain.entities import (
    TrustProfile,
    CredentialTemplate,
    PresentationPolicy,
    DeploymentProfile,
    Flow,
    FlowExecution,
)

# Value objects
from digital_identity.domain.value_objects import (
    TrustProfileType,
    FlowType,
    FlowStatus,
    ApprovalStrategy,
    ClaimDefinition,
    RevocationPolicy,
    TimePolicy,
    # CredentialRequirement,  # TODO: Add this value object
    # FlowHooks,  # TODO: Add this value object
    # EnvironmentConfig,  # TODO: Add this value object
)

# Database management
from digital_identity.infrastructure.persistence import (
    init_database,
    close_database,
    get_database_manager,
)

__all__ = [
    # Version
    "__version__",
    # Plugin
    "DigitalIdentityPlugin",
    "register_plugin",
    # Entities
    "TrustProfile",
    "CredentialTemplate",
    "PresentationPolicy",
    "DeploymentProfile",
    "Flow",
    "FlowExecution",
    # Value Objects
    "TrustProfileType",
    "FlowType",
    "FlowStatus",
    "ApprovalStrategy",
    "ClaimDefinition",
    "RevocationPolicy",
    "TimePolicy",
    # "CredentialRequirement",  # TODO
    # "FlowHooks",  # TODO
    # "EnvironmentConfig",  # TODO
    # Database
    "init_database",
    "close_database",
    "get_database_manager",
]
