"""gRPC authentication backed by verified TLS identity.

No caller metadata can create a trusted identity. Authorization consumes the
request-local context installed while the authenticated RPC handler executes.
"""

from __future__ import annotations

import inspect
import logging
import os
from contextvars import ContextVar

import grpc
from grpc import aio as grpc_aio


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
        if any(value is not None for value in (
            jwt_secret, jwt_public_key, jwt_jwks, jwt_issuer, jwt_audience, jwt_key_id
        )) or jwt_algorithm != "RS256":
            raise ValueError(
                "Python JWT authentication is retired; use the Rust service authentication owner"
            )
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

        def authenticate_sync(context):
            if self.bypass_health_checks and self._is_health_check(handler_call_details):
                return AuthContext()
            auth = self._authenticate_request_sync(handler_call_details, context)
            if not auth.authenticated:
                context.abort(grpc.StatusCode.UNAUTHENTICATED, "Authentication required")
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

        def sync_unary(request, context):
            auth = authenticate_sync(context)
            if auth is None:
                return None
            token = _REQUEST_AUTH.set(auth)
            try:
                return behavior(request, context)
            finally:
                _REQUEST_AUTH.reset(token)

        def sync_streaming(request, context):
            auth = authenticate_sync(context)
            if auth is None:
                return
            token = _REQUEST_AUTH.set(auth)
            try:
                yield from behavior(request, context)
            finally:
                _REQUEST_AUTH.reset(token)

        factory = {
            (False, False): grpc.unary_unary_rpc_method_handler,
            (False, True): grpc.unary_stream_rpc_method_handler,
            (True, False): grpc.stream_unary_rpc_method_handler,
            (True, True): grpc.stream_stream_rpc_method_handler,
        }[(handler.request_streaming, handler.response_streaming)]
        asynchronous = inspect.iscoroutinefunction(behavior) or inspect.isasyncgenfunction(behavior)
        wrapped = (streaming if handler.response_streaming else unary) if asynchronous else (
            sync_streaming if handler.response_streaming else sync_unary
        )
        return factory(
            wrapped,
            request_deserializer=handler.request_deserializer,
            response_serializer=handler.response_serializer,
        )

    async def _authenticate_request(self, handler_call_details, grpc_context=None):
        return self._authenticate_request_sync(handler_call_details, grpc_context)

    def _authenticate_request_sync(self, handler_call_details, grpc_context=None):
        values = [
            value for name, value in handler_call_details.invocation_metadata
            if name.lower() == "authorization"
        ]
        if values:
            # Supplying any removed bearer/JWT credential is an authentication
            # failure, even if a valid client certificate is also present.
            return AuthContext()
        return self._authenticate_mtls_sync(grpc_context)



    async def _authenticate_mtls(self, grpc_context):
        return self._authenticate_mtls_sync(grpc_context)

    def _authenticate_mtls_sync(self, grpc_context):
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
    """Create mandatory mTLS authentication; reject retired JWT configuration."""
    if require_auth is False:
        raise ValueError("Authentication cannot be disabled")
    # Reject retired mode selection without reading any configured key/JWKS file.
    if jwt_jwks is None:
        jwt_jwks = os.environ.get("MARTY_JWT_JWKS_FILE")
    jwt_public_key = jwt_public_key or os.environ.get("MARTY_JWT_PUBLIC_KEY")
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
