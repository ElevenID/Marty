"""
Domain value objects for the Status List bounded context.

Follows W3C Bitstring Status List v1.0 and IETF Token Status List specs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class StatusPurpose(str, Enum):
    """Status purpose per W3C Bitstring Status List v1.0 §4.4."""
    REVOCATION = "revocation"
    SUSPENSION = "suspension"
    MESSAGE = "message"


class StatusListFormat(str, Enum):
    """Status list encoding format."""
    BITSTRING = "bitstring"       # W3C Bitstring Status List v1.0
    TOKEN_STATUS_LIST = "tsl"     # IETF draft-ietf-oauth-status-list


class StatusValue(int, Enum):
    """Standard status values for Token Status List (2-bit)."""
    VALID = 0x00
    INVALID = 0x01      # Revoked (irreversible)
    SUSPENDED = 0x02    # Suspended (reversible)


@dataclass(frozen=True)
class ShardConfig:
    """Configuration for status list shard sizing.

    The minimum bitstring size per the W3C spec is 16 KB (131072 bits),
    which accommodates 131072 credential slots per shard.
    """
    shard_size: int = 131_072          # entries per shard (W3C minimum)
    format: StatusListFormat = StatusListFormat.BITSTRING
    ttl_seconds: int = 300             # 5 minutes (spec default)
    bits_per_status: int = 1           # 1 for bitstring, 2 for TSL


@dataclass
class StatusListEntry:
    """A credential's allocated slot in a status list shard."""
    credential_id: str
    shard_id: str
    index: int
    purpose: StatusPurpose
    status_list_credential_url: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class StatusListShard:
    """One shard of a status list.

    Shard data is the raw bitstring (BitstringStatusList) or status bytes
    (TokenStatusList) as produced by the Rust FFI layer.
    """
    id: str
    issuer_id: str
    purpose: StatusPurpose
    format: StatusListFormat
    credential_url: str          # URL where verifiers fetch this VC
    size: int                    # total capacity (entries)
    next_index: int = 0          # next unallocated slot
    encoded_list: Optional[str] = None  # cached encodedList string
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
