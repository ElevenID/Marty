"""
Trust Profile Port

Defines the unified trust validation interface that abstracts
multiple trust models (ICAO, AAMVA, EUDI, Custom).

This port provides a common interface for:
- Getting trust anchors
- Validating certificate chains
- Checking revocation status
- Refreshing trust data
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from digital_identity.domain.value_objects import TrustProfileType


class ValidationStatus(str, Enum):
    """Result status for validation operations."""
    
    VALID = "valid"
    INVALID = "invalid"
    UNKNOWN = "unknown"
    EXPIRED = "expired"
    REVOKED = "revoked"
    NOT_YET_VALID = "not_yet_valid"
    
    def __str__(self) -> str:
        return self.value


class RevocationStatus(str, Enum):
    """Certificate revocation status."""
    
    GOOD = "good"
    REVOKED = "revoked"
    UNKNOWN = "unknown"
    
    def __str__(self) -> str:
        return self.value


@dataclass
class TrustAnchor:
    """
    A trust anchor (root certificate or key).
    
    Represents a trusted entity that can sign credentials or certificates.
    """
    
    id: str
    subject: str
    issuer: str
    serial_number: str
    valid_from: datetime
    valid_until: datetime
    public_key_pem: str | None = None
    certificate_pem: str | None = None
    certificate_der: bytes | None = None
    key_usage: list[str] = field(default_factory=list)
    country_code: str | None = None
    jurisdiction: str | None = None  # For AAMVA
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChainValidationResult:
    """
    Result of certificate chain validation.
    
    Contains the validation status and details about the chain.
    """
    
    status: ValidationStatus
    trust_anchor_id: str | None = None
    chain_length: int = 0
    chain_path: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    validated_at: datetime = field(default_factory=datetime.now)
    
    @property
    def is_valid(self) -> bool:
        return self.status == ValidationStatus.VALID


@dataclass
class RevocationCheckResult:
    """
    Result of revocation status check.
    
    Contains the revocation status and source information.
    """
    
    status: RevocationStatus
    checked_via: str | None = None  # "ocsp", "crl", "status_list"
    revocation_date: datetime | None = None
    revocation_reason: int | None = None
    next_update: datetime | None = None
    errors: list[str] = field(default_factory=list)
    checked_at: datetime = field(default_factory=datetime.now)
    
    @property
    def is_good(self) -> bool:
        return self.status == RevocationStatus.GOOD


@dataclass
class RefreshResult:
    """
    Result of trust data refresh operation.
    
    Contains counts of updated trust data.
    """
    
    success: bool
    anchors_added: int = 0
    anchors_updated: int = 0
    anchors_removed: int = 0
    errors: list[str] = field(default_factory=list)
    refreshed_at: datetime = field(default_factory=datetime.now)


@runtime_checkable
class TrustProfilePort(Protocol):
    """
    Port for trust profile operations.
    
    This is the unified interface that abstracts different trust models.
    Implementations wrap specific trust sources (ICAO CSCA, AAMVA IACA, etc.)
    and provide a consistent validation interface.
    
    Each implementation handles:
    - Loading trust anchors from its specific source
    - Chain validation according to its trust model rules
    - Revocation checking via appropriate mechanisms
    - Periodic refresh of trust data
    """
    
    @property
    def profile_type(self) -> TrustProfileType:
        """Return the type of trust profile."""
        ...
    
    @property
    def profile_id(self) -> str:
        """Return the unique identifier for this profile."""
        ...
    
    async def get_trust_anchors(
        self,
        jurisdiction: str | None = None,
        country_code: str | None = None,
    ) -> list[TrustAnchor]:
        """
        Get trust anchors, optionally filtered.
        
        Args:
            jurisdiction: Filter by jurisdiction (for AAMVA)
            country_code: Filter by country code (for ICAO)
            
        Returns:
            List of trust anchors matching the filter
        """
        ...
    
    async def get_anchor_by_id(self, anchor_id: str) -> TrustAnchor | None:
        """
        Get a specific trust anchor by ID.
        
        Args:
            anchor_id: The anchor identifier
            
        Returns:
            TrustAnchor if found, None otherwise
        """
        ...
    
    async def validate_chain(
        self,
        certificate_pem: str | None = None,
        certificate_der: bytes | None = None,
    ) -> ChainValidationResult:
        """
        Validate a certificate chain against trust anchors.
        
        Args:
            certificate_pem: PEM-encoded certificate
            certificate_der: DER-encoded certificate
            
        Returns:
            ChainValidationResult with status and details
        """
        ...
    
    async def check_revocation(
        self,
        certificate_pem: str | None = None,
        certificate_der: bytes | None = None,
    ) -> RevocationCheckResult:
        """
        Check revocation status of a certificate.
        
        Args:
            certificate_pem: PEM-encoded certificate
            certificate_der: DER-encoded certificate
            
        Returns:
            RevocationCheckResult with status and details
        """
        ...
    
    async def refresh(self) -> RefreshResult:
        """
        Refresh trust data from external sources.
        
        Returns:
            RefreshResult with counts of changes
        """
        ...
    
    async def is_issuer_trusted(self, issuer_id: str) -> bool:
        """
        Check if an issuer is trusted by this profile.
        
        Args:
            issuer_id: Issuer identifier (DID, key ID, etc.)
            
        Returns:
            True if issuer is trusted
        """
        ...
