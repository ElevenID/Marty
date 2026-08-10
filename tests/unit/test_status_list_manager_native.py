from __future__ import annotations

import pytest

from marty_plugin.native_backends import NativeOperationError
from revocation.status_list_manager import StatusListFormat, StatusListManager


class MemoryStorage:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}
        self.fail_writes = False

    async def set(self, key: str, value: object) -> None:
        if self.fail_writes:
            raise RuntimeError("storage unavailable")
        self.values[key] = value

    async def get(self, key: str) -> object | None:
        return self.values.get(key)


@pytest.mark.asyncio
async def test_status_mutation_roundtrips_through_native_formats() -> None:
    manager = StatusListManager()

    token_index = await manager.set_status(
        "mdoc-1", 2, StatusListFormat.TOKEN_STATUS_LIST, "issuer-1"
    )
    bitstring_index = await manager.set_status(
        "sd-jwt-1", 1, StatusListFormat.BITSTRING_STATUS_LIST, "issuer-1"
    )

    assert token_index == 0
    assert bitstring_index == 0
    assert (
        await manager.get_status(
            "mdoc-1", StatusListFormat.TOKEN_STATUS_LIST, "issuer-1"
        )
        == 2
    )
    assert (
        await manager.get_status(
            "sd-jwt-1", StatusListFormat.BITSTRING_STATUS_LIST, "issuer-1"
        )
        == 1
    )
    bitstring_shard = next(
        shard
        for shard in manager._shards.values()
        if shard.format == StatusListFormat.BITSTRING_STATUS_LIST
    )
    assert bitstring_shard.data.startswith(b"u")


@pytest.mark.asyncio
async def test_persistence_failure_rolls_back_native_status() -> None:
    storage = MemoryStorage()
    manager = StatusListManager(storage=storage)
    await manager.set_status(
        "mdoc-1", 1, StatusListFormat.TOKEN_STATUS_LIST, "issuer-1"
    )

    storage.fail_writes = True
    with pytest.raises(RuntimeError, match="storage unavailable"):
        await manager.set_status(
            "mdoc-1", 2, StatusListFormat.TOKEN_STATUS_LIST, "issuer-1"
        )

    assert (
        await manager.get_status(
            "mdoc-1", StatusListFormat.TOKEN_STATUS_LIST, "issuer-1"
        )
        == 1
    )


@pytest.mark.asyncio
async def test_missing_mapped_shard_and_binding_mismatch_fail_closed() -> None:
    manager = StatusListManager()
    with pytest.raises(NativeOperationError, match="mapping is unavailable"):
        await manager.get_status(
            "unknown", StatusListFormat.BITSTRING_STATUS_LIST, "issuer-1"
        )

    manager._credential_index["missing"] = ("missing-shard", 0)
    with pytest.raises(RuntimeError, match="unavailable"):
        await manager.get_status(
            "missing", StatusListFormat.TOKEN_STATUS_LIST, "issuer-1"
        )

    await manager.set_status(
        "mdoc-1", 1, StatusListFormat.TOKEN_STATUS_LIST, "issuer-1"
    )
    with pytest.raises(ValueError, match="does not match"):
        await manager.get_status(
            "mdoc-1", StatusListFormat.BITSTRING_STATUS_LIST, "issuer-1"
        )


def test_status_list_privacy_floor_is_enforced() -> None:
    with pytest.raises(ValueError, match="at least 131072"):
        StatusListManager(shard_size=100_000)


@pytest.mark.asyncio
async def test_unsigned_status_list_credentials_are_not_returned() -> None:
    manager = StatusListManager()
    with pytest.raises(NativeOperationError, match="Unsigned"):
        await manager.get_status_list_credential(
            "shard", "did:example:issuer", object()
        )
