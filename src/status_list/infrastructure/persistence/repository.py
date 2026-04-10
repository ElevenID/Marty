"""
In-memory repositories for status list persistence.

These repositories satisfy the interface expected by StatusListService.
For production, replace with SQLAlchemy or other persistent backends.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from status_list.domain.value_objects import StatusListEntry, StatusListShard

logger = logging.getLogger(__name__)


class StatusListRepository:
    """Repository for StatusListShard objects."""

    def __init__(self, session_factory: Any = None):
        self._session_factory = session_factory
        self._store: dict[str, StatusListShard] = {}

    async def save(self, shard: StatusListShard) -> None:
        self._store[shard.id] = shard

    async def get(self, shard_id: str) -> Optional[StatusListShard]:
        return self._store.get(shard_id)

    async def find_active_shard(
        self,
        issuer_id: str,
        purpose: str,
    ) -> Optional[StatusListShard]:
        """Find a shard with remaining capacity for this issuer+purpose."""
        for shard in self._store.values():
            if (
                shard.issuer_id == issuer_id
                and shard.purpose.value == purpose
                and shard.next_index < shard.size
            ):
                return shard
        return None


class StatusEntryRepository:
    """Repository for StatusListEntry objects."""

    def __init__(self, session_factory: Any = None):
        self._session_factory = session_factory
        self._by_credential: dict[str, StatusListEntry] = {}
        self._by_shard: dict[str, list[StatusListEntry]] = {}

    async def save(self, entry: StatusListEntry) -> None:
        self._by_credential[entry.credential_id] = entry
        shard_entries = self._by_shard.setdefault(entry.shard_id, [])
        shard_entries.append(entry)

    async def get_by_credential_id(
        self, credential_id: str
    ) -> Optional[StatusListEntry]:
        return self._by_credential.get(credential_id)

    async def get_by_shard(
        self, shard_id: str
    ) -> list[StatusListEntry]:
        return self._by_shard.get(shard_id, [])
