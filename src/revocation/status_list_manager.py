"""
Status List Manager

Manages Token Status Lists (IETF) and Bitstring Status Lists (W3C).
Provides shard-based storage and efficient status updates.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from marty_plugin.native_backends import NativeOperationError, require_backend

logger = logging.getLogger(__name__)


class StatusListFormat(str, Enum):
    """Status list format types."""

    TOKEN_STATUS_LIST = "tsl"  # IETF draft-14 for mDoc
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

    DEFAULT_SHARD_SIZE = 131_072  # W3C privacy floor: 16 KiB at one bit per entry

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
        if shard_size < self.DEFAULT_SHARD_SIZE:
            raise ValueError(
                f"Status-list shards require at least {self.DEFAULT_SHARD_SIZE} entries"
            )
        self._native = require_backend("_marty_rs")
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
            if shard is None:
                shard = await self._load_shard(shard_id)
            if shard is None:
                raise RuntimeError(
                    f"Mapped status-list shard is unavailable: {shard_id}"
                )
            self._validate_shard_binding(shard, format_type, issuer_id)
            old_data = shard.data
            old_updated_at = shard.updated_at
            self._set_status_in_shard(shard, index, status)
            shard.updated_at = datetime.now(timezone.utc)
            try:
                await self._persist_shard(shard)
            except Exception:
                shard.data = old_data
                shard.updated_at = old_updated_at
                raise
            return index

        # Get or create shard
        shard = await self._get_or_create_shard(format_type, issuer_id)

        # Allocate index
        index = shard.next_index
        old_data = shard.data
        old_updated_at = shard.updated_at
        shard.next_index += 1
        self._set_status_in_shard(shard, index, status)
        shard.updated_at = datetime.now(timezone.utc)
        try:
            await self._persist_shard(shard)
        except Exception:
            shard.data = old_data
            shard.next_index = index
            shard.updated_at = old_updated_at
            raise

        self._credential_index[credential_id] = (shard.id, index)

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
            raise NativeOperationError(
                f"Credential status mapping is unavailable: {credential_id}"
            )

        shard_id, index = self._credential_index[credential_id]
        shard = self._shards.get(shard_id)

        if not shard:
            shard = await self._load_shard(shard_id)
            if not shard:
                raise RuntimeError(
                    f"Mapped status-list shard is unavailable: {shard_id}"
                )

        self._validate_shard_binding(shard, format_type, issuer_id)

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
        del shard_id, issuer_did, issuer_key
        raise NativeOperationError(
            "Unsigned status-list credential construction is disabled. "
            "Issue and sign status-list credentials through the native credential service."
        )

    def _set_status_in_shard(
        self,
        shard: StatusListShard,
        index: int,
        status: int,
    ) -> None:
        """Set status at index in shard using Rust bindings."""
        if shard.format == StatusListFormat.TOKEN_STATUS_LIST:
            status_list = self._native.TokenStatusList.from_base64url(
                shard.data.decode("ascii"), shard.size, 8
            )
            status_list.set(index, status)
        else:
            if status not in (0, 1):
                raise ValueError("Bitstring status values must be 0 or 1")
            status_list = self._native.BitstringStatusList.from_base64url(
                self._bitstring_payload(shard.data), shard.size
            )
            status_list.set(index, status == 1)
        encoded = status_list.to_base64url().encode("ascii")
        shard.data = (
            b"u" + encoded
            if shard.format == StatusListFormat.BITSTRING_STATUS_LIST
            else encoded
        )

    def _get_status_from_shard(
        self,
        shard: StatusListShard,
        index: int,
    ) -> int:
        """Get status at index from shard using Rust bindings."""
        if shard.format == StatusListFormat.TOKEN_STATUS_LIST:
            status_list = self._native.TokenStatusList.from_base64url(
                shard.data.decode("ascii"), shard.size, 8
            )
            return status_list.get(index)
        status_list = self._native.BitstringStatusList.from_base64url(
            self._bitstring_payload(shard.data), shard.size
        )
        return 1 if status_list.get(index) else 0

    @staticmethod
    def _bitstring_payload(data: bytes) -> str:
        """Remove the W3C multibase marker before passing data to Rust."""
        encoded = data.decode("ascii")
        if not encoded.startswith("u"):
            raise NativeOperationError(
                "Bitstring status list is missing its multibase prefix"
            )
        return encoded[1:]

    @staticmethod
    def _validate_shard_binding(
        shard: StatusListShard,
        format_type: StatusListFormat,
        issuer_id: Optional[str],
    ) -> None:
        if shard.format != format_type or shard.issuer_id != issuer_id:
            raise ValueError(
                "Credential status mapping does not match format and issuer"
            )

    async def _get_or_create_shard(
        self,
        format_type: StatusListFormat,
        issuer_id: Optional[str],
    ) -> StatusListShard:
        """Get an existing shard with space or create a new one."""
        # Look for existing shard with space
        for shard in self._shards.values():
            if (
                shard.format == format_type
                and shard.issuer_id == issuer_id
                and shard.next_index < self._shard_size
            ):
                return shard

        # Create new shard
        shard_id = self._generate_shard_id(format_type, issuer_id)

        if format_type == StatusListFormat.TOKEN_STATUS_LIST:
            status_list = self._native.TokenStatusList(self._shard_size, 8)
        else:
            status_list = self._native.BitstringStatusList(self._shard_size)
        data = status_list.to_base64url().encode("ascii")
        if format_type == StatusListFormat.BITSTRING_STATUS_LIST:
            data = b"u" + data

        shard = StatusListShard(
            id=shard_id,
            format=format_type,
            issuer_id=issuer_id,
            size=self._shard_size,
            data=data,
        )

        self._shards[shard_id] = shard
        try:
            await self._persist_shard(shard)
        except Exception:
            self._shards.pop(shard_id, None)
            raise

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
        return self._native.sha256(hash_input.encode()).hex()[:16]

    async def _persist_shard(self, shard: StatusListShard) -> None:
        """Persist shard to storage."""
        if self._storage is None:
            return  # In-memory only

        try:
            if hasattr(self._storage, "set"):
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
            raise

    async def _load_shard(self, shard_id: str) -> Optional[StatusListShard]:
        """Load shard from storage."""
        if self._storage is None:
            return None

        try:
            if hasattr(self._storage, "get"):
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
            raise

        return None
