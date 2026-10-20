"""gRPC authentication backed by Rust JWT validation and verified TLS identity.

No caller metadata can create a trusted identity. Authorization consumes the
request-local context installed while the authenticated RPC handler executes.
"""

from __future__ import annotations

import inspect
import json
import logging
import os
from contextvars import ContextVar
from pathlib import Path
from typing import Any

import grpc
from grpc import aio as grpc_aio

from marty_common.native_backends import load_native_backend

LOGGER = logging.getLogger(__name__)


class AuthContext:
    """Authenticated request identity; claims come only from the trusted verifier."""

    def __init__(self, authenticated=False, identity=None, auth_method=None, claims=None):
        self.authenticated = authenticated
        self.identity = identity
        self.auth_method = auth_method
        self.claims = claims or {}


_REQUEST_AUTH: ContextVar[AuthContext | None] = ContextVar("marty_request_auth", default=None)


def get_auth_context() -> AuthContext | None:
    """Return the current handler's authenticated context, never invocation metadata."""
    return _REQUEST_AUTH.get()


class AuthServerInterceptor(grpc_aio.ServerInterceptor):
    """Authenticate every RPC shape and scope its identity to handler execution."""

    def __init__(
        self,
        jwt_secret: str | None = None,
        jwt_algorithm: str = "RS256",
        jwt_public_key: str | None = None,
        require_auth: bool = True,
        bypass_health_checks: bool = True,
        *,
        jwt_jwks: dict | str | None = None,
        jwt_issuer: str | None = None,
        jwt_audience: str | None = None,
        jwt_key_id: str | None = None,
    ):
        if not require_auth:
            raise ValueError("Authentication cannot be disabled; expose standard health RPCs separately")
        if jwt_secret is not None or jwt_algorithm.startswith("HS"):
            raise ValueError("Use Rust-validated asymmetric JWTs with public JWKS; shared-secret auth is retired")
        if jwt_public_key is not None and jwt_jwks is not None:
            raise ValueError("Supply public JWKS or a public PEM, not both")
        if jwt_public_key is not None:
            if not jwt_key_id:
                raise ValueError("Public PEM authentication requires a configured JWT key id")
            native = load_native_backend("marty_verification", ("public_key_pem_to_jwk",))
            public_jwk = json.loads(native.public_key_pem_to_jwk(jwt_public_key))
            public_jwk["kid"] = jwt_key_id
            jwt_jwks = {"keys": [public_jwk]}
        if jwt_jwks is not None:
            if not jwt_issuer or not jwt_audience:
                raise ValueError("JWT authentication requires issuer and audience")
            jwt_jwks = json.loads(jwt_jwks) if isinstance(jwt_jwks, str) else json.loads(json.dumps(jwt_jwks))
            if not isinstance(jwt_jwks, dict) or not isinstance(jwt_jwks.get("keys"), list) or not jwt_jwks["keys"]:
                raise ValueError("JWT authentication requires a nonempty public JWKS")
            private_members = {"d", "p", "q", "dp", "dq", "qi", "oth", "k", "rsa_d"}
            if any(not isinstance(key, dict) or private_members.intersection(key) for key in jwt_jwks["keys"]):
                raise ValueError("Authentication JWKS must contain public keys only")
        self.jwt_jwks = jwt_jwks
        self.jwt_algorithm = jwt_algorithm
        self.jwt_issuer = jwt_issuer
        self.jwt_audience = jwt_audience
        self.require_auth = True
        self.bypass_health_checks = bypass_health_checks

    async def intercept_service(self, continuation, handler_call_details):
        handler = await continuation(handler_call_details)
        if handler is None:
            return None

        async def authenticate(context):
            if self.bypass_health_checks and self._is_health_check(handler_call_details):
                return AuthContext()
            auth = await self._authenticate_request(handler_call_details, context)
            if not auth.authenticated:
                await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Authentication required")
                return None
            return auth

        behavior = (
            handler.stream_stream if handler.request_streaming and handler.response_streaming
            else handler.stream_unary if handler.request_streaming
            else handler.unary_stream if handler.response_streaming
            else handler.unary_unary
        )

        async def unary(request, context):
            auth = await authenticate(context)
            if auth is None:
                return None
            token = _REQUEST_AUTH.set(auth)
            try:
                response = behavior(request, context)
                return await response if inspect.isawaitable(response) else response
            finally:
                _REQUEST_AUTH.reset(token)

        async def streaming(request, context):
            auth = await authenticate(context)
            if auth is None:
                return
            token = _REQUEST_AUTH.set(auth)
            try:
                response = behavior(request, context)
                if inspect.isawaitable(response):
                    response = await response
                if response is None:  # A response-stream handler may use context.write().
                    return
                if hasattr(response, "__aiter__"):
                    async for item in response:
                        yield item
                else:
                    for item in response:
                        yield item
            finally:
                _REQUEST_AUTH.reset(token)

        factory = {
            (False, False): grpc.unary_unary_rpc_method_handler,
            (False, True): grpc.unary_stream_rpc_method_handler,
            (True, False): grpc.stream_unary_rpc_method_handler,
            (True, True): grpc.stream_stream_rpc_method_handler,
        }[(handler.request_streaming, handler.response_streaming)]
        return factory(
            streaming if handler.response_streaming else unary,
            request_deserializer=handler.request_deserializer,
            response_serializer=handler.response_serializer,
        )

    async def _authenticate_request(self, handler_call_details, grpc_context=None):
        values = [
            value for name, value in handler_call_details.invocation_metadata
            if name.lower() == "authorization"
        ]
        if values:
            if len(values) != 1:
                return AuthContext()
            value = values[0]
            if isinstance(value, bytes):
                try:
                    value = value.decode("ascii")
                except UnicodeDecodeError:
                    return AuthContext()
            # An invalid supplied credential never falls back to a different identity.
            return await self._authenticate_jwt({"authorization": value})
        return await self._authenticate_mtls(grpc_context)

    async def _authenticate_jwt(self, metadata):
        authorization = metadata.get("authorization", "")
        if not isinstance(authorization, str) or not authorization.startswith("Bearer ") or self.jwt_jwks is None:
            return AuthContext()
        try:
            native = load_native_backend("marty_rs", ("oidc_validate_id_token",))
            claims = json.loads(native.oidc_validate_id_token(json.dumps({
                "compact_jwt": authorization[7:],
                "jwks": self.jwt_jwks,
                "expected_issuer": self.jwt_issuer,
                "expected_audience": self.jwt_audience,
                "allowed_algorithms": [self.jwt_algorithm],
                "leeway_seconds": 0,
            })))
            identity = claims.get("sub")
            roles = claims.get("roles", [])
            if not isinstance(identity, str) or not identity or not isinstance(roles, list) or any(
                not isinstance(role, str) for role in roles
            ):
                return AuthContext()
            return AuthContext(True, identity, "jwt", claims)
        except Exception:
            # Never log the bearer credential or unverified claims on a failure.
            LOGGER.warning("Rust JWT authentication failed")
            return AuthContext()

    async def _authenticate_mtls(self, grpc_context):
        if grpc_context is None:
            return AuthContext()
        try:
            transport = grpc_context.auth_context()
            if b"ssl" not in transport.get("transport_security_type", []):
                return AuthContext()
            key = grpc_context.peer_identity_key()
            if key not in {"x509_subject_alternative_name", "x509_common_name", "x509_subject"}:
                return AuthContext()
            identities = grpc_context.peer_identities()
            if not identities or len(set(identities)) != 1:
                return AuthContext()
            identity = identities[0].decode("utf-8")
            if not identity:
                return AuthContext()
            # Certificate attributes are identity, never automatically privileged roles.
            return AuthContext(True, identity, "mtls", {"cert_subject": identity})
        except Exception:
            LOGGER.warning("Verified TLS identity extraction failed")
            return AuthContext()

    def _is_health_check(self, handler_call_details):
        return handler_call_details.method in {
            "/grpc.health.v1.Health/Check",
            "/grpc.health.v1.Health/Watch",
        }


