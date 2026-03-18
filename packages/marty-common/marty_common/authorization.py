"""Authorization system with Cedar policy evaluation for Marty services.

This module provides:
- Cedar-backed policy engine (replaces YAML RBAC/ABAC)
- Authorization guard decorators for gRPC service methods
- Authentication context extraction from gRPC metadata

Cedar policies are evaluated via cedarpy (PyO3 binding to the Rust
cedar-policy crate, ~100μs per evaluation). Role definitions live in
cedar/backend_policies.cedar rather than YAML config.
"""

from __future__ import annotations

import asyncio
import functools
import json
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

import cedarpy

LOGGER = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

_CEDAR_DIR = Path(__file__).parent / "cedar"


class AuthorizationError(Exception):
    """Raised when authorization fails."""


class PolicyEvaluationError(Exception):
    """Raised when policy evaluation encounters an error."""


@dataclass(frozen=True)
class AuthzDecision:
    """Result of a Cedar authorization evaluation."""

    allowed: bool
    reasons: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class AuthorizationContext:
    """Context for authorization decisions."""

    def __init__(
        self,
        identity: str | None = None,
        roles: list[str] | None = None,
        attributes: dict[str, Any] | None = None,
        resource: str | None = None,
        action: str | None = None,
    ) -> None:
        self.identity = identity
        self.roles = roles or []
        self.attributes = attributes or {}
        self.resource = resource
        self.action = action


class PolicyEngine:
    """Cedar-backed policy engine for evaluating authorization rules.

    Replaces the previous YAML-based RBAC/ABAC engine with Cedar policy
    evaluation via cedarpy.
    """

    def __init__(
        self,
        schema: str | None = None,
        policies: str | None = None,
    ) -> None:
        if schema is None or policies is None:
            default_schema, default_policies = _load_default_cedar_config()
            schema = schema or default_schema
            policies = policies or default_policies
        self._schema = schema
        self._policies = policies

    @classmethod
    def from_files(
        cls,
        schema_path: str | Path,
        policy_paths: list[str | Path],
    ) -> PolicyEngine:
        """Load schema and policies from filesystem paths."""
        schema = Path(schema_path).read_text()
        policy_parts: list[str] = []
        for p in policy_paths:
            path = Path(p)
            if path.is_dir():
                for f in sorted(path.glob("*.cedar")):
                    policy_parts.append(f.read_text())
            elif path.exists():
                policy_parts.append(path.read_text())
        return cls(schema=schema, policies="\n\n".join(policy_parts))

    @classmethod
    def with_defaults(cls) -> PolicyEngine:
        """Create engine with bundled backend schema and default policies."""
        return cls()

    @property
    def policies(self) -> str:
        return self._policies

    @policies.setter
    def policies(self, value: str) -> None:
        self._policies = value

    def evaluate(self, context: AuthorizationContext) -> bool:
        """Evaluate authorization for the given context using Cedar.

        Converts AuthorizationContext to Cedar entities and request,
        then evaluates against loaded Cedar policies.

        Returns:
            True if authorized, False otherwise.
        """
        try:
            if not context.identity:
                return False

            if not context.action:
                return False

            entities = _build_entities(context)
            principal = f'MIP::User::"{context.identity}"'
            action = f'MIP::Action::"{context.action}"'
            resource = f'MIP::ServiceResource::"{context.resource or "default"}"'
            cedar_context = {
                "ip_address": {"__extn": {"fn": "ip", "arg": context.attributes.get("ip_address", "0.0.0.0")}},
                "timestamp": int(time.time()),
                "mfa_authenticated": context.attributes.get("mfa_authenticated", False),
            }

            request = {
                "principal": principal,
                "action": action,
                "resource": resource,
                "context": cedar_context,
            }

            result = cedarpy.is_authorized(
                request, self._policies, json.dumps(entities), self._schema
            )

            if result.diagnostics.errors:
                for err in result.diagnostics.errors:
                    LOGGER.warning("Cedar evaluation diagnostic: %s", err)

            return result.allowed

        except Exception as e:
            LOGGER.error("Cedar policy evaluation error: %s", str(e))
            raise PolicyEvaluationError(f"Policy evaluation failed: {str(e)}") from e

    def is_authorized(
        self,
        principal: str,
        action: str,
        resource: str,
        context: dict[str, Any],
        entities: list[dict[str, Any]],
    ) -> AuthzDecision:
        """Raw Cedar authorization evaluation.

        For cases where callers need full control over the Cedar request
        (typed entities, specific context records, etc.).
        """
        request = {
            "principal": principal,
            "action": action,
            "resource": resource,
            "context": context,
        }
        try:
            result = cedarpy.is_authorized(
                request, self._policies, json.dumps(entities), self._schema
            )
            return AuthzDecision(
                allowed=result.allowed,
                reasons=list(result.diagnostics.reasons)
                if result.diagnostics.reasons
                else [],
                errors=list(result.diagnostics.errors)
                if result.diagnostics.errors
                else [],
            )
        except Exception as e:
            LOGGER.error("Cedar evaluation error: %s", e, exc_info=True)
            return AuthzDecision(allowed=False, errors=[str(e)])


