"""Authentication interceptor for gRPC services.

This module provides authentication interceptors that support:
- JWT Bearer token validation (HS256/RS256)
- mTLS client certificate identity extraction
- Configurable authentication modes based on environment
"""

from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any

import grpc
import jwt
from grpc import aio as grpc_aio

# Use Rust crypto_bridge for certificate operations
from marty_common.crypto_bridge import Certificate

LOGGER = logging.getLogger(__name__)


class AuthContext:
    """Authentication context extracted from the request."""

    def __init__(
        self,
        authenticated: bool = False,
        identity: str | None = None,
        auth_method: str | None = None,
        claims: dict[str, Any] | None = None,
    ) -> None:
        self.authenticated = authenticated
        self.identity = identity
        self.auth_method = auth_method
        self.claims = claims or {}


class AuthServerInterceptor(grpc_aio.ServerInterceptor):
    """Authentication interceptor for gRPC servers.

    Supports multiple authentication methods:
    - JWT Bearer tokens (Authorization header)
    - mTLS client certificate DN extraction
    - Optional authentication bypass for health checks
    """

    def __init__(
        self,
        jwt_secret: str | None = None,
        jwt_algorithm: str = "HS256",
        jwt_public_key: str | None = None,
        require_auth: bool = True,
        bypass_health_checks: bool = True,
    ) -> None:
        """Initialize the authentication interceptor.

        Args:
            jwt_secret: Secret key for HS256 JWT validation
            jwt_algorithm: JWT algorithm (HS256, RS256, etc.)
            jwt_public_key: Public key for RS256 JWT validation
            require_auth: Whether authentication is required
            bypass_health_checks: Whether to bypass auth for health check endpoints
        """
        self.jwt_secret = jwt_secret
        self.jwt_algorithm = jwt_algorithm
        self.jwt_public_key = jwt_public_key
        self.require_auth = require_auth
        self.bypass_health_checks = bypass_health_checks

    async def intercept_service(
        self,
        continuation,
        handler_call_details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler:
        """Intercept gRPC service calls to perform authentication."""

        # Skip authentication for health checks if configured
        if self.bypass_health_checks and self._is_health_check(handler_call_details):
            return await continuation(handler_call_details)

        auth_context = await self._authenticate_request(handler_call_details)

        # If authentication is required but failed, reject the request
        if self.require_auth and not auth_context.authenticated:
            return self._create_unauthenticated_handler()

        # Add auth context to invocation metadata for service access
        self._add_auth_context_to_metadata(handler_call_details, auth_context)

        return await continuation(handler_call_details)

    async def _authenticate_request(
        self, handler_call_details: grpc.HandlerCallDetails
    ) -> AuthContext:
        """Authenticate the incoming request using available methods."""

        metadata = {
            key: str(value.decode() if isinstance(value, bytes) else value)
            for key, value in handler_call_details.invocation_metadata
        }

        # Try JWT authentication first
        auth_context = await self._authenticate_jwt(metadata)
        if auth_context.authenticated:
            return auth_context

        # Try mTLS authentication if JWT failed
        auth_context = await self._authenticate_mtls(metadata)
        if auth_context.authenticated:
            return auth_context

        # No authentication succeeded
        return AuthContext(authenticated=False)

    async def _authenticate_jwt(self, metadata: dict[str, str]) -> AuthContext:
        """Authenticate using JWT Bearer token."""

        authorization = metadata.get("authorization", "")
        if not authorization.startswith("Bearer "):
            return AuthContext(authenticated=False)

        token = authorization[7:]  # Remove "Bearer " prefix

        try:
            # Determine the key to use for validation
            key = self._get_jwt_validation_key()
            if not key:
                LOGGER.warning("JWT authentication configured but no validation key available")
                return AuthContext(authenticated=False)

            # Decode and validate the JWT
            claims = jwt.decode(token, key, algorithms=[self.jwt_algorithm])

            identity = claims.get("sub") or claims.get("user_id") or claims.get("email")
            if not identity:
                LOGGER.warning("JWT token missing identity claim")
                return AuthContext(authenticated=False)

            LOGGER.debug("Successfully authenticated JWT for identity: %s", identity)
            return AuthContext(
                authenticated=True,
                identity=str(identity),
                auth_method="jwt",
                claims=claims,
            )

        except jwt.InvalidTokenError as e:
            LOGGER.warning("JWT validation failed: %s", str(e))
            return AuthContext(authenticated=False)
        except Exception as e:
            LOGGER.error("Unexpected error during JWT validation: %s", str(e))
            return AuthContext(authenticated=False)

    async def _authenticate_mtls(self, metadata: dict[str, str]) -> AuthContext:
        """Authenticate using mTLS client certificate DN."""

        # Look for client certificate information in metadata
        # This would typically be populated by the gRPC TLS layer
        client_cert_pem = metadata.get("x-client-cert", "")
        client_cert_subject = metadata.get("x-client-cert-subject", "")

        # If we have a direct subject, use it
        if client_cert_subject:
            LOGGER.debug("mTLS authentication using provided subject: %s", client_cert_subject)
            return AuthContext(
                authenticated=True,
                identity=client_cert_subject,
                auth_method="mtls",
                claims={"cert_subject": client_cert_subject},
            )

        # If we have a PEM certificate, extract the subject
        if client_cert_pem:
            try:
                # Decode base64 if necessary
                if not client_cert_pem.startswith("-----BEGIN"):
                    client_cert_pem = base64.b64decode(client_cert_pem).decode("utf-8")

                # Use Rust crypto_bridge for certificate parsing
                cert = Certificate.from_pem(client_cert_pem)
                subject = cert.subject

                LOGGER.debug("mTLS authentication using extracted subject: %s", subject)
                return AuthContext(
                    authenticated=True,
                    identity=subject,
                    auth_method="mtls",
                    claims={"cert_subject": subject},
                )

            except Exception as e:
                LOGGER.warning("Failed to parse client certificate: %s", str(e))
                return AuthContext(authenticated=False)

        return AuthContext(authenticated=False)

    def _get_jwt_validation_key(self) -> str | None:
        """Get the appropriate key for JWT validation based on algorithm."""

        if self.jwt_algorithm.startswith("HS"):
            return self.jwt_secret
        elif self.jwt_algorithm.startswith("RS") or self.jwt_algorithm.startswith("ES"):
            return self.jwt_public_key
        else:
            LOGGER.error("Unsupported JWT algorithm: %s", self.jwt_algorithm)
            return None

    def _is_health_check(self, handler_call_details: grpc.HandlerCallDetails) -> bool:
        """Check if the request is a health check endpoint."""
        method = handler_call_details.method
        if not method:
            return False
        return any(
            health_pattern in method
            for health_pattern in ["/grpc.health.v1.Health/", "/health", "/status"]
        )

    def _create_unauthenticated_handler(self) -> grpc.RpcMethodHandler:
        """Create a handler that returns UNAUTHENTICATED status."""

        def unauthenticated_handler(_request, context):
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "Authentication required")

        return grpc.unary_unary_rpc_method_handler(unauthenticated_handler)

    def _add_auth_context_to_metadata(
        self,
        handler_call_details: grpc.HandlerCallDetails,
        auth_context: AuthContext,
    ) -> None:
        """Add authentication context to request metadata for service access."""

        # Note: In practice, this would require a custom context mechanism
        # since gRPC metadata is immutable once created. Services can access
        # the auth context through context.invocation_metadata() and parse
        # the authorization header or client cert metadata themselves.
        # This is a placeholder for future context management enhancements.
        del handler_call_details, auth_context  # Acknowledge unused parameters