def create_auth_interceptor(
    require_auth=None,
    jwt_secret=None,
    jwt_algorithm=None,
    jwt_public_key=None,
    *,
    jwt_jwks=None,
    jwt_issuer=None,
    jwt_audience=None,
    jwt_key_id=None,
):
    """Use configured public key material and policy; authentication is mandatory."""
    if require_auth is False:
        raise ValueError("Authentication cannot be disabled")
    jwks_file = os.environ.get("MARTY_JWT_JWKS_FILE")
    if jwt_jwks is None and jwks_file:
        jwt_jwks = Path(jwks_file).read_text(encoding="utf-8")
    jwt_public_key = jwt_public_key or os.environ.get("MARTY_JWT_PUBLIC_KEY")
    if jwt_public_key and os.path.isfile(jwt_public_key):
        jwt_public_key = Path(jwt_public_key).read_text(encoding="utf-8")
    return AuthServerInterceptor(
        jwt_secret=jwt_secret or os.environ.get("MARTY_JWT_SECRET"),
        jwt_algorithm=jwt_algorithm or os.environ.get("MARTY_JWT_ALGORITHM", "RS256"),
        jwt_public_key=jwt_public_key,
        jwt_jwks=jwt_jwks,
        jwt_issuer=jwt_issuer or os.environ.get("MARTY_JWT_ISSUER"),
        jwt_audience=jwt_audience or os.environ.get("MARTY_JWT_AUDIENCE"),
        jwt_key_id=jwt_key_id or os.environ.get("MARTY_JWT_KEY_ID"),
    )


__all__ = ["AuthContext", "AuthServerInterceptor", "create_auth_interceptor", "get_auth_context"]
