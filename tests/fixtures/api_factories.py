"""
Entity factories for API integration tests.

Provides factory functions to create test data for:
- Organizations
- API Keys
- Webhooks
- Subscriptions
- Credentials
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from src.subscription.models import (
    APIKey,
    Organization,
    Subscription,
    SubscriptionStatus,
    WebhookEndpoint,
)


class OrganizationFactory:
    """Factory for creating test Organization instances."""
    
    @staticmethod
    def create(
        id: Optional[UUID] = None,
        name: str = "Test Organization",
        slug: Optional[str] = None,
        settings: Optional[dict[str, Any]] = None,
        **kwargs
    ) -> Organization:
        """
        Create a test organization.
        
        Args:
            id: Organization ID (generates UUID if not provided)
            name: Organization name
            slug: Organization slug (generates from name if not provided)
            settings: Organization settings dict
            **kwargs: Additional fields
        
        Returns:
            Organization instance
        """
        if id is None:
            id = uuid4()
        
        if slug is None:
            slug = name.lower().replace(" ", "-") + f"-{uuid4().hex[:8]}"
        
        if settings is None:
            settings = {}
        
        return Organization(
            id=id,
            name=name,
            slug=slug,
            settings=settings,
            created_at=kwargs.get("created_at", datetime.now(timezone.utc)),
            **{k: v for k, v in kwargs.items() if k != "created_at"}
        )


class SubscriptionFactory:
    """Factory for creating test Subscription instances."""
    
    @staticmethod
    def create(
        organization_id: UUID,
        plan: str = "professional",
        status: SubscriptionStatus = SubscriptionStatus.ACTIVE,
        api_calls_limit: int = 10000,
        api_calls_used: int = 0,
        **kwargs
    ) -> Subscription:
        """
        Create a test subscription.
        
        Args:
            organization_id: ID of the organization
            plan: Subscription plan name
            status: Subscription status
            api_calls_limit: API call limit
            api_calls_used: Current API call usage
            **kwargs: Additional fields
        
        Returns:
            Subscription instance
        """
        now = datetime.now(timezone.utc)
        
        return Subscription(
            id=kwargs.get("id", uuid4()),
            organization_id=organization_id,
            plan=plan,
            status=status,
            api_calls_limit=api_calls_limit,
            api_calls_used=api_calls_used,
            current_period_start=kwargs.get("current_period_start", now),
            current_period_end=kwargs.get("current_period_end", now + timedelta(days=30)),
            created_at=kwargs.get("created_at", now),
            **{k: v for k, v in kwargs.items() if k not in [
                "id", "current_period_start", "current_period_end", "created_at"
            ]}
        )


class APIKeyFactory:
    """Factory for creating test APIKey instances."""
    
    @staticmethod
    def create(
        organization_id: UUID,
        name: str = "Test API Key",
        key_prefix: Optional[str] = None,
        key_hash: Optional[str] = None,
        scopes: Optional[list[str]] = None,
        is_test: bool = False,
        **kwargs
    ) -> APIKey:
        """
        Create a test API key.
        
        Args:
            organization_id: ID of the organization
            name: API key name
            key_prefix: Key prefix (e.g., 'pk_test_')
            key_hash: SHA-256 hash of the key
            scopes: List of scopes
            is_test: Whether this is a test key
            **kwargs: Additional fields
        
        Returns:
            APIKey instance
        """
        import hashlib
        
        if key_prefix is None:
            prefix = "pk_test_" if is_test else "pk_live_"
            key_prefix = f"{prefix}{uuid4().hex[:8]}"
        
        if key_hash is None:
            # Generate a mock hash
            key_hash = hashlib.sha256(f"test-key-{uuid4()}".encode()).hexdigest()
        
        if scopes is None:
            scopes = ["read:credentials", "write:credentials"]
        
        return APIKey(
            id=kwargs.get("id", uuid4()),
            organization_id=organization_id,
            name=name,
            key_prefix=key_prefix,
            key_hash=key_hash,
            scopes=scopes,
            ip_allowlist=kwargs.get("ip_allowlist", []),
            is_test=is_test,
            expires_at=kwargs.get("expires_at"),
            last_used_at=kwargs.get("last_used_at"),
            created_at=kwargs.get("created_at", datetime.now(timezone.utc)),
            revoked_at=kwargs.get("revoked_at"),
            **{k: v for k, v in kwargs.items() if k not in [
                "id", "ip_allowlist", "expires_at", "last_used_at", "created_at", "revoked_at"
            ]}
        )


class WebhookFactory:
    """Factory for creating test WebhookEndpoint instances."""
    
    @staticmethod
    def create(
        organization_id: UUID,
        url: str = "https://example.com/webhooks",
        event_types: Optional[list[str]] = None,
        secret: Optional[str] = None,
        enabled: bool = True,
        **kwargs
    ) -> WebhookEndpoint:
        """
        Create a test webhook endpoint.
        
        Args:
            organization_id: ID of the organization
            url: Webhook URL
            event_types: List of event types to subscribe to
            secret: HMAC secret for signature verification
            enabled: Whether webhook is enabled
            **kwargs: Additional fields
        
        Returns:
            WebhookEndpoint instance
        """
        import secrets
        
        if event_types is None:
            event_types = ["credential.issued", "credential.revoked"]
        
        if secret is None:
            secret = secrets.token_urlsafe(32)
        
        return WebhookEndpoint(
            id=kwargs.get("id", uuid4()),
            organization_id=organization_id,
            url=url,
            event_types=event_types,
            secret=secret,
            enabled=enabled,
            description=kwargs.get("description", ""),
            failure_count=kwargs.get("failure_count", 0),
            last_failure_at=kwargs.get("last_failure_at"),
            disabled_at=kwargs.get("disabled_at"),
            created_at=kwargs.get("created_at", datetime.now(timezone.utc)),
            updated_at=kwargs.get("updated_at"),
            **{k: v for k, v in kwargs.items() if k not in [
                "id", "description", "failure_count", "last_failure_at",
                "disabled_at", "created_at", "updated_at"
            ]}
        )


class CredentialConfigFactory:
    """Factory for creating test credential configuration instances."""
    
    @staticmethod
    def create(
        organization_id: UUID,
        credential_type: str = "VerifiableCredential",
        schema_url: Optional[str] = None,
        display_name: str = "Test Credential",
        **kwargs
    ) -> dict[str, Any]:
        """
        Create a test credential configuration.
        
        Args:
            organization_id: ID of the organization
            credential_type: Credential type identifier
            schema_url: URL to credential schema
            display_name: Display name for the credential
            **kwargs: Additional configuration fields
        
        Returns:
            Dict representing credential configuration
        """
        if schema_url is None:
            schema_url = f"https://example.com/schemas/{credential_type.lower()}"
        
        return {
            "id": str(kwargs.get("id", uuid4())),
            "organization_id": str(organization_id),
            "credential_type": credential_type,
            "schema_url": schema_url,
            "display_name": display_name,
            "fields": kwargs.get("fields", [
                {"name": "givenName", "type": "string", "required": True},
                {"name": "familyName", "type": "string", "required": True},
                {"name": "dateOfBirth", "type": "date", "required": False},
            ]),
            "issuer_name": kwargs.get("issuer_name", "Test Issuer"),
            "enabled": kwargs.get("enabled", True),
            "created_at": kwargs.get("created_at", datetime.now(timezone.utc).isoformat()),
        }


class TrustConfigFactory:
    """Factory for creating test trust configuration instances."""
    
    @staticmethod
    def create(
        organization_id: UUID,
        signing_algorithm: str = "ES256",
        key_type: str = "ec",
        **kwargs
    ) -> dict[str, Any]:
        """
        Create a test trust configuration.
        
        Args:
            organization_id: ID of the organization
            signing_algorithm: Signing algorithm (e.g., ES256, RS256)
            key_type: Key type (ec, rsa)
            **kwargs: Additional configuration fields
        
        Returns:
            Dict representing trust configuration
        """
        return {
            "id": str(kwargs.get("id", uuid4())),
            "organization_id": str(organization_id),
            "signing_algorithm": signing_algorithm,
            "key_type": key_type,
            "did": kwargs.get("did", f"did:key:test{uuid4().hex[:16]}"),
            "verification_method": kwargs.get("verification_method", "JsonWebKey2020"),
            "trust_framework": kwargs.get("trust_framework", "custom"),
            "enabled": kwargs.get("enabled", True),
            "created_at": kwargs.get("created_at", datetime.now(timezone.utc).isoformat()),
        }


# Convenience functions
def create_test_organization(**kwargs) -> Organization:
    """Shortcut to create a test organization."""
    return OrganizationFactory.create(**kwargs)


def create_test_subscription(organization_id: UUID, **kwargs) -> Subscription:
    """Shortcut to create a test subscription."""
    return SubscriptionFactory.create(organization_id, **kwargs)


def create_test_api_key(organization_id: UUID, **kwargs) -> APIKey:
    """Shortcut to create a test API key."""
    return APIKeyFactory.create(organization_id, **kwargs)


def create_test_webhook(organization_id: UUID, **kwargs) -> WebhookEndpoint:
    """Shortcut to create a test webhook."""
    return WebhookFactory.create(organization_id, **kwargs)
