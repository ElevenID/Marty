"""
Subscription Module

Provides subscription management, API key services, and Square billing integration.
"""
from .api_key_service import (
    APIKeyError,
    APIKeyInfo,
    APIKeyLimitError,
    APIKeyService,
    InsufficientScopesError,
    InvalidAPIKeyError,
    InvalidIPError,
    IPNotAllowedError,
    RateLimitResult,
)
from .models import (
    APIKey,
    Organization,
    Subscription,
    SubscriptionStatus,
    UsageRecord,
    WebhookEndpoint,
)
from .routes import (
    api_key_router,
    router,
    webhook_router,
)
from .square_service import (
    PLAN_LIMITS,
    PlanLimits,
    SquareConfig,
    SquareError,
    SquarePlan,
    SquareService,
)

__all__ = [
    # Models
    "Organization",
    "Subscription",
    "SubscriptionStatus",
    "APIKey",
    "WebhookEndpoint",
    "UsageRecord",
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
    # Exceptions
    "APIKeyError",
    "InvalidAPIKeyError",
    "IPNotAllowedError",
    "InsufficientScopesError",
    "APIKeyLimitError",
    "InvalidIPError",
    # FastAPI routers
    "router",
    "api_key_router",
    "webhook_router",
]
