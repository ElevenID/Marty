"""
StatusListService — application-layer orchestrator for credential status management.

Manages the lifecycle of status list shards and entries, backed by the Rust
BitstringStatusList / TokenStatusList FFI bindings.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from status_list.domain.value_objects import (
    ShardConfig,
    StatusListEntry,
    StatusListFormat,
    StatusListShard,
    StatusPurpose,
)

logger = logging.getLogger(__name__)


@dataclass
class AllocatedEntry:
    """Result of allocating a status list entry."""
    shard_id: str
    shard_index: int
    bit_index: int
    status_list_credential_url: str
    purpose: str


class StatusListService:
    """
    Manages status list shards and entry allocation.

    Provides:
    - allocate_status_entry: assign an index in a shard for a new credential
    - revoke_credential: flip the bit in the status list
    - suspend_credential / unsuspend_credential: reversible status changes
    - get_status_list_credential: produce the publishable VC

    The heavy bitstring manipulation (encoding, decoding, gzip, multibase)
    is delegated to the Rust ``_marty_rs.BitstringStatusList`` class.
    """

    def __init__(
        self,
        status_list_repository: Any,
        status_entry_repository: Any,
        event_publisher: Any | None = None,
        default_config: ShardConfig | None = None,
    ):
        self._shard_repo = status_list_repository
        self._entry_repo = status_entry_repository
        self._event_publisher = event_publisher
        self._config = default_config or ShardConfig()

        # In-memory shard cache (shard_id → StatusListShard)
        self._shards: dict[str, StatusListShard] = {}
        # In-memory Rust BitstringStatusList objects (shard_id → rust obj)
        self._rust_lists: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def allocate_status_entry(
        self,
        credential_id: str,
        issuer_id: str,
        purpose: StatusPurpose = StatusPurpose.REVOCATION,
    ) -> AllocatedEntry:
        """
        Allocate a status list slot for a new credential.

        This is called during credential issuance.  Returns the shard_id +
        index that must be embedded in the credential's ``credentialStatus``.
        """
        shard = await self._get_or_create_shard(issuer_id, purpose)
        index = shard.next_index

        # Record the entry
        entry = StatusListEntry(
            credential_id=credential_id,
            shard_id=shard.id,
            index=index,
            purpose=purpose,
            status_list_credential_url=shard.credential_url,
        )

        # Advance the shard pointer
        shard.next_index += 1
        shard.updated_at = datetime.now(timezone.utc)

        # Persist
        await self._entry_repo.save(entry)
        await self._shard_repo.save(shard)

        logger.info(
            "Allocated status index %d in shard %s for credential %s",
            index, shard.id, credential_id,
        )

        return AllocatedEntry(
            shard_id=shard.id,
            shard_index=0,  # shard_index within issuer (always 0 for now)
            bit_index=index,
            status_list_credential_url=shard.credential_url,
            purpose=purpose.value,
        )

    async def revoke_credential(
        self,
        credential_id: str,
        issuer_id: str,
    ) -> bool:
        """
        Revoke a credential by flipping its bit in the status list.

        Returns True if successful.
        """
        entry = await self._entry_repo.get_by_credential_id(credential_id)
        if not entry:
            logger.warning("No status entry found for credential %s", credential_id)
            return False

        rust_list = await self._get_rust_list(entry.shard_id)
        rust_list.set(entry.index, True)

        # Update cached encoded list
        shard = self._shards.get(entry.shard_id)
        if shard:
            shard.encoded_list = rust_list.to_base64url()
            shard.updated_at = datetime.now(timezone.utc)
            await self._shard_repo.save(shard)

        logger.info(
            "Revoked credential %s (shard=%s, index=%d)",
            credential_id, entry.shard_id, entry.index,
        )
        return True

    async def suspend_credential(
        self,
        credential_id: str,
        issuer_id: str,
    ) -> bool:
        """Suspend a credential (reversible)."""
        entry = await self._entry_repo.get_by_credential_id(credential_id)
        if not entry:
            return False
        if entry.purpose != StatusPurpose.SUSPENSION:
            logger.warning(
                "Cannot suspend credential %s — purpose is %s",
                credential_id, entry.purpose,
            )
            return False

        rust_list = await self._get_rust_list(entry.shard_id)
        rust_list.set(entry.index, True)

        shard = self._shards.get(entry.shard_id)
        if shard:
            shard.encoded_list = rust_list.to_base64url()
            shard.updated_at = datetime.now(timezone.utc)
            await self._shard_repo.save(shard)

        return True

    async def unsuspend_credential(
        self,
        credential_id: str,
        issuer_id: str,
    ) -> bool:
        """Lift suspension on a credential (reversible)."""
        entry = await self._entry_repo.get_by_credential_id(credential_id)
        if not entry:
            return False

        rust_list = await self._get_rust_list(entry.shard_id)
        rust_list.set(entry.index, False)

        shard = self._shards.get(entry.shard_id)
        if shard:
            shard.encoded_list = rust_list.to_base64url()
            shard.updated_at = datetime.now(timezone.utc)
            await self._shard_repo.save(shard)

        return True

    async def get_status_list_credential(
        self,
        shard_id: str,
        issuer_did: str,
    ) -> dict:
        """
        Build the full BitstringStatusListCredential VC for a shard.

        This is served at the ``statusListCredential`` URL that verifiers
        fetch to check credential status.  The returned dict is an unsigned
        W3C VC — the caller signs it (JWT-VC or Data Integrity).
        """
        import json
        from datetime import datetime, timezone

        rust_list = await self._get_rust_list(shard_id)
        shard = self._shards.get(shard_id)
        if not shard:
            raise ValueError(f"Shard not found: {shard_id}")

        # Build the BitstringStatusListCredential VC envelope in Python
        # Prefix with 'u' multibase header per W3C Bitstring Status List spec
        encoded_list = "u" + rust_list.to_base64url()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        credential = {
            "@context": [
                "https://www.w3.org/ns/credentials/v2",
            ],
            "id": shard.credential_url,
            "type": ["VerifiableCredential", "BitstringStatusListCredential"],
            "issuer": issuer_did,
            "validFrom": now,
            "credentialSubject": {
                "id": f"{shard.credential_url}#list",
                "type": "BitstringStatusList",
                "statusPurpose": shard.purpose.value,
                "encodedList": encoded_list,
            },
        }
        return credential

    async def get_credential_status(
        self,
        credential_id: str,
        issuer_id: str,
        purpose: StatusPurpose = StatusPurpose.REVOCATION,
    ) -> Optional[StatusListEntry]:
        """
        Look up a credential's status entry.

        Returns None if the credential has no entry (= valid).
        """
        entry = await self._entry_repo.get_by_credential_id(credential_id)
        if not entry:
            return None

        rust_list = await self._get_rust_list(entry.shard_id)
        revoked = rust_list.get(entry.index)
        entry._revoked = revoked  # type: ignore[attr-defined]
        return entry

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _get_or_create_shard(
        self,
        issuer_id: str,
        purpose: StatusPurpose,
    ) -> StatusListShard:
        """Find an existing shard with space or create a new one."""
        # Check in-memory cache
        for shard in self._shards.values():
            if (
                shard.issuer_id == issuer_id
                and shard.purpose == purpose
                and shard.next_index < shard.size
            ):
                return shard

        # Try loading from persistence
        existing = await self._shard_repo.find_active_shard(issuer_id, purpose.value)
        if existing:
            self._shards[existing.id] = existing
            return existing

        # Create new shard
        shard_id = hashlib.sha256(
            f"{issuer_id}:{purpose.value}:{uuid4()}".encode()
        ).hexdigest()[:16]

        credential_url = (
            f"https://status.marty.dev/{issuer_id}/credentials/status/{shard_id}"
        )

        shard = StatusListShard(
            id=shard_id,
            issuer_id=issuer_id,
            purpose=purpose,
            format=self._config.format,
            credential_url=credential_url,
            size=self._config.shard_size,
            next_index=0,
        )

        self._shards[shard_id] = shard

        # Create corresponding Rust object
        from _marty_rs import BitstringStatusList
        self._rust_lists[shard_id] = BitstringStatusList(size=shard.size)

        await self._shard_repo.save(shard)

        logger.info(
            "Created new status list shard %s for issuer=%s purpose=%s",
            shard_id, issuer_id, purpose.value,
        )
        return shard

    async def _get_rust_list(self, shard_id: str) -> Any:
        """Get or load the Rust BitstringStatusList for a shard."""
        if shard_id in self._rust_lists:
            return self._rust_lists[shard_id]

        # Load shard and decode its encoded_list
        shard = self._shards.get(shard_id)
        if not shard:
            shard = await self._shard_repo.get(shard_id)
            if shard:
                self._shards[shard_id] = shard

        if not shard:
            raise ValueError(f"Shard {shard_id} not found")

        from _marty_rs import BitstringStatusList

        if shard.encoded_list:
            rust_list = BitstringStatusList.from_base64url(shard.encoded_list)
        else:
            rust_list = BitstringStatusList(size=shard.size)

        self._rust_lists[shard_id] = rust_list
        return rust_list
