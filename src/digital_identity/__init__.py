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

from importlib import import_module

__version__ = "0.1.0"


_LAZY_IMPORTS = {
    # Plugin
    "DigitalIdentityPlugin": ("digital_identity.plugin", "DigitalIdentityPlugin"),
    "register_plugin": ("digital_identity.plugin", "register_plugin"),
    # Entities
    "TrustProfile": ("digital_identity.domain.entities", "TrustProfile"),
    "CredentialTemplate": ("digital_identity.domain.entities", "CredentialTemplate"),
    "PresentationPolicy": ("digital_identity.domain.entities", "PresentationPolicy"),
    "DeploymentProfile": ("digital_identity.domain.entities", "DeploymentProfile"),
    "Flow": ("digital_identity.domain.entities", "Flow"),
    "FlowExecution": ("digital_identity.domain.entities", "FlowExecution"),
    # Value objects
    "TrustProfileType": ("digital_identity.domain.value_objects", "TrustProfileType"),
    "FlowType": ("digital_identity.domain.value_objects", "FlowType"),
    "FlowStatus": ("digital_identity.domain.value_objects", "FlowStatus"),
    "ApprovalStrategy": ("digital_identity.domain.value_objects", "ApprovalStrategy"),
    "ClaimDefinition": ("digital_identity.domain.value_objects", "ClaimDefinition"),
    "RevocationPolicy": ("digital_identity.domain.value_objects", "RevocationPolicy"),
    "TimePolicy": ("digital_identity.domain.value_objects", "TimePolicy"),
    # Database management
    "init_database": ("digital_identity.infrastructure.persistence", "init_database"),
    "close_database": ("digital_identity.infrastructure.persistence", "close_database"),
    "get_database_manager": ("digital_identity.infrastructure.persistence", "get_database_manager"),
}


def __getattr__(name: str):
    """Lazy-load digital identity exports so subpackage imports stay lightweight."""
    if name in _LAZY_IMPORTS:
        module_name, attr_name = _LAZY_IMPORTS[name]
        value = getattr(import_module(module_name), attr_name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

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
