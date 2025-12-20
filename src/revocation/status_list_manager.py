"""
Status List Manager

Manages Token Status Lists (IETF) and Bitstring Status Lists (W3C).
Provides shard-based storage and efficient status updates.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class StatusListFormat(str, Enum):
    """Status list format types."""
    TOKEN_STATUS_LIST = "tsl"      # IETF draft-14 for mDoc
    BITSTRING_STATUS_LIST = "bitstring"  # W3C v1.0 for SD-JWT VC


@dataclass
class StatusListShard:
    """A shard of a status list."""
    id: str
    format: StatusListFormat
    issuer_id: Optional[str]
    size: int
    data: bytes
    next_index: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class StatusListManager:
    """
    Manages status lists for credential revocation.
    
    Features:
    - Format-per-credential-type support
    - Shard-based storage for scalability
    - Efficient status lookups and updates
    - Integration with Rust ssi-status bindings
    """
    
    DEFAULT_SHARD_SIZE = 100000  # 100K entries per shard
    
    def __init__(
        self,
        storage: Optional[Any] = None,  # Database or cache storage
        shard_size: int = DEFAULT_SHARD_SIZE,
    ):
        """
        Initialize the status list manager.
        
        Args:
            storage: Optional storage backend
            shard_size: Number of entries per shard
        """
        # Import Rust bindings (required)
        from _marty_rs import TokenStatusList, BitstringStatusList  # noqa: F401
        
        self._storage = storage
        self._shard_size = shard_size
        
        # In-memory shard cache
        self._shards: dict[str, StatusListShard] = {}
        
        # Credential ID to (shard_id, index) mapping
        self._credential_index: dict[str, tuple[str, int]] = {}
    
    async def set_status(
        self,
        credential_id: str,
        status: int,
        format_type: StatusListFormat,
        issuer_id: Optional[str] = None,
    ) -> int:
        """
        Set the status for a credential.
        
        Args:
            credential_id: The credential identifier
            status: Status code (0 = valid, 1 = revoked, etc.)
            format_type: The status list format
            issuer_id: Optional issuer for list selection
            
        Returns:
            The status list index assigned to this credential
        """
        # Check if credential already has an index
        if credential_id in self._credential_index:
            shard_id, index = self._credential_index[credential_id]
            shard = self._shards.get(shard_id)
            if shard:
                self._set_status_in_shard(shard, index, status)
                shard.updated_at = datetime.now(timezone.utc)
                await self._persist_shard(shard)
                return index
        
        # Get or create shard
        shard = await self._get_or_create_shard(format_type, issuer_id)
        
        # Allocate index
        index = shard.next_index
        shard.next_index += 1
        
        # Set status
        self._set_status_in_shard(shard, index, status)
        shard.updated_at = datetime.now(timezone.utc)
        
        # Record mapping
        self._credential_index[credential_id] = (shard.id, index)
        
        # Persist
        await self._persist_shard(shard)
        
        return index
    
    async def get_status(
        self,
        credential_id: str,
        format_type: StatusListFormat,
        issuer_id: Optional[str] = None,
    ) -> int:
        """
        Get the status for a credential.
        
        Args:
            credential_id: The credential identifier
            format_type: The status list format
            issuer_id: Optional issuer for list selection
            
        Returns:
            Status code (0 = valid, 1 = revoked, etc.)
        """
        if credential_id not in self._credential_index:
            return 0  # Not found = valid
        
        shard_id, index = self._credential_index[credential_id]
        shard = self._shards.get(shard_id)
        
        if not shard:
            shard = await self._load_shard(shard_id)
            if not shard:
                return 0
        
        return self._get_status_from_shard(shard, index)
    
    async def get_status_list_credential(
        self,
        shard_id: str,
        issuer_did: str,
        issuer_key: Any,
    ) -> dict[str, Any]:
        """
        Get a status list as a verifiable credential.
        
        Args:
            shard_id: The shard identifier
            issuer_did: The issuer DID
            issuer_key: The issuer signing key
            
        Returns:
            Status list credential (JWT or CBOR depending on format)
        """
        shard = self._shards.get(shard_id)
        if not shard:
            shard = await self._load_shard(shard_id)
            if not shard:
                raise ValueError(f"Shard not found: {shard_id}")
        
        if shard.format == StatusListFormat.TOKEN_STATUS_LIST:
            return self._build_tsl_credential(shard, issuer_did, issuer_key)
        else:
            return self._build_bitstring_credential(shard, issuer_did, issuer_key)
    
    def _set_status_in_shard(
        self,
        shard: StatusListShard,
        index: int,
        status: int,
    ) -> None:
        """Set status at index in shard using Rust bindings."""
        from _marty_rs import TokenStatusList, BitstringStatusList
        
        if shard.format == StatusListFormat.TOKEN_STATUS_LIST:
            tsl = TokenStatusList.from_cbor(shard.data)
            tsl.set_status(index, status)
            shard.data = tsl.to_cbor()
        else:
            bsl = BitstringStatusList.from_base64(shard.data.decode())
            bsl.set_status(index, status == 1)
            shard.data = bsl.to_base64().encode()
    
    def _get_status_from_shard(
        self,
        shard: StatusListShard,
        index: int,
    ) -> int:
        """Get status at index from shard using Rust bindings."""
        from _marty_rs import TokenStatusList, BitstringStatusList
        
        if shard.format == StatusListFormat.TOKEN_STATUS_LIST:
            tsl = TokenStatusList.from_cbor(shard.data)
            return tsl.get_status(index)
        else:
            bsl = BitstringStatusList.from_base64(shard.data.decode())
            return 1 if bsl.get_status(index) else 0
    
    async def _get_or_create_shard(
        self,
        format_type: StatusListFormat,
        issuer_id: Optional[str],
    ) -> StatusListShard:
        """Get an existing shard with space or create a new one."""
        # Look for existing shard with space
        for shard in self._shards.values():
            if (
                shard.format == format_type and
                shard.issuer_id == issuer_id and
                shard.next_index < self._shard_size
            ):
                return shard
        
        # Create new shard
        shard_id = self._generate_shard_id(format_type, issuer_id)
        
        if format_type == StatusListFormat.TOKEN_STATUS_LIST:
            # TSL: 1 byte per entry
            data = b'\x00' * 1000  # Start with 1000 entries
        else:
            # Bitstring: 1 bit per entry
            data = b'\x00' * 125  # 125 bytes = 1000 bits
        
        shard = StatusListShard(
            id=shard_id,
            format=format_type,
            issuer_id=issuer_id,
            size=self._shard_size,
            data=data,
        )
        
        self._shards[shard_id] = shard
        await self._persist_shard(shard)
        
        return shard
    
    def _generate_shard_id(
        self,
        format_type: StatusListFormat,
        issuer_id: Optional[str],
    ) -> str:
        """Generate a unique shard ID."""
        components = [
            format_type.value,
            issuer_id or "default",
            str(len(self._shards)),
            datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
        ]
        hash_input = ":".join(components)
        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]
    
    async def _persist_shard(self, shard: StatusListShard) -> None:
        """Persist shard to storage."""
        if self._storage is None:
            return  # In-memory only
        
        try:
            if hasattr(self._storage, 'set'):
                await self._storage.set(
                    f"shard:{shard.id}",
                    {
                        "id": shard.id,
                        "format": shard.format.value,
                        "issuer_id": shard.issuer_id,
                        "size": shard.size,
                        "data": shard.data.hex(),
                        "next_index": shard.next_index,
                        "created_at": shard.created_at.isoformat(),
                        "updated_at": shard.updated_at.isoformat(),
                    },
                )
        except Exception as e:
            logger.error(f"Failed to persist shard {shard.id}: {e}")
    
    async def _load_shard(self, shard_id: str) -> Optional[StatusListShard]:
        """Load shard from storage."""
        if self._storage is None:
            return None
        
        try:
            if hasattr(self._storage, 'get'):
                data = await self._storage.get(f"shard:{shard_id}")
                if data:
                    shard = StatusListShard(
                        id=data["id"],
                        format=StatusListFormat(data["format"]),
                        issuer_id=data["issuer_id"],
                        size=data["size"],
                        data=bytes.fromhex(data["data"]),
                        next_index=data["next_index"],
                        created_at=datetime.fromisoformat(data["created_at"]),
                        updated_at=datetime.fromisoformat(data["updated_at"]),
                    )
                    self._shards[shard_id] = shard
                    return shard
        except Exception as e:
            logger.error(f"Failed to load shard {shard_id}: {e}")
        
        return None
    
    def _build_tsl_credential(
        self,
        shard: StatusListShard,
        issuer_did: str,
        issuer_key: Any,
    ) -> dict[str, Any]:
        """Build Token Status List credential."""
        import base64
        import zlib
        
        # Compress data
        compressed = zlib.compress(shard.data)
        encoded = base64.urlsafe_b64encode(compressed).decode().rstrip('=')
        
        now = datetime.now(timezone.utc)
        
        return {
            "format": "tsl",
            "issuer": issuer_did,
            "issued_at": now.isoformat(),
            "status_list": {
                "bits": 8,  # TSL uses 8 bits per entry
                "lst": encoded,
            },
            "shard_id": shard.id,
            "total_entries": shard.next_index,
        }
    
    def _build_bitstring_credential(
        self,
        shard: StatusListShard,
        issuer_did: str,
        issuer_key: Any,
    ) -> dict[str, Any]:
        """Build Bitstring Status List credential."""
        import base64
        import zlib
        
        # Compress data
        compressed = zlib.compress(shard.data)
        encoded = base64.standard_b64encode(compressed).decode()
        
        now = datetime.now(timezone.utc)
        
        return {
            "@context": [
                "https://www.w3.org/ns/credentials/v2",
                "https://www.w3.org/ns/credentials/status/v1",
            ],
            "type": ["VerifiableCredential", "BitstringStatusListCredential"],
            "issuer": issuer_did,
            "validFrom": now.isoformat(),
            "credentialSubject": {
                "id": f"urn:uuid:{shard.id}",
                "type": "BitstringStatusList",
                "statusPurpose": "revocation",
                "encodedList": encoded,
            },
            "shard_id": shard.id,
            "total_entries": shard.next_index,
        }
