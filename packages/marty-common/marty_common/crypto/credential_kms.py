"""
Credential KMS Extension

This module extends MMF's IKMSProvider with credential-specific key operations.
It integrates with Marty's role separation framework to enforce proper boundaries
between issuer, holder, verifier, and other credential-related keys.

Key ID Namespacing:
- cred:issuer:{issuer_id}:{key_id} - Issuer signing keys (CSCA, DSC)
- cred:holder:{device_id}:{credential_id} - Holder binding keys
- cred:vdsnc:{country_code}:{role}:{generation} - VDS-NC signing keys
- cred:evidence:{service_id} - Evidence signing keys

This is the Marty credential domain layer - MMF handles authentication keys (auth:*).
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from .role_separation import (
    CryptoRole,
    KeyIdentity,
    KeyPurpose,
    RoleBoundaryViolation,
    RoleSeparationEnforcer,
    SecurityLevel,
    get_role_policy,
)

if TYPE_CHECKING:
    from mmf.core.security.ports.kms import (
        IKMSProvider,
        KeyAlgorithm,
        KeyMaterial,
        KeyMetadata,
    )

logger = logging.getLogger(__name__)


class CredentialKeyPrefix:
    """Key ID prefix constants for credential keys."""

    ISSUER = "cred:issuer:"
    HOLDER = "cred:holder:"
    VDSNC = "cred:vdsnc:"
    EVIDENCE = "cred:evidence:"
    AUDIT = "cred:audit:"

    @classmethod
    def issuer_key_id(cls, issuer_id: str, key_id: str) -> str:
        """Create an issuer key ID."""
        return f"{cls.ISSUER}{issuer_id}:{key_id}"

    @classmethod
    def holder_key_id(cls, device_id: str, credential_id: str) -> str:
        """Create a holder binding key ID."""
        return f"{cls.HOLDER}{device_id}:{credential_id}"

    @classmethod
    def vdsnc_key_id(cls, country_code: str, role: str, generation: int) -> str:
        """Create a VDS-NC signing key ID."""
        return f"{cls.VDSNC}{country_code}:{role}:{generation}"

    @classmethod
    def evidence_key_id(cls, service_id: str) -> str:
        """Create an evidence signing key ID."""
        return f"{cls.EVIDENCE}{service_id}"

    @classmethod
    def is_credential_key(cls, key_id: str) -> bool:
        """Check if a key ID is a credential key."""
        return key_id.startswith("cred:")

    @classmethod
    def parse_prefix(cls, key_id: str) -> str | None:
        """Extract the credential key type (issuer, holder, vdsnc, evidence)."""
        if not key_id.startswith("cred:"):
            return None
        parts = key_id.split(":")
        if len(parts) >= 2:
            return parts[1]
        return None

    @classmethod
    def get_crypto_role(cls, key_id: str) -> CryptoRole | None:
        """Map a credential key ID to its CryptoRole."""
        prefix = cls.parse_prefix(key_id)
        mapping = {
            "issuer": CryptoRole.DSC,  # Document Signer Certificate
            "holder": CryptoRole.HOLDER,
            "vdsnc": CryptoRole.DSC,
            "evidence": CryptoRole.EVIDENCE,
            "audit": CryptoRole.AUDIT,
        }
        return mapping.get(prefix)


@dataclass
class CredentialKeyInfo:
    """Extended key information for credential keys."""

    key_id: str
    crypto_role: CryptoRole
    key_purpose: KeyPurpose
    key_identity: KeyIdentity
    public_key_pem: bytes
    public_key_jwk: dict[str, Any] | None = None
    issuer_identifier: str | None = None
    device_identifier: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None
    is_hardware_backed: bool = False

    @property
    def is_expired(self) -> bool:
        """Check if the key has expired."""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at


@runtime_checkable
class ICredentialKeyManager(Protocol):
    """
    Credential-specific key manager interface.

    This extends MMF's IKMSProvider with credential domain operations,
    enforcing Marty's role separation policies.
    """

    @property
    def kms_provider(self) -> "IKMSProvider":
        """Get the underlying KMS provider from MMF."""
        ...

    # === Issuer Key Operations ===

    async def generate_issuer_key(
        self,
        issuer_id: str,
        key_id: str,
        *,
        algorithm: str = "ES256",
        expires_in_days: int = 1095,  # 3 years default
        require_hsm: bool = True,
    ) -> CredentialKeyInfo:
        """
        Generate an issuer signing key (DSC level).

        Args:
            issuer_id: Issuer identifier (e.g., country code)
            key_id: Unique key identifier within the issuer
            algorithm: Signing algorithm (ES256, ES384, RS256, etc.)
            expires_in_days: Key expiration in days
            require_hsm: Whether HSM backing is required

        Returns:
            CredentialKeyInfo with key details
        """
        ...

    async def get_issuer_key(
        self,
        issuer_id: str,
        key_id: str,
    ) -> CredentialKeyInfo | None:
        """Get an issuer key's public information."""
        ...

    async def sign_credential(
        self,
        issuer_id: str,
        key_id: str,
        payload: bytes,
        *,
        algorithm: str | None = None,
    ) -> bytes:
        """
        Sign credential data using an issuer key.

        Enforces role separation - only DSC role can sign credentials.
        """
        ...

    async def rotate_issuer_key(
        self,
        issuer_id: str,
        key_id: str,
        *,
        new_expires_in_days: int = 1095,
    ) -> CredentialKeyInfo:
        """Rotate an issuer key, generating a new version."""
        ...

    # === Holder Key Operations ===

    async def generate_holder_binding_key(
        self,
        device_id: str,
        credential_id: str,
        *,
        algorithm: str = "ES256",
    ) -> CredentialKeyInfo:
        """
        Generate a holder binding key for a credential.

        This key binds a credential to a specific holder device.
        """
        ...

    async def get_holder_binding_key(
        self,
        device_id: str,
        credential_id: str,
    ) -> CredentialKeyInfo | None:
        """Get a holder binding key."""
        ...

    async def sign_presentation(
        self,
        device_id: str,
        credential_id: str,
        payload: bytes,
    ) -> bytes:
        """
        Sign a credential presentation using the holder binding key.

        Enforces role separation - only HOLDER role can sign presentations.
        """
        ...

    # === VDS-NC Key Operations ===

    async def generate_vdsnc_key(
        self,
        country_code: str,
        role: str,
        generation: int,
        *,
        algorithm: str = "ES256",
        expires_in_days: int = 1095,
    ) -> CredentialKeyInfo:
        """
        Generate a VDS-NC signing key.

        VDS-NC (Visible Digital Seal - Non-Cryptographic) keys are used
        for signing visible digital seals on documents.
        """
        ...

    async def sign_vdsnc(
        self,
        country_code: str,
        role: str,
        generation: int,
        payload: bytes,
    ) -> bytes:
        """Sign a VDS-NC document."""
        ...

    # === Evidence Key Operations ===

    async def generate_evidence_key(
        self,
        service_id: str,
        *,
        algorithm: str = "ES256",
        expires_in_days: int = 1095,
    ) -> CredentialKeyInfo:
        """
        Generate an evidence signing key.

        Evidence keys are used for tamper-evident audit logs.
        """
        ...

    async def sign_evidence(
        self,
        service_id: str,
        payload: bytes,
    ) -> bytes:
        """Sign evidence/audit data."""
        ...

    # === Key Listing and Management ===

    async def list_credential_keys(
        self,
        *,
        role: CryptoRole | None = None,
        issuer_id: str | None = None,
    ) -> list[CredentialKeyInfo]:
        """List credential keys with optional filtering."""
        ...

    async def delete_credential_key(self, key_id: str) -> bool:
        """Delete a credential key."""
        ...

    async def validate_key_operation(
        self,
        key_id: str,
        operation: str,
        requesting_role: CryptoRole,
    ) -> None:
        """
        Validate that a key operation is allowed.

        Raises RoleBoundaryViolation if the operation violates role separation.
        """
        ...


