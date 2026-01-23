"""Authorization system with RBAC/ABAC support for Marty services.

This module provides:
- Role-based access control (RBAC) decorators
- Attribute-based access control (ABAC) policies
- Policy configuration loading and validation
- Authorization guard decorators for service methods
"""

from __future__ import annotations

import functools
import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar, Union

import grpc
import yaml
from grpc import aio as grpc_aio

LOGGER = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


class AuthorizationError(Exception):
    """Raised when authorization fails."""


class PolicyEvaluationError(Exception):
    """Raised when policy evaluation encounters an error."""


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
    """Policy engine for evaluating authorization rules."""

    def __init__(self, policy_config: dict[str, Any] | None = None) -> None:
        """Initialize the policy engine with configuration.

        Args:
            policy_config: Policy configuration dictionary
        """
        self.config = policy_config or {}
        self.policies = self.config.get("policies", {})
        self.roles = self.config.get("roles", {})
        self.default_action = self.config.get("default_action", "deny")

    def evaluate(self, context: AuthorizationContext) -> bool:
        """Evaluate authorization for the given context.

        Args:
            context: Authorization context containing identity, roles, etc.

        Returns:
            True if authorized, False otherwise
        """
        try:
            # If no identity, deny access (unless explicitly allowed)
            if not context.identity:
                return self._evaluate_anonymous_access(context)

            # Check role-based permissions
            if self._evaluate_rbac(context):
                return True

            # Check attribute-based permissions
            if self._evaluate_abac(context):
                return True

            # Check resource-specific policies
            if context.resource and self._evaluate_resource_policy(context):
                return True

            # Fall back to default action
            return self.default_action == "allow"

        except Exception as e:
            LOGGER.error("Policy evaluation error: %s", str(e))
            raise PolicyEvaluationError(f"Policy evaluation failed: {str(e)}") from e

    def _evaluate_anonymous_access(self, context: AuthorizationContext) -> bool:
        """Evaluate access for anonymous (unauthenticated) requests."""
        anonymous_policy = self.policies.get("anonymous", {})
        allowed_actions = anonymous_policy.get("allowed_actions", [])

        if context.action and context.action in allowed_actions:
            return True

        allowed_resources = anonymous_policy.get("allowed_resources", [])
        if context.resource and context.resource in allowed_resources:
            return True

        return False

    def _evaluate_rbac(self, context: AuthorizationContext) -> bool:
        """Evaluate role-based access control."""
        if not context.roles:
            return False

        for role in context.roles:
            role_config = self.roles.get(role, {})

            # Check allowed actions
            allowed_actions = role_config.get("allowed_actions", [])
            if context.action and context.action in allowed_actions:
                return True

            # Check allowed resources
            allowed_resources = role_config.get("allowed_resources", [])
            if context.resource and context.resource in allowed_resources:
                return True

            # Check resource-action combinations
            permissions = role_config.get("permissions", [])
            for permission in permissions:
                if self._match_permission(permission, context):
                    return True

        return False

    def _evaluate_abac(self, context: AuthorizationContext) -> bool:
        """Evaluate attribute-based access control."""
        abac_policies = self.policies.get("abac", [])

        for policy in abac_policies:
            if self._evaluate_abac_policy(policy, context):
                return True

        return False

    def _evaluate_resource_policy(self, context: AuthorizationContext) -> bool:
        """Evaluate resource-specific policies."""
        if not context.resource:
            return False

        resource_policies = self.policies.get("resources", {})
        resource_policy = resource_policies.get(context.resource, {})

        if not resource_policy:
            return False

        # Check if the action is allowed for this resource
        allowed_actions = resource_policy.get("allowed_actions", [])
        if context.action and context.action in allowed_actions:
            return True

        # Check conditions
        conditions = resource_policy.get("conditions", [])
        for condition in conditions:
            if self._evaluate_condition(condition, context):
                return True

        return False

    def _match_permission(self, permission: dict[str, Any], context: AuthorizationContext) -> bool:
        """Check if a permission matches the current context."""
        # Match resource pattern
        resource_pattern = permission.get("resource")
        if resource_pattern and context.resource:
            if not self._match_pattern(resource_pattern, context.resource):
                return False

        # Match action pattern
        action_pattern = permission.get("action")
        if action_pattern and context.action:
            if not self._match_pattern(action_pattern, context.action):
                return False

        # Evaluate conditions
        conditions = permission.get("conditions", [])
        for condition in conditions:
            if not self._evaluate_condition(condition, context):
                return False

        return True

    def _evaluate_abac_policy(self, policy: dict[str, Any], context: AuthorizationContext) -> bool:
        """Evaluate a single ABAC policy."""
        # Check if the policy applies to this context
        target = policy.get("target", {})

        if not self._match_target(target, context):
            return False

        # Evaluate the policy rules
        rules = policy.get("rules", [])
        effect = policy.get("effect", "deny")

        for rule in rules:
            if self._evaluate_rule(rule, context):
                return effect == "allow"

        return False

    def _evaluate_condition(self, condition: dict[str, Any], context: AuthorizationContext) -> bool:
        """Evaluate a single condition."""
        condition_type = condition.get("type")

        if condition_type == "attribute":
            return self._evaluate_attribute_condition(condition, context)
        elif condition_type == "time":
            return self._evaluate_time_condition(condition, context)
        elif condition_type == "identity":
            return self._evaluate_identity_condition(condition, context)
        else:
            LOGGER.warning("Unknown condition type: %s", condition_type)
            return False

    def _evaluate_attribute_condition(
        self, condition: dict[str, Any], context: AuthorizationContext
    ) -> bool:
        """Evaluate an attribute-based condition."""
        attribute_name = condition.get("attribute")
        expected_value = condition.get("value")
        operator = condition.get("operator", "equals")

        if not attribute_name:
            return False

        actual_value = context.attributes.get(attribute_name)

        if operator == "equals":
            return actual_value == expected_value
        elif operator == "not_equals":
            return actual_value != expected_value
        elif operator == "in":
            return actual_value in expected_value if isinstance(expected_value, list) else False
        elif operator == "not_in":
            return actual_value not in expected_value if isinstance(expected_value, list) else True
        else:
            LOGGER.warning("Unknown operator: %s", operator)
            return False

    def _evaluate_time_condition(
        self, condition: dict[str, Any], context: AuthorizationContext
    ) -> bool:
        """Evaluate a time-based condition."""
        # This would implement time-based access control
        # For now, return True as a placeholder
        del condition, context  # Acknowledge unused parameters
        return True

    def _evaluate_identity_condition(
        self, condition: dict[str, Any], context: AuthorizationContext
    ) -> bool:
        """Evaluate an identity-based condition."""
        allowed_identities = condition.get("allowed_identities", [])
        return context.identity in allowed_identities if context.identity else False

    def _match_target(self, target: dict[str, Any], context: AuthorizationContext) -> bool:
        """Check if a policy target matches the context."""
        # Match resource
        if "resource" in target and context.resource:
            if not self._match_pattern(target["resource"], context.resource):
                return False

        # Match action
        if "action" in target and context.action:
            if not self._match_pattern(target["action"], context.action):
                return False

        # Match identity
        if "identity" in target and context.identity:
            if not self._match_pattern(target["identity"], context.identity):
                return False

        return True

    def _evaluate_rule(self, rule: dict[str, Any], context: AuthorizationContext) -> bool:
        """Evaluate a policy rule."""
        conditions = rule.get("conditions", [])

        # All conditions must be true (AND logic)
        for condition in conditions:
            if not self._evaluate_condition(condition, context):
                return False

        return True

    def _match_pattern(self, pattern: str, value: str) -> bool:
        """Match a pattern against a value (supports wildcards)."""
        if pattern == "*":
            return True

        if "*" in pattern:
            # Simple wildcard matching
            import fnmatch

            return fnmatch.fnmatch(value, pattern)

        return pattern == value


