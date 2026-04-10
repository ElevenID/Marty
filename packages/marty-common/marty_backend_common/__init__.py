"""
Marty Common package - shared infrastructure for Marty digital identity services.

This package contains common infrastructure functionality used across the Marty ecosystem:
- Cryptography bridge (crypto_bridge.py)
- gRPC infrastructure
- Database utilities  
- Configuration management
- Observability and monitoring
- Security and validation
"""

__version__ = "0.1.0"

from .exceptions import (
    AuthenticationError,
    ConfigurationError,
    InvalidInputError,
    MartyServiceException,
    OperationFailedError,
    ResourceNotFoundError,
    ServiceCommunicationError,
)

from .authorization import (
    AuthorizationContext,
    AuthorizationError as AuthzError,
    AuthzDecision,
    PolicyEngine,
    PolicyEvaluationError,
    require,
)

__all__ = [
    "AuthenticationError",
    "ConfigurationError",
    "InvalidInputError",
    "MartyServiceException",
    "OperationFailedError",
    "ResourceNotFoundError",
    "ServiceCommunicationError",
    # Cedar Authorization
    "AuthorizationContext",
    "AuthzError",
    "AuthzDecision",
    "PolicyEngine",
    "PolicyEvaluationError",
    "require",
]
