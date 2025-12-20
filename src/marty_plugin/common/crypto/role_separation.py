"""
Crypto Role Separation Architecture for Marty

This module defines strict separation of cryptographic roles and key management
to ensure proper security boundaries between different actors in the system.

Key Principles:
1. CSCA/DSC keys (issuing authorities) must never mix with reader/verifier keys
2. Wallet/holder keys must be completely isolated from issuer/verifier keys
3. All private key operations must go through KMS/HSM providers
4. Verification outcomes must be signed for tamper-evident audit logs
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Dict, Optional, Protocol, Union

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa


class CryptoRole(Enum):
    """Defines the cryptographic roles in the system with strict separation."""

    # Issuing Authority roles (private keys must never be exposed)
    CSCA = "csca"  # Country Signing Certificate Authority
    DSC = "dsc"  # Document Signer Certificate

    # Verification roles (only need public keys)
    READER = "reader"  # Document reader/scanner
    VERIFIER = "verifier"  # Verification service

    # End-user roles (completely separate key space)
    WALLET = "wallet"  # Digital wallet
    HOLDER = "holder"  # Document holder/owner

    # Infrastructure roles
    AUDIT = "audit"  # Audit log signing
    EVIDENCE = "evidence"  # Evidence/outcome signing


class KeyPurpose(Enum):
    """Specific purposes for cryptographic keys."""

    # Issuing purposes
    CERTIFICATE_SIGNING = auto()
    DOCUMENT_SIGNING = auto()
    VDS_NC_SIGNING = auto()

    # Verification purposes
    SIGNATURE_VERIFICATION = auto()
    CERTIFICATE_VALIDATION = auto()

    # Holder/Wallet purposes
    DEVICE_BINDING = auto()
    SESSION_ESTABLISHMENT = auto()
    EPHEMERAL_COMMUNICATION = auto()

    # Infrastructure purposes
    AUDIT_LOGGING = auto()
    EVIDENCE_SIGNING = auto()
    SECURE_MESSAGING = auto()


class SecurityLevel(Enum):
    """Security levels for key material."""

    HSM_REQUIRED = "hsm_required"  # Must use Hardware Security Module
    HSM_PREFERRED = "hsm_preferred"  # HSM preferred, soft allowed for dev
    SOFTWARE_OK = "software_ok"  # Software keys acceptable
    EPHEMERAL_ONLY = "ephemeral_only"  # Keys should not be persisted


@dataclass(frozen=True)
class RoleKeyPolicy:
    """Policy defining key handling requirements for a role."""

    role: CryptoRole
    purposes: list[KeyPurpose]
    security_level: SecurityLevel
    max_key_lifetime_days: int | None
    requires_audit: bool
    can_cross_boundaries: bool = False  # Whether keys can be used across role boundaries

    def is_compatible_purpose(self, purpose: KeyPurpose) -> bool:
        """Check if a key purpose is allowed for this role."""
        return purpose in self.purposes

    def requires_hsm(self) -> bool:
        """Check if this role requires HSM backing."""
        return self.security_level == SecurityLevel.HSM_REQUIRED


# Role-based key policies with strict separation
ROLE_POLICIES: dict[CryptoRole, RoleKeyPolicy] = {
    CryptoRole.CSCA: RoleKeyPolicy(
        role=CryptoRole.CSCA,
        purposes=[KeyPurpose.CERTIFICATE_SIGNING],
        security_level=SecurityLevel.HSM_REQUIRED,
        max_key_lifetime_days=3650,  # 10 years max
        requires_audit=True,
        can_cross_boundaries=False,
    ),
    CryptoRole.DSC: RoleKeyPolicy(
        role=CryptoRole.DSC,
        purposes=[KeyPurpose.DOCUMENT_SIGNING, KeyPurpose.VDS_NC_SIGNING],
        security_level=SecurityLevel.HSM_REQUIRED,
        max_key_lifetime_days=1095,  # 3 years max
        requires_audit=True,
        can_cross_boundaries=False,
    ),
    CryptoRole.READER: RoleKeyPolicy(
        role=CryptoRole.READER,
        purposes=[KeyPurpose.SIGNATURE_VERIFICATION, KeyPurpose.CERTIFICATE_VALIDATION],
        security_level=SecurityLevel.SOFTWARE_OK,
        max_key_lifetime_days=None,  # Public keys don't expire
        requires_audit=True,
        can_cross_boundaries=False,
    ),
    CryptoRole.VERIFIER: RoleKeyPolicy(
        role=CryptoRole.VERIFIER,
        purposes=[KeyPurpose.SIGNATURE_VERIFICATION, KeyPurpose.CERTIFICATE_VALIDATION],
        security_level=SecurityLevel.SOFTWARE_OK,
        max_key_lifetime_days=None,
        requires_audit=True,
        can_cross_boundaries=False,
    ),
    CryptoRole.WALLET: RoleKeyPolicy(
        role=CryptoRole.WALLET,
        purposes=[KeyPurpose.DEVICE_BINDING, KeyPurpose.SESSION_ESTABLISHMENT],
        security_level=SecurityLevel.SOFTWARE_OK,
        max_key_lifetime_days=365,  # 1 year max
        requires_audit=False,
        can_cross_boundaries=False,
    ),
    CryptoRole.HOLDER: RoleKeyPolicy(
        role=CryptoRole.HOLDER,
        purposes=[KeyPurpose.EPHEMERAL_COMMUNICATION, KeyPurpose.SESSION_ESTABLISHMENT],
        security_level=SecurityLevel.EPHEMERAL_ONLY,
        max_key_lifetime_days=1,  # Very short-lived
        requires_audit=False,
        can_cross_boundaries=False,
    ),
    CryptoRole.AUDIT: RoleKeyPolicy(
        role=CryptoRole.AUDIT,
        purposes=[KeyPurpose.AUDIT_LOGGING],
        security_level=SecurityLevel.HSM_PREFERRED,
        max_key_lifetime_days=1095,  # 3 years
        requires_audit=True,
        can_cross_boundaries=False,
    ),
    CryptoRole.EVIDENCE: RoleKeyPolicy(
        role=CryptoRole.EVIDENCE,
        purposes=[KeyPurpose.EVIDENCE_SIGNING],
        security_level=SecurityLevel.HSM_PREFERRED,
        max_key_lifetime_days=1095,  # 3 years
        requires_audit=True,
        can_cross_boundaries=False,
    ),
}


class RoleBoundaryViolation(Exception):
    """Raised when attempting to use keys across role boundaries."""

    pass


class KeyPurposeMismatch(Exception):
    """Raised when using a key for an incompatible purpose."""

    pass


@dataclass(frozen=True)
class KeyIdentity:
    """Unique identity for a cryptographic key with role information."""

    role: CryptoRole
    purpose: KeyPurpose
    key_id: str
    issuer_identifier: str | None = None  # For issuing authorities
    device_identifier: str | None = None  # For devices/wallets

    def __post_init__(self):
        """Validate key identity constraints."""
        policy = ROLE_POLICIES[self.role]
        if not policy.is_compatible_purpose(self.purpose):
            raise KeyPurposeMismatch(f"Purpose {self.purpose} not allowed for role {self.role}")

    @property
    def full_key_id(self) -> str:
        """Generate a unique key identifier including role and purpose."""
        parts = [self.role.value, self.purpose.name.lower(), self.key_id]
        if self.issuer_identifier:
            parts.append(self.issuer_identifier)
        if self.device_identifier:
            parts.append(self.device_identifier)
        return ":".join(parts)


class RoleSeparationEnforcer:
    """Enforces strict separation between cryptographic roles."""

    @staticmethod
    def validate_key_operation(
        key_identity: KeyIdentity, operation: str, requesting_role: CryptoRole
    ) -> None:
        """Validate that a key operation respects role boundaries."""

        # Check if the requesting role can use this key
        if key_identity.role != requesting_role:
            if not ROLE_POLICIES[key_identity.role].can_cross_boundaries:
                raise RoleBoundaryViolation(
                    f"Role {requesting_role} cannot use {key_identity.role} keys"
                )

        # Check specific operation constraints
        if operation == "sign" and key_identity.role in [CryptoRole.READER, CryptoRole.VERIFIER]:
            raise RoleBoundaryViolation("Reader/Verifier roles cannot perform signing operations")

        if operation in ["decrypt", "unwrap"] and key_identity.role == CryptoRole.HOLDER:
            # Holders should only decrypt their own data
            pass

    @staticmethod
    def validate_key_sharing(
        source_role: CryptoRole, target_role: CryptoRole, key_purpose: KeyPurpose
    ) -> None:
        """Validate if key material can be shared between roles."""

        # Issuing authority private keys must never be shared
        if source_role in [CryptoRole.CSCA, CryptoRole.DSC]:
            if key_purpose in [KeyPurpose.CERTIFICATE_SIGNING, KeyPurpose.DOCUMENT_SIGNING]:
                raise RoleBoundaryViolation(f"Private keys from {source_role} cannot be shared")

        # Public keys can be shared for verification
        if key_purpose in [KeyPurpose.SIGNATURE_VERIFICATION, KeyPurpose.CERTIFICATE_VALIDATION]:
            return  # Public key sharing is OK

        # Wallet/Holder keys must remain isolated
        if source_role in [CryptoRole.WALLET, CryptoRole.HOLDER]:
            if target_role not in [CryptoRole.WALLET, CryptoRole.HOLDER]:
                raise RoleBoundaryViolation(
                    f"Wallet/Holder keys cannot be shared with {target_role}"
                )


def get_role_policy(role: CryptoRole) -> RoleKeyPolicy:
    """Get the key policy for a specific role."""
    return ROLE_POLICIES[role]


def validate_role_compatibility(role: CryptoRole, purpose: KeyPurpose) -> bool:
    """Check if a role is compatible with a key purpose."""
    policy = ROLE_POLICIES[role]
    return policy.is_compatible_purpose(purpose)


# Example usage and factories
def create_csca_key_identity(country_code: str, generation: int = 1) -> KeyIdentity:
    """Create a key identity for a CSCA key."""
    return KeyIdentity(
        role=CryptoRole.CSCA,
        purpose=KeyPurpose.CERTIFICATE_SIGNING,
        key_id=f"csca-{country_code}-gen{generation}",
        issuer_identifier=country_code,
    )


def create_dsc_key_identity(country_code: str, signer_id: str, generation: int = 1) -> KeyIdentity:
    """Create a key identity for a DSC key."""
    return KeyIdentity(
        role=CryptoRole.DSC,
        purpose=KeyPurpose.DOCUMENT_SIGNING,
        key_id=f"dsc-{country_code}-{signer_id}-gen{generation}",
        issuer_identifier=country_code,
    )


def create_wallet_key_identity(device_id: str) -> KeyIdentity:
    """Create a key identity for a wallet key."""
    return KeyIdentity(
        role=CryptoRole.WALLET,
        purpose=KeyPurpose.DEVICE_BINDING,
        key_id=f"wallet-{device_id}",
        device_identifier=device_id,
    )


def create_evidence_key_identity(service_id: str) -> KeyIdentity:
    """Create a key identity for evidence signing."""
    return KeyIdentity(
        role=CryptoRole.EVIDENCE,
        purpose=KeyPurpose.EVIDENCE_SIGNING,
        key_id=f"evidence-{service_id}",
    )
