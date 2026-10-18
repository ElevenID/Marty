"""
KMS/HSM Provider Abstraction for Secure Key Management

This module defines the retained provider interface for managed key custody.

All private key operations are wrapped through providers to ensure:
1. Consistent security across environments
2. Hardware-backed security where required
3. Audit trail of all key operations
4. Role-based access controls
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from marty_common.native_backends import NativeOperationError

from .role_separation import (
    CryptoRole,
    KeyIdentity,
    KeyPurpose,
    RoleSeparationEnforcer,
    get_role_policy,
)


class KMSProvider(Enum):
    """Supported KMS/HSM providers."""

    AWS_KMS = "aws_kms"
    AZURE_KEY_VAULT = "azure_key_vault"
    GCP_KMS = "gcp_kms"
    HASHICORP_VAULT = "hashicorp_vault"
    PKCS11_HSM = "pkcs11_hsm"


class KeyOperation(Enum):
    """Key operations that can be audited."""

    GENERATE = "generate"
    IMPORT = "import"
    SIGN = "sign"
    ENCRYPT = "encrypt"
    DECRYPT = "decrypt"
    VERIFY = "verify"
    EXPORT_PUBLIC = "export_public"
    DELETE = "delete"
    ROTATE = "rotate"
    BACKUP = "backup"
    RESTORE = "restore"


@dataclass
class KeyMaterial:
    """Represents key material with metadata."""

    key_identity: KeyIdentity
    algorithm: str
    public_key_pem: bytes
    provider: KMSProvider
    provider_key_id: str
    created_at: datetime
    expires_at: datetime | None = None
    metadata: dict[str, Any] | None = None

    @property
    def is_expired(self) -> bool:
        """Check if the key has expired."""
        if self.expires_at is None:
            return False
        return datetime.now(UTC) > self.expires_at


@dataclass
class KeyOperationAuditLog:
    """Audit log entry for key operations."""

    timestamp: datetime
    operation: KeyOperation
    key_identity: KeyIdentity
    provider: KMSProvider
    success: bool
    error_message: str | None = None
    requesting_entity: str | None = None
    additional_context: dict[str, Any] | None = None


class KMSProviderInterface(ABC):
    """Abstract interface for KMS/HSM providers."""

    @property
    @abstractmethod
    def provider_type(self) -> KMSProvider:
        """Declare the managed custody provider used for policy and audit."""

    @abstractmethod
    async def generate_key(self, key_identity: KeyIdentity, algorithm: str, **kwargs) -> KeyMaterial:
        """Generate a new key."""
        pass

    @abstractmethod
    async def sign(self, key_identity: KeyIdentity, data: bytes, algorithm: str = "SHA256") -> bytes:
        """Sign data using the specified key."""
        pass

    @abstractmethod
    async def encrypt(self, key_identity: KeyIdentity, plaintext: bytes, algorithm: str = "AES-256-GCM") -> bytes:
        """Encrypt data using the specified key."""
        pass

    @abstractmethod
    async def decrypt(self, key_identity: KeyIdentity, ciphertext: bytes, algorithm: str = "AES-256-GCM") -> bytes:
        """Decrypt data using the specified key."""
        pass

    @abstractmethod
    async def get_public_key(self, key_identity: KeyIdentity) -> bytes:
        """Get the public key in PEM format."""
        pass

    @abstractmethod
    async def delete_key(self, key_identity: KeyIdentity) -> bool:
        """Delete a key (if supported by provider)."""
        pass

    @abstractmethod
    async def list_keys(self, role: CryptoRole | None = None) -> list[KeyMaterial]:
        """List available keys, optionally filtered by role."""
        pass

    @abstractmethod
    async def key_exists(self, key_identity: KeyIdentity) -> bool:
        """Check if a key exists."""
        pass


class KMSManager:
    """Central manager for KMS/HSM operations with role enforcement."""

    def __init__(self, provider: KMSProviderInterface):
        provider_type = getattr(provider, "provider_type", None)
        if not isinstance(provider_type, KMSProvider):
            raise NativeOperationError("An explicit managed provider identity is required")
        self.provider_type = provider_type
        self.provider = provider
        self.logger = logging.getLogger(f"{__name__}.KMSManager")
        self.audit_logs: list[KeyOperationAuditLog] = []
        self.role_enforcer = RoleSeparationEnforcer()

    async def generate_key_for_role(
        self, role: CryptoRole, purpose: KeyPurpose, key_id: str, algorithm: str = "ES256", **kwargs
    ) -> KeyMaterial:
        """Generate a key for a specific role and purpose."""

        # Create key identity
        key_identity = KeyIdentity(
            role=role,
            purpose=purpose,
            key_id=key_id,
            issuer_identifier=kwargs.get("issuer_identifier"),
            device_identifier=kwargs.get("device_identifier"),
        )

        try:
            key_material = await self.provider.generate_key(key_identity, algorithm, **kwargs)

            # Log the operation
            await self._log_operation(
                KeyOperation.GENERATE,
                key_identity,
                success=True,
                additional_context={"algorithm": algorithm},
            )

            return key_material

        except Exception as e:
            await self._log_operation(KeyOperation.GENERATE, key_identity, success=False, error_message=str(e))
            raise

    async def sign_with_role_validation(
        self,
        key_identity: KeyIdentity,
        data: bytes,
        requesting_role: CryptoRole,
        algorithm: str = "SHA256",
    ) -> bytes:
        """Sign data with role boundary validation."""

        # Validate the operation is allowed
        self.role_enforcer.validate_key_operation(key_identity, "sign", requesting_role)

        try:
            signature = await self.provider.sign(key_identity, data, algorithm)

            await self._log_operation(
                KeyOperation.SIGN,
                key_identity,
                success=True,
                requesting_entity=requesting_role.value,
            )

            return signature

        except Exception as e:
            await self._log_operation(
                KeyOperation.SIGN,
                key_identity,
                success=False,
                error_message=str(e),
                requesting_entity=requesting_role.value,
            )
            raise

    async def get_public_key_for_verification(self, key_identity: KeyIdentity, requesting_role: CryptoRole) -> bytes:
        """Get public key for verification purposes."""

        # Public keys can be shared for verification
        if requesting_role in [CryptoRole.READER, CryptoRole.VERIFIER]:
            return await self.provider.get_public_key(key_identity)

        # Other roles need validation
        self.role_enforcer.validate_key_operation(key_identity, "export_public", requesting_role)

        return await self.provider.get_public_key(key_identity)

    async def _log_operation(
        self,
        operation: KeyOperation,
        key_identity: KeyIdentity,
        success: bool,
        error_message: str | None = None,
        requesting_entity: str | None = None,
        additional_context: dict[str, Any] | None = None,
    ) -> None:
        """Log a key operation for audit purposes."""

        log_entry = KeyOperationAuditLog(
            timestamp=datetime.now(UTC),
            operation=operation,
            key_identity=key_identity,
            provider=self.provider_type,
            success=success,
            error_message=error_message,
            requesting_entity=requesting_entity,
            additional_context=additional_context,
        )

        self.audit_logs.append(log_entry)

        # In production, this would also write to persistent audit storage
        if get_role_policy(key_identity.role).requires_audit:
            self.logger.info(
                f"Audit: {operation.value} on {key_identity.full_key_id} "
                f"by {requesting_entity} - {'SUCCESS' if success else 'FAILED'}"
            )

    async def list_keys_by_role(self, role: CryptoRole) -> list[KeyMaterial]:
        """List all keys for a specific role."""
        return await self.provider.list_keys(role)

    async def rotate_key(
        self, old_key_identity: KeyIdentity, algorithm: str = "ES256", overlap_days: int = 30
    ) -> KeyMaterial:
        """Rotate a key while maintaining overlap period."""

        # Generate new key with incremented version
        new_key_id = f"{old_key_identity.key_id}-rotated-{int(datetime.now().timestamp())}"
        new_key_identity = KeyIdentity(
            role=old_key_identity.role,
            purpose=old_key_identity.purpose,
            key_id=new_key_id,
            issuer_identifier=old_key_identity.issuer_identifier,
            device_identifier=old_key_identity.device_identifier,
        )

        # Generate new key
        new_key = await self.provider.generate_key(new_key_identity, algorithm)

        # Log rotation
        await self._log_operation(
            KeyOperation.ROTATE,
            old_key_identity,
            success=True,
            additional_context={
                "new_key_id": new_key_identity.full_key_id,
                "overlap_days": overlap_days,
            },
        )

        return new_key


def create_kms_manager(provider_type: KMSProvider, **config) -> KMSManager:
    """Factory function to create KMS manager with specified provider."""

    if not isinstance(provider_type, KMSProvider):
        raise NativeOperationError("An explicit managed provider identity is required")
    raise NotImplementedError(f"Managed adapter for {provider_type} is not implemented")