def _build_entities(context: AuthorizationContext) -> list[dict[str, Any]]:
    """Build Cedar entity list from an AuthorizationContext."""
    entities: list[dict[str, Any]] = []

    # Role entities
    user_parents: list[dict[str, str]] = []
    for role in context.roles:
        role_id = role.lower()
        user_parents.append({"type": "MIP::Role", "id": role_id})
        entities.append(
            {
                "uid": {"type": "MIP::Role", "id": role_id},
                "attrs": {"is_system_role": True},
                "parents": [],
            }
        )

    # User entity
    entities.append(
        {
            "uid": {"type": "MIP::User", "id": context.identity},
            "attrs": {
                "email": context.attributes.get("email", ""),
                "status": context.attributes.get("status", "ACTIVE"),
            },
            "parents": user_parents,
        }
    )

    # ServiceResource entity
    entities.append(
        {
            "uid": {
                "type": "MIP::ServiceResource",
                "id": context.resource or "default",
            },
            "attrs": {},
            "parents": [],
        }
    )

    return entities


def _load_default_cedar_config() -> tuple[str, str]:
    """Load bundled Cedar schema and policies.

    Checks CEDAR_SCHEMA_PATH and CEDAR_POLICIES_DIR env vars first,
    then falls back to bundled defaults.
    """
    schema_path = os.environ.get("CEDAR_SCHEMA_PATH")
    policies_dir = os.environ.get("CEDAR_POLICIES_DIR")

    if schema_path and Path(schema_path).exists():
        schema = Path(schema_path).read_text()
    else:
        schema = (_CEDAR_DIR / "mip_backend.cedarschema").read_text()

    if policies_dir and Path(policies_dir).is_dir():
        parts = []
        for f in sorted(Path(policies_dir).glob("*.cedar")):
            parts.append(f.read_text())
        policies = "\n\n".join(parts)
    else:
        policies = (_CEDAR_DIR / "backend_policies.cedar").read_text()

    return schema, policies


def require(
    permission: str,
    resource: str | None = None,
    policy_engine: PolicyEngine | None = None,
) -> Callable[[F], F]:
    """Decorator to require specific permissions for a gRPC method.

    Args:
        permission: Required Cedar action (e.g., "document:sign").
        resource: Optional resource identifier.
        policy_engine: Optional PolicyEngine instance (uses default if None).

    Returns:
        Decorator function.
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            grpc_context = _find_grpc_context(args)
            auth_context = _extract_auth_context(grpc_context)

            authz_context = AuthorizationContext(
                identity=auth_context["identity"],
                roles=auth_context["roles"],
                attributes=auth_context["attributes"],
                resource=resource or _extract_resource_from_method(func),
                action=permission,
            )

            engine = policy_engine or _get_default_policy_engine()
            if not engine.evaluate(authz_context):
                raise AuthorizationError(f"Access denied for permission: {permission}")

            return await func(*args, **kwargs)

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            grpc_context = _find_grpc_context(args)
            auth_context = _extract_auth_context(grpc_context)

            authz_context = AuthorizationContext(
                identity=auth_context["identity"],
                roles=auth_context["roles"],
                attributes=auth_context["attributes"],
                resource=resource or _extract_resource_from_method(func),
                action=permission,
            )

            engine = policy_engine or _get_default_policy_engine()
            if not engine.evaluate(authz_context):
                raise AuthorizationError(f"Access denied for permission: {permission}")

            return func(*args, **kwargs)

        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore[return-value]
        return sync_wrapper  # type: ignore[return-value]

    return decorator


def _find_grpc_context(args: tuple[Any, ...]) -> Any:
    """Locate the gRPC ServicerContext in a method's positional args."""
    for arg in reversed(args):
        if hasattr(arg, "invocation_metadata"):
            return arg
    raise AuthorizationError("gRPC context not found")


def _extract_auth_context(grpc_context: Any) -> dict[str, Any]:
    """Extract authentication context from gRPC metadata."""
    metadata = dict(grpc_context.invocation_metadata())

    identity = None
    roles: list[str] = []
    attributes: dict[str, Any] = {}

    # Try JWT from Authorization header
    auth_header = metadata.get("authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            import jwt  # type: ignore[import-untyped]

            token = auth_header[7:]
            claims = jwt.decode(token, options={"verify_signature": False})
            identity = claims.get("sub") or claims.get("user_id")
            roles = claims.get("roles", [])
            attributes = {
                k: v for k, v in claims.items() if k not in ("sub", "user_id", "roles")
            }
        except Exception:
            pass

    # Fall back to client certificate subject
    if not identity:
        client_cert_subject = metadata.get("x-client-cert-subject", "")
        if client_cert_subject:
            identity = client_cert_subject
            if "ou=" in client_cert_subject.lower():
                roles = [client_cert_subject.split("ou=")[1].split(",")[0]]

    return {"identity": identity, "roles": roles, "attributes": attributes}


def _extract_resource_from_method(func: Callable[..., Any]) -> str:
    """Extract resource name from method name or class."""
    if hasattr(func, "__qualname__"):
        parts = func.__qualname__.split(".")
        if len(parts) > 1:
            class_name = parts[-2]
            for suffix in ("Service", "Servicer"):
                if class_name.endswith(suffix):
                    class_name = class_name[: -len(suffix)]
                    break
            return class_name.lower()
    return func.__name__


# Global policy engine instance
_default_policy_engine: PolicyEngine | None = None


def _get_default_policy_engine() -> PolicyEngine:
    """Get or create the default policy engine."""
    global _default_policy_engine  # noqa: PLW0603

    if _default_policy_engine is None:
        _default_policy_engine = PolicyEngine()

    return _default_policy_engine


__all__ = [
    "AuthorizationError",
    "AuthzDecision",
    "PolicyEvaluationError",
    "AuthorizationContext",
    "PolicyEngine",
    "require",
]
