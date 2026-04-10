"""
KMS Configuration Service

Manages organization-level KMS/HSM configuration for remote signing.
Production tiers (STARTER, PROFESSIONAL, ENTERPRISE) must configure their
own KMS to use remote signing.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from typing import Optional
from uuid import UUID

from cryptography.fernet import Fernet, MultiFernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Organization, Subscription
from .square_service import PLAN_LIMITS, SquarePlan

logger = logging.getLogger(__name__)


@dataclass
class KMSProviderConfig:
    """KMS provider configuration."""

    provider: str
    region: Optional[str] = None
    key_id: Optional[str] = None
    endpoint_url: Optional[str] = None
    algorithm: str = "ES256"
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> KMSProviderConfig:
        """Create from dictionary."""
        return cls(
            provider=data["provider"],
            region=data.get("region"),
            key_id=data.get("key_id"),
            endpoint_url=data.get("endpoint_url"),
            algorithm=data.get("algorithm", "ES256"),
            metadata=data.get("metadata", {}),
        )


class KMSConfigError(Exception):
    """KMS configuration error."""

    pass


class KMSConfigService:
    """
    Manage organization KMS configuration.

    Handles:
    - KMS provider configuration for production tiers
    - Secure credential storage (Fernet encrypted)
    - Tier validation (only production tiers can configure KMS)
    - Configuration retrieval for signing operations
    """

    def __init__(self, db: AsyncSession, encryption_key: Optional[bytes] = None):
        """
        Initialize KMS configuration service.

        Args:
            db: Database session
            encryption_key: Fernet encryption key for credentials.
                           If None, loaded from KMS_ENCRYPTION_KEY env var.
                           For key rotation, set KMS_ENCRYPTION_KEY to the new key
                           and KMS_ENCRYPTION_KEY_PREVIOUS to the old key.
        """
        self.db = db
        self.logger = logging.getLogger(__name__)

        # Get or generate encryption key
        if encryption_key is None:
            key_str = os.environ.get("KMS_ENCRYPTION_KEY")
            if key_str:
                encryption_key = key_str.encode()
            else:
                # Generate a key for development (NEVER use in production)
                encryption_key = Fernet.generate_key()
                self.logger.warning(
                    "KMS_ENCRYPTION_KEY not set - generated temporary key. "
                    "This is ONLY for development. Set KMS_ENCRYPTION_KEY in production."
                )

        # Build Fernet key chain: primary key first, then previous keys
        fernet_keys = [Fernet(encryption_key)]
        previous_key_str = os.environ.get("KMS_ENCRYPTION_KEY_PREVIOUS")
        if previous_key_str:
            fernet_keys.append(Fernet(previous_key_str.encode()))

        # MultiFernet always encrypts with the first key,
        # but can decrypt with any key in the list
        self.cipher = MultiFernet(fernet_keys)
        self._primary_key = encryption_key

    async def configure_kms(
        self,
        organization: Organization,
        provider: str,
        credentials: dict,
        config: KMSProviderConfig,
    ) -> None:
        """
        Configure KMS for an organization.

        Args:
            organization: Organization to configure
            provider: KMS provider name (aws_kms, azure_key_vault, etc.)
            credentials: Provider credentials (will be encrypted)
            config: Provider configuration

        Raises:
            KMSConfigError: If tier doesn't support KMS or validation fails
        """
        # Validate subscription tier
        subscription = await self._get_active_subscription(organization.id)
        if not subscription:
            raise KMSConfigError("No active subscription found")

        plan = SquarePlan(subscription.plan)
        plan_limits = PLAN_LIMITS.get(plan)

        if not plan_limits or not plan_limits.requires_remote_signing:
            raise KMSConfigError(
                f"Tier {plan.value} uses service key vault with automatic rotation. "
                f"KMS configuration is only available for production tiers "
                f"(STARTER, PROFESSIONAL, ENTERPRISE)."
            )

        # Validate provider
        supported_providers = {
            "aws_kms",
            "azure_key_vault",
            "gcp_kms",
            "hashicorp_vault",
            "pkcs11_hsm",
            "software_hsm",  # For development/testing
        }
        if provider not in supported_providers:
            raise KMSConfigError(
                f"Unsupported provider: {provider}. "
                f"Supported: {', '.join(sorted(supported_providers))}"
            )

        # Validate required config fields by provider
        self._validate_provider_config(provider, config, credentials)

        # Encrypt credentials
        credentials_json = json.dumps(credentials)
        encrypted = self.cipher.encrypt(credentials_json.encode())

        # Store configuration
        organization.kms_provider = provider
        organization.kms_config = config.to_dict()
        organization.kms_credentials_encrypted = encrypted.decode()

        await self.db.commit()

        self.logger.info(
            f"Configured {provider} for organization {organization.id} ({organization.name})"
        )

    async def get_kms_config(
        self,
        organization: Organization,
    ) -> tuple[KMSProviderConfig, dict]:
        """
        Get KMS configuration and decrypted credentials.

        Args:
            organization: Organization

        Returns:
            Tuple of (config, credentials)

        Raises:
            KMSConfigError: If KMS not configured
        """
        if not organization.kms_provider:
            raise KMSConfigError(
                f"KMS not configured for organization {organization.name}. "
                f"Configure KMS before using remote signing."
            )

        config = KMSProviderConfig.from_dict(organization.kms_config)

        # Decrypt credentials
        if organization.kms_credentials_encrypted:
            encrypted = organization.kms_credentials_encrypted.encode()
            decrypted = self.cipher.decrypt(encrypted)
            credentials = json.loads(decrypted.decode())
        else:
            credentials = {}

        return config, credentials

    async def get_kms_config_safe(
        self,
        organization: Organization,
    ) -> Optional[dict]:
        """
        Get KMS configuration without credentials (safe for API responses).

        Args:
            organization: Organization

        Returns:
            Configuration dict with credentials redacted, or None if not configured
        """
        if not organization.kms_provider:
            return None

        config = organization.kms_config.copy()
        return {
            "provider": organization.kms_provider,
            "region": config.get("region"),
            "algorithm": config.get("algorithm", "ES256"),
            "endpoint_url": config.get("endpoint_url"),
            "metadata": config.get("metadata", {}),
            # Credentials are NEVER included in safe responses
        }

    async def delete_kms_config(self, organization: Organization) -> None:
        """
        Remove KMS configuration from organization.

        Args:
            organization: Organization
        """
        organization.kms_provider = None
        organization.kms_config = {}
        organization.kms_credentials_encrypted = None

        await self.db.commit()

        self.logger.info(
            f"Deleted KMS configuration for organization {organization.id}"
        )

    async def rotate_credentials(self, organization: Organization) -> bool:
        """
        Re-encrypt a single organization's credentials with the current primary key.

        Uses MultiFernet.rotate() which decrypts with any key in the chain
        and re-encrypts with the primary (first) key.

        Args:
            organization: Organization to re-encrypt

        Returns:
            True if credentials were rotated, False if no credentials to rotate
        """
        if not organization.kms_credentials_encrypted:
            return False

        try:
            old_token = organization.kms_credentials_encrypted.encode()
            new_token = self.cipher.rotate(old_token)
            organization.kms_credentials_encrypted = new_token.decode()
            await self.db.commit()

            self.logger.info(
                f"Rotated encryption key for organization {organization.id}"
            )
            return True
        except Exception as e:
            await self.db.rollback()
            self.logger.error(
                f"Failed to rotate credentials for organization {organization.id}: {e}"
            )
            raise KMSConfigError(
                f"Failed to rotate credentials for organization {organization.id}"
            ) from e

    async def rotate_all_credentials(self) -> dict:
        """
        Re-encrypt all organization credentials with the current primary key.

        This should be called after updating KMS_ENCRYPTION_KEY and setting
        KMS_ENCRYPTION_KEY_PREVIOUS to the old key.

        Returns:
            Dict with rotation results: {rotated: int, skipped: int, failed: int, errors: list}
        """
        result = await self.db.execute(
            select(Organization).where(
                Organization.kms_credentials_encrypted.isnot(None)
            )
        )
        organizations = result.scalars().all()

        stats = {"rotated": 0, "skipped": 0, "failed": 0, "errors": []}

        for org in organizations:
            try:
                rotated = await self.rotate_credentials(org)
                if rotated:
                    stats["rotated"] += 1
                else:
                    stats["skipped"] += 1
            except KMSConfigError as e:
                stats["failed"] += 1
                stats["errors"].append(
                    {"organization_id": str(org.id), "error": str(e)}
                )

        self.logger.info(
            f"Key rotation complete: {stats['rotated']} rotated, "
            f"{stats['skipped']} skipped, {stats['failed']} failed"
        )
        return stats

    async def test_kms_connectivity(
        self,
        organization: Organization,
    ) -> dict:
        """
        Test KMS connectivity and return status.

        Args:
            organization: Organization

        Returns:
            Dict with connectivity status and details
        """
        try:
            config, credentials = await self.get_kms_config(organization)

            # Import provider factory
            from marty_backend_common.crypto.kms_provider import (
                AWSKMSProvider,
                AzureKeyVaultProvider,
                GCPCloudKMSProvider,
                KMSProvider as KMSProviderEnum,
            )

            provider_type = organization.kms_provider

            # Test based on provider type
            if provider_type == "aws_kms":
                try:
                    import boto3

                    kms = boto3.client(
                        "kms",
                        region_name=config.region,
                        aws_access_key_id=credentials.get("access_key_id"),
                        aws_secret_access_key=credentials.get("secret_access_key"),
                        endpoint_url=config.endpoint_url,
                    )
                    kms.list_aliases(Limit=1)
                    return {"connected": True, "provider": "aws_kms"}
                except Exception as e:
                    return {
                        "connected": False,
                        "provider": "aws_kms",
                        "error": str(e),
                    }

            elif provider_type == "azure_key_vault":
                try:
                    provider = AzureKeyVaultProvider(
                        vault_url=config.endpoint_url or credentials.get("vault_url", ""),
                        tenant_id=credentials.get("tenant_id"),
                        client_id=credentials.get("client_id"),
                        client_secret=credentials.get("client_secret"),
                    )
                    await provider.list_keys()
                    return {"connected": True, "provider": "azure_key_vault"}
                except Exception as e:
                    return {
                        "connected": False,
                        "provider": "azure_key_vault",
                        "error": str(e),
                    }

            elif provider_type == "gcp_kms":
                try:
                    provider = GCPCloudKMSProvider(
                        project_id=credentials.get("project_id", config.metadata.get("project_id", "")),
                        location=config.region or "global",
                        key_ring=config.metadata.get("key_ring", "marty"),
                        credentials_json=credentials.get("credentials_json"),
                    )
                    await provider.list_keys()
                    return {"connected": True, "provider": "gcp_kms"}
                except Exception as e:
                    return {
                        "connected": False,
                        "provider": "gcp_kms",
                        "error": str(e),
                    }

            else:
                # SoftwareHSM / PKCS11 / Vault — creation is the connectivity test
                return {
                    "connected": True,
                    "provider": provider_type,
                }

        except Exception as e:
            return {"connected": False, "error": str(e)}

    async def _get_active_subscription(
        self, organization_id: UUID
    ) -> Optional[Subscription]:
        """Get active subscription for organization."""
        result = await self.db.execute(
            select(Subscription)
            .where(Subscription.organization_id == organization_id)
            .where(Subscription.status == "active")
            .limit(1)
        )
        return result.scalar_one_or_none()

    def _validate_provider_config(
        self,
        provider: str,
        config: KMSProviderConfig,
        credentials: dict,
    ) -> None:
        """
        Validate provider-specific configuration.

        Raises:
            KMSConfigError: If validation fails
        """
        if provider == "aws_kms":
            if not config.region:
                raise KMSConfigError("AWS KMS requires 'region' in config")
            if not credentials.get("access_key_id"):
                raise KMSConfigError("AWS KMS requires 'access_key_id' in credentials")
            if not credentials.get("secret_access_key"):
                raise KMSConfigError(
                    "AWS KMS requires 'secret_access_key' in credentials"
                )

        elif provider == "azure_key_vault":
            if not config.endpoint_url:
                raise KMSConfigError("Azure Key Vault requires 'endpoint_url' in config")
            if not credentials.get("tenant_id"):
                raise KMSConfigError("Azure Key Vault requires 'tenant_id' in credentials")
            if not credentials.get("client_id"):
                raise KMSConfigError("Azure Key Vault requires 'client_id' in credentials")

        elif provider == "gcp_kms":
            if not config.region:
                raise KMSConfigError("GCP KMS requires 'region' in config")
            if not config.metadata.get("project_id"):
                raise KMSConfigError("GCP KMS requires 'project_id' in metadata")
            if not credentials.get("type"):
                raise KMSConfigError(
                    "GCP KMS requires service account credentials (JSON)"
                )

        elif provider == "hashicorp_vault":
            if not config.endpoint_url:
                raise KMSConfigError("HashiCorp Vault requires 'endpoint_url' in config")

        elif provider == "pkcs11_hsm":
            if not config.metadata.get("library_path"):
                raise KMSConfigError("PKCS#11 HSM requires 'library_path' in metadata")
            if not config.metadata.get("token_label"):
                raise KMSConfigError("PKCS#11 HSM requires 'token_label' in metadata")
            if not credentials.get("user_pin"):
                raise KMSConfigError("PKCS#11 HSM requires 'user_pin' in credentials")
