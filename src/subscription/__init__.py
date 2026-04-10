"""
Subscription Module

Provides subscription management, API key services, Square billing integration,
tier-based signing with key vault access control, and KMS configuration for
remote signing operations.
"""
from importlib import import_module

from .models import (
    APIKey,
    Organization,
    Subscription,
    SubscriptionStatus,
    UsageRecord,
    WebhookEndpoint,
)


_LAZY_IMPORTS = {
    # api_key_service
    "APIKeyError": (".api_key_service", "APIKeyError"),
    "APIKeyInfo": (".api_key_service", "APIKeyInfo"),
    "APIKeyLimitError": (".api_key_service", "APIKeyLimitError"),
    "APIKeyService": (".api_key_service", "APIKeyService"),
    "InsufficientScopesError": (".api_key_service", "InsufficientScopesError"),
    "InvalidAPIKeyError": (".api_key_service", "InvalidAPIKeyError"),
    "InvalidIPError": (".api_key_service", "InvalidIPError"),
    "IPNotAllowedError": (".api_key_service", "IPNotAllowedError"),
    "RateLimitResult": (".api_key_service", "RateLimitResult"),
    # kms_config_service
    "KMSConfigError": (".kms_config_service", "KMSConfigError"),
    "KMSConfigService": (".kms_config_service", "KMSConfigService"),
    "KMSProviderConfig": (".kms_config_service", "KMSProviderConfig"),
    # remote_signing_service
    "RemoteSigningError": (".remote_signing_service", "RemoteSigningError"),
    "RemoteSigningService": (".remote_signing_service", "RemoteSigningService"),
    # audit
    "configure_audit_logging": (".audit", "configure_audit_logging"),
    # billing_routes
    "billing_router": (".billing_routes", "billing_router"),
    "configure_billing_dependencies": (".billing_routes", "configure_billing_dependencies"),
    # routes
    "router": (".routes", "router"),
    "api_key_router": (".routes", "api_key_router"),
    "webhook_router": (".routes", "webhook_router"),
    # signing_service
    "KeyRotationRequired": (".signing_service", "KeyRotationRequired"),
    "RemoteSigningRequired": (".signing_service", "RemoteSigningRequired"),
    "SigningError": (".signing_service", "SigningError"),
    "SigningKeyInfo": (".signing_service", "SigningKeyInfo"),
    "SigningKeyType": (".signing_service", "SigningKeyType"),
    "SigningService": (".signing_service", "SigningService"),
    "UnauthorizedKeyVaultAccess": (".signing_service", "UnauthorizedKeyVaultAccess"),
    # square_service
    "PLAN_LIMITS": (".square_service", "PLAN_LIMITS"),
    "PlanLimits": (".square_service", "PlanLimits"),
    "SquareConfig": (".square_service", "SquareConfig"),
    "SquareError": (".square_service", "SquareError"),
    "SquarePlan": (".square_service", "SquarePlan"),
    "SquareService": (".square_service", "SquareService"),
    # kms_router
    "kms_router": (".kms_router", "kms_router"),
}


def __getattr__(name: str):
    """Lazy-load heavyweight modules to keep lightweight imports test-friendly."""
    if name in _LAZY_IMPORTS:
        module_name, attr_name = _LAZY_IMPORTS[name]
        value = getattr(import_module(module_name, __name__), attr_name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    # Models
    "Organization",
    "Subscription",
    "SubscriptionStatus",
    "APIKey",
    "WebhookEndpoint",
    "UsageRecord",
    # Audit logging
    "configure_audit_logging",
    # Square service
    "SquareService",
    "SquareConfig",
    "SquarePlan",
    "PlanLimits",
    "PLAN_LIMITS",
    "SquareError",
    # API Key service
    "APIKeyService",
    "APIKeyInfo",
    "RateLimitResult",
    # Signing service
    "SigningService",
    "SigningKeyInfo",
    "SigningKeyType",
    "SigningError",
    "UnauthorizedKeyVaultAccess",
    "KeyRotationRequired",
    "RemoteSigningRequired",
    # KMS Configuration service
    "KMSConfigService",
    "KMSConfigError",
    "KMSProviderConfig",
    # Remote Signing service
    "RemoteSigningService",
    "RemoteSigningError",
    # Exceptions
    "APIKeyError",
    "InvalidAPIKeyError",
    "IPNotAllowedError",
    "InsufficientScopesError",
    "APIKeyLimitError",
    "InvalidIPError",
    # FastAPI routers
    "billing_router",
    "configure_billing_dependencies",
    "router",
    "api_key_router",
    "webhook_router",
    "kms_router",
]