class CredentialKeyManager:
    """
    Default implementation of ICredentialKeyManager.

    Wraps an MMF IKMSProvider with credential-specific operations and
    role separation enforcement.
    """

    def __init__(self, kms_provider: "IKMSProvider"):
        """
        Initialize the credential key manager.

        Args:
            kms_provider: The underlying KMS provider from MMF
        """
        self._kms_provider = kms_provider
        self._enforcer = RoleSeparationEnforcer()
        self._logger = logging.getLogger(f"{__name__}.CredentialKeyManager")

    @property
    def kms_provider(self) -> "IKMSProvider":
        """Get the underlying KMS provider."""
        return self._kms_provider

    async def generate_issuer_key(
        self,
        issuer_id: str,
        key_id: str,
        *,
        algorithm: str = "ES256",
        expires_in_days: int = 1095,
        require_hsm: bool = True,
    ) -> CredentialKeyInfo:
        """Generate an issuer signing key."""
        from mmf.core.security.ports.kms import KeyAlgorithm

        # Create key identity for role validation
        key_identity = KeyIdentity(
            role=CryptoRole.DSC,
            purpose=KeyPurpose.DOCUMENT_SIGNING,
            key_id=key_id,
            issuer_identifier=issuer_id,
        )

        # Validate policy
        policy = get_role_policy(CryptoRole.DSC)
        if policy.requires_hsm() and require_hsm:
            self._logger.info(f"Generating HSM-backed issuer key for {issuer_id}")

        # Generate the key via MMF KMS
        full_key_id = CredentialKeyPrefix.issuer_key_id(issuer_id, key_id)
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)

        key_algo = KeyAlgorithm[algorithm] if hasattr(KeyAlgorithm, algorithm) else KeyAlgorithm.ES256
        key_material = await self._kms_provider.generate_key(
            key_id=full_key_id,
            algorithm=key_algo,
            expires_at=expires_at,
            require_hardware=require_hsm,
            labels={"role": CryptoRole.DSC.value, "issuer": issuer_id},
        )

        return CredentialKeyInfo(
            key_id=full_key_id,
            crypto_role=CryptoRole.DSC,
            key_purpose=KeyPurpose.DOCUMENT_SIGNING,
            key_identity=key_identity,
            public_key_pem=key_material.public_key_pem,
            public_key_jwk=key_material.public_key_jwk,
            issuer_identifier=issuer_id,
            created_at=key_material.metadata.created_at,
            expires_at=expires_at,
            is_hardware_backed=key_material.metadata.is_hardware_backed,
        )

    async def get_issuer_key(
        self,
        issuer_id: str,
        key_id: str,
    ) -> CredentialKeyInfo | None:
        """Get an issuer key's public information."""
        full_key_id = CredentialKeyPrefix.issuer_key_id(issuer_id, key_id)
        metadata = await self._kms_provider.get_key_metadata(full_key_id)
        if not metadata:
            return None

        public_key_pem = await self._kms_provider.get_public_key(full_key_id)
        public_key_jwk = await self._kms_provider.get_public_key_jwk(full_key_id)

        key_identity = KeyIdentity(
            role=CryptoRole.DSC,
            purpose=KeyPurpose.DOCUMENT_SIGNING,
            key_id=key_id,
            issuer_identifier=issuer_id,
        )

        return CredentialKeyInfo(
            key_id=full_key_id,
            crypto_role=CryptoRole.DSC,
            key_purpose=KeyPurpose.DOCUMENT_SIGNING,
            key_identity=key_identity,
            public_key_pem=public_key_pem,
            public_key_jwk=public_key_jwk,
            issuer_identifier=issuer_id,
            created_at=metadata.created_at,
            expires_at=metadata.expires_at,
            is_hardware_backed=metadata.is_hardware_backed,
        )

    async def sign_credential(
        self,
        issuer_id: str,
        key_id: str,
        payload: bytes,
        *,
        algorithm: str | None = None,
    ) -> bytes:
        """Sign credential data using an issuer key."""
        from mmf.core.security.ports.kms import KeyAlgorithm

        full_key_id = CredentialKeyPrefix.issuer_key_id(issuer_id, key_id)

        # Validate role separation
        key_identity = KeyIdentity(
            role=CryptoRole.DSC,
            purpose=KeyPurpose.DOCUMENT_SIGNING,
            key_id=key_id,
            issuer_identifier=issuer_id,
        )
        self._enforcer.validate_key_operation(key_identity, "sign", CryptoRole.DSC)

        # Sign via KMS
        key_algo = None
        if algorithm:
            key_algo = KeyAlgorithm[algorithm] if hasattr(KeyAlgorithm, algorithm) else None

        return await self._kms_provider.sign(full_key_id, payload, algorithm=key_algo)

    async def rotate_issuer_key(
        self,
        issuer_id: str,
        key_id: str,
        *,
        new_expires_in_days: int = 1095,
    ) -> CredentialKeyInfo:
        """Rotate an issuer key."""
        full_key_id = CredentialKeyPrefix.issuer_key_id(issuer_id, key_id)
        new_expires_at = datetime.now(timezone.utc) + timedelta(days=new_expires_in_days)

        key_material = await self._kms_provider.rotate_key(
            full_key_id,
            new_expires_at=new_expires_at,
        )

        key_identity = KeyIdentity(
            role=CryptoRole.DSC,
            purpose=KeyPurpose.DOCUMENT_SIGNING,
            key_id=key_id,
            issuer_identifier=issuer_id,
        )

        return CredentialKeyInfo(
            key_id=full_key_id,
            crypto_role=CryptoRole.DSC,
            key_purpose=KeyPurpose.DOCUMENT_SIGNING,
            key_identity=key_identity,
            public_key_pem=key_material.public_key_pem,
            public_key_jwk=key_material.public_key_jwk,
            issuer_identifier=issuer_id,
            created_at=key_material.metadata.created_at,
            expires_at=new_expires_at,
            is_hardware_backed=key_material.metadata.is_hardware_backed,
        )

    async def generate_holder_binding_key(
        self,
        device_id: str,
        credential_id: str,
        *,
        algorithm: str = "ES256",
    ) -> CredentialKeyInfo:
        """Generate a holder binding key for a credential."""
        from mmf.core.security.ports.kms import KeyAlgorithm

        key_identity = KeyIdentity(
            role=CryptoRole.HOLDER,
            purpose=KeyPurpose.DEVICE_BINDING,
            key_id=credential_id,
            device_identifier=device_id,
        )

        full_key_id = CredentialKeyPrefix.holder_key_id(device_id, credential_id)

        # Holder keys are typically ephemeral
        policy = get_role_policy(CryptoRole.HOLDER)
        expires_at = None
        if policy.max_key_lifetime_days:
            expires_at = datetime.now(timezone.utc) + timedelta(days=policy.max_key_lifetime_days)

        key_algo = KeyAlgorithm[algorithm] if hasattr(KeyAlgorithm, algorithm) else KeyAlgorithm.ES256
        key_material = await self._kms_provider.generate_key(
            key_id=full_key_id,
            algorithm=key_algo,
            expires_at=expires_at,
            require_hardware=False,  # Holder keys don't require HSM
            labels={"role": CryptoRole.HOLDER.value, "device": device_id},
        )

        return CredentialKeyInfo(
            key_id=full_key_id,
            crypto_role=CryptoRole.HOLDER,
            key_purpose=KeyPurpose.DEVICE_BINDING,
            key_identity=key_identity,
            public_key_pem=key_material.public_key_pem,
            public_key_jwk=key_material.public_key_jwk,
            device_identifier=device_id,
            created_at=key_material.metadata.created_at,
            expires_at=expires_at,
            is_hardware_backed=key_material.metadata.is_hardware_backed,
        )

    async def get_holder_binding_key(
        self,
        device_id: str,
        credential_id: str,
    ) -> CredentialKeyInfo | None:
        """Get a holder binding key."""
        full_key_id = CredentialKeyPrefix.holder_key_id(device_id, credential_id)
        metadata = await self._kms_provider.get_key_metadata(full_key_id)
        if not metadata:
            return None

        public_key_pem = await self._kms_provider.get_public_key(full_key_id)
        public_key_jwk = await self._kms_provider.get_public_key_jwk(full_key_id)

        key_identity = KeyIdentity(
            role=CryptoRole.HOLDER,
            purpose=KeyPurpose.DEVICE_BINDING,
            key_id=credential_id,
            device_identifier=device_id,
        )

        return CredentialKeyInfo(
            key_id=full_key_id,
            crypto_role=CryptoRole.HOLDER,
            key_purpose=KeyPurpose.DEVICE_BINDING,
            key_identity=key_identity,
            public_key_pem=public_key_pem,
            public_key_jwk=public_key_jwk,
            device_identifier=device_id,
            created_at=metadata.created_at,
            expires_at=metadata.expires_at,
            is_hardware_backed=metadata.is_hardware_backed,
        )

    async def sign_presentation(
        self,
        device_id: str,
        credential_id: str,
        payload: bytes,
    ) -> bytes:
        """Sign a credential presentation."""
        full_key_id = CredentialKeyPrefix.holder_key_id(device_id, credential_id)

        # Validate role separation
        key_identity = KeyIdentity(
            role=CryptoRole.HOLDER,
            purpose=KeyPurpose.DEVICE_BINDING,
            key_id=credential_id,
            device_identifier=device_id,
        )
        self._enforcer.validate_key_operation(key_identity, "sign", CryptoRole.HOLDER)

        return await self._kms_provider.sign(full_key_id, payload)

    async def generate_vdsnc_key(
        self,
        country_code: str,
        role: str,
        generation: int,
        *,
        algorithm: str = "ES256",
        expires_in_days: int = 1095,
    ) -> CredentialKeyInfo:
        """Generate a VDS-NC signing key."""
        from mmf.core.security.ports.kms import KeyAlgorithm

        key_id = f"{country_code}-{role}-gen{generation}"
        key_identity = KeyIdentity(
            role=CryptoRole.DSC,
            purpose=KeyPurpose.VDS_NC_SIGNING,
            key_id=key_id,
            issuer_identifier=country_code,
        )

        full_key_id = CredentialKeyPrefix.vdsnc_key_id(country_code, role, generation)
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)

        key_algo = KeyAlgorithm[algorithm] if hasattr(KeyAlgorithm, algorithm) else KeyAlgorithm.ES256
        key_material = await self._kms_provider.generate_key(
            key_id=full_key_id,
            algorithm=key_algo,
            expires_at=expires_at,
            require_hardware=True,  # VDS-NC keys require HSM
            labels={"role": CryptoRole.DSC.value, "country": country_code, "generation": str(generation)},
        )

        return CredentialKeyInfo(
            key_id=full_key_id,
            crypto_role=CryptoRole.DSC,
            key_purpose=KeyPurpose.VDS_NC_SIGNING,
            key_identity=key_identity,
            public_key_pem=key_material.public_key_pem,
            public_key_jwk=key_material.public_key_jwk,
            issuer_identifier=country_code,
            created_at=key_material.metadata.created_at,
            expires_at=expires_at,
            is_hardware_backed=key_material.metadata.is_hardware_backed,
        )

    async def sign_vdsnc(
        self,
        country_code: str,
        role: str,
        generation: int,
        payload: bytes,
    ) -> bytes:
        """Sign a VDS-NC document."""
        full_key_id = CredentialKeyPrefix.vdsnc_key_id(country_code, role, generation)

        key_id = f"{country_code}-{role}-gen{generation}"
        key_identity = KeyIdentity(
            role=CryptoRole.DSC,
            purpose=KeyPurpose.VDS_NC_SIGNING,
            key_id=key_id,
            issuer_identifier=country_code,
        )
        self._enforcer.validate_key_operation(key_identity, "sign", CryptoRole.DSC)

        return await self._kms_provider.sign(full_key_id, payload)

    async def generate_evidence_key(
        self,
        service_id: str,
        *,
        algorithm: str = "ES256",
        expires_in_days: int = 1095,
    ) -> CredentialKeyInfo:
        """Generate an evidence signing key."""
        from mmf.core.security.ports.kms import KeyAlgorithm

        key_identity = KeyIdentity(
            role=CryptoRole.EVIDENCE,
            purpose=KeyPurpose.EVIDENCE_SIGNING,
            key_id=service_id,
        )

        full_key_id = CredentialKeyPrefix.evidence_key_id(service_id)
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)

        key_algo = KeyAlgorithm[algorithm] if hasattr(KeyAlgorithm, algorithm) else KeyAlgorithm.ES256
        key_material = await self._kms_provider.generate_key(
            key_id=full_key_id,
            algorithm=key_algo,
            expires_at=expires_at,
            require_hardware=False,  # Evidence keys prefer HSM but don't require
            labels={"role": CryptoRole.EVIDENCE.value, "service": service_id},
        )

        return CredentialKeyInfo(
            key_id=full_key_id,
            crypto_role=CryptoRole.EVIDENCE,
            key_purpose=KeyPurpose.EVIDENCE_SIGNING,
            key_identity=key_identity,
            public_key_pem=key_material.public_key_pem,
            public_key_jwk=key_material.public_key_jwk,
            created_at=key_material.metadata.created_at,
            expires_at=expires_at,
            is_hardware_backed=key_material.metadata.is_hardware_backed,
        )

    async def sign_evidence(
        self,
        service_id: str,
        payload: bytes,
    ) -> bytes:
        """Sign evidence/audit data."""
        full_key_id = CredentialKeyPrefix.evidence_key_id(service_id)

        key_identity = KeyIdentity(
            role=CryptoRole.EVIDENCE,
            purpose=KeyPurpose.EVIDENCE_SIGNING,
            key_id=service_id,
        )
        self._enforcer.validate_key_operation(key_identity, "sign", CryptoRole.EVIDENCE)

        return await self._kms_provider.sign(full_key_id, payload)

    async def list_credential_keys(
        self,
        *,
        role: CryptoRole | None = None,
        issuer_id: str | None = None,
    ) -> list[CredentialKeyInfo]:
        """List credential keys with optional filtering."""
        labels = {}
        if role:
            labels["role"] = role.value
        if issuer_id:
            labels["issuer"] = issuer_id

        keys = await self._kms_provider.list_keys(
            namespace="cred",
            labels=labels if labels else None,
        )

        result = []
        for metadata in keys:
            crypto_role = CredentialKeyPrefix.get_crypto_role(metadata.key_id)
            if crypto_role:
                result.append(
                    CredentialKeyInfo(
                        key_id=metadata.key_id,
                        crypto_role=crypto_role,
                        key_purpose=KeyPurpose.DOCUMENT_SIGNING,  # Default, would need more context
                        key_identity=KeyIdentity(
                            role=crypto_role,
                            purpose=KeyPurpose.DOCUMENT_SIGNING,
                            key_id=metadata.key_id.split(":")[-1],
                        ),
                        public_key_pem=b"",  # Would need to fetch
                        created_at=metadata.created_at,
                        expires_at=metadata.expires_at,
                        is_hardware_backed=metadata.is_hardware_backed,
                    )
                )
        return result

    async def delete_credential_key(self, key_id: str) -> bool:
        """Delete a credential key."""
        if not CredentialKeyPrefix.is_credential_key(key_id):
            raise ValueError(f"Not a credential key: {key_id}")
        return await self._kms_provider.delete_key(key_id)

    async def validate_key_operation(
        self,
        key_id: str,
        operation: str,
        requesting_role: CryptoRole,
    ) -> None:
        """Validate that a key operation is allowed."""
        if not CredentialKeyPrefix.is_credential_key(key_id):
            raise ValueError(f"Not a credential key: {key_id}")

        crypto_role = CredentialKeyPrefix.get_crypto_role(key_id)
        if not crypto_role:
            raise ValueError(f"Cannot determine role for key: {key_id}")

        # Create a minimal key identity for validation
        key_identity = KeyIdentity(
            role=crypto_role,
            purpose=KeyPurpose.DOCUMENT_SIGNING,  # Default purpose
            key_id=key_id.split(":")[-1],
        )

        self._enforcer.validate_key_operation(key_identity, operation, requesting_role)