def create_auth_interceptor(
    require_auth: bool | None = None,
    jwt_secret: str | None = None,
    jwt_algorithm: str | None = None,
    jwt_public_key: str | None = None,
) -> AuthServerInterceptor:
    """Create an authentication interceptor with configuration from environment.

    Args:
        require_auth: ALWAYS True - no backward compatibility
        jwt_secret: Override for JWT secret
        jwt_algorithm: Override for JWT algorithm
        jwt_public_key: Override for JWT public key

    Returns:
        Configured AuthServerInterceptor
    """

    # Authentication is ALWAYS required - no backward compatibility
    require_auth = True

    jwt_secret = jwt_secret or os.environ.get("MARTY_JWT_SECRET")
    jwt_algorithm = jwt_algorithm or os.environ.get("MARTY_JWT_ALGORITHM", "HS256")
    jwt_public_key = jwt_public_key or os.environ.get("MARTY_JWT_PUBLIC_KEY")

    # Read JWT public key from file if path is provided
    if jwt_public_key and os.path.isfile(jwt_public_key):
        try:
            with open(jwt_public_key, encoding="utf-8") as f:
                jwt_public_key = f.read()
        except OSError as e:
            LOGGER.warning("Failed to read JWT public key file: %s", str(e))
            jwt_public_key = None

    return AuthServerInterceptor(
        jwt_secret=jwt_secret,
        jwt_algorithm=jwt_algorithm,
        jwt_public_key=jwt_public_key,
        require_auth=require_auth,
        bypass_health_checks=True,
    )


__all__ = [
    "AuthContext",
    "AuthServerInterceptor",
    "create_auth_interceptor",
]