def load_policy_config(config_path: str | None = None) -> dict[str, Any]:
    """Load policy configuration from file.

    Args:
        config_path: Path to policy configuration file

    Returns:
        Policy configuration dictionary
    """
    if not config_path:
        config_path = os.environ.get("MARTY_POLICY_CONFIG", "config/policy.yaml")

    try:
        config_file = Path(config_path)
        if not config_file.exists():
            LOGGER.warning("Policy config file not found: %s", config_path)
            return {}

        with open(config_file, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    except (OSError, yaml.YAMLError) as e:
        LOGGER.error("Failed to load policy config: %s", str(e))
        return {}


def require(
    permission: str,
    resource: str | None = None,
    policy_engine: PolicyEngine | None = None,
) -> Callable[[F], F]:
    """Decorator to require specific permissions for a method.

    Args:
        permission: Required permission (e.g., "document:sign")
        resource: Optional resource name
        policy_engine: Optional policy engine instance

    Returns:
        Decorator function
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Extract gRPC context from args (typically the last argument)
            context = None
            for arg in reversed(args):
                if hasattr(arg, "invocation_metadata"):
                    context = arg
                    break

            if not context:
                raise AuthorizationError("gRPC context not found")

            # Extract authentication info from metadata
            auth_context = _extract_auth_context(context)

            # Create authorization context
            authz_context = AuthorizationContext(
                identity=auth_context.get("identity"),
                roles=auth_context.get("roles", []),
                attributes=auth_context.get("attributes", {}),
                resource=resource or _extract_resource_from_method(func),
                action=permission,
            )

            # Evaluate authorization
            engine = policy_engine or _get_default_policy_engine()
            if not engine.evaluate(authz_context):
                raise AuthorizationError(f"Access denied for permission: {permission}")

            return await func(*args, **kwargs)

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Same logic for synchronous functions
            context = None
            for arg in reversed(args):
                if hasattr(arg, "invocation_metadata"):
                    context = arg
                    break

            if not context:
                raise AuthorizationError("gRPC context not found")

            auth_context = _extract_auth_context(context)

            authz_context = AuthorizationContext(
                identity=auth_context.get("identity"),
                roles=auth_context.get("roles", []),
                attributes=auth_context.get("attributes", {}),
                resource=resource or _extract_resource_from_method(func),
                action=permission,
            )

            engine = policy_engine or _get_default_policy_engine()
            if not engine.evaluate(authz_context):
                raise AuthorizationError(f"Access denied for permission: {permission}")

            return func(*args, **kwargs)

        # Return appropriate wrapper based on function type
        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        else:
            return sync_wrapper  # type: ignore

    return decorator


def _extract_auth_context(grpc_context) -> dict[str, Any]:
    """Extract authentication context from gRPC metadata."""
    metadata = dict(grpc_context.invocation_metadata())

    # Extract identity from JWT or client cert
    identity = None
    roles = []
    attributes = {}

    # Try to extract from Authorization header (JWT)
    auth_header = metadata.get("authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            import jwt

            token = auth_header[7:]
            # Note: This is a simplified example - in practice you'd validate the JWT
            claims = jwt.decode(token, options={"verify_signature": False})
            identity = claims.get("sub") or claims.get("user_id")
            roles = claims.get("roles", [])
            attributes = {k: v for k, v in claims.items() if k not in ("sub", "user_id", "roles")}
        except Exception:
            pass  # Fall back to other methods

    # Try to extract from client certificate
    if not identity:
        client_cert_subject = metadata.get("x-client-cert-subject", "")
        if client_cert_subject:
            identity = client_cert_subject
            # Extract roles from certificate attributes if available
            # This is a simplified example
            if "ou=" in client_cert_subject.lower():
                roles = [client_cert_subject.split("ou=")[1].split(",")[0]]

    return {
        "identity": identity,
        "roles": roles,
        "attributes": attributes,
    }


def _extract_resource_from_method(func: Callable) -> str:
    """Extract resource name from method name or class."""
    if hasattr(func, "__qualname__"):
        parts = func.__qualname__.split(".")
        if len(parts) > 1:
            # Remove "Service" or "Servicer" suffix if present
            class_name = parts[-2]
            for suffix in ["Service", "Servicer"]:
                if class_name.endswith(suffix):
                    class_name = class_name[: -len(suffix)]
                    break
            return class_name.lower()

    return func.__name__


# Global policy engine instance
_default_policy_engine: PolicyEngine | None = None


def _get_default_policy_engine() -> PolicyEngine:
    """Get or create the default policy engine."""
    global _default_policy_engine

    if _default_policy_engine is None:
        config = load_policy_config()
        _default_policy_engine = PolicyEngine(config)

    return _default_policy_engine


__all__ = [
    "AuthorizationError",
    "PolicyEvaluationError",
    "AuthorizationContext",
    "PolicyEngine",
    "load_policy_config",
    "require",
]
