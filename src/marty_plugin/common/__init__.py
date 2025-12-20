"""
Marty Common package - shared library for code used across all Marty services.

This package contains common functionality that is used by multiple services in the Marty ecosystem.
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

__all__ = [
    "AuthenticationError",
    "ConfigurationError",
    "InvalidInputError",
    "MartyServiceException",
    "OperationFailedError",
    "ResourceNotFoundError",
    "ServiceCommunicationError",
    # ... other exports
]
