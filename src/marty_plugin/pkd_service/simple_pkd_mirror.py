"""Retired demonstration PKD mirror.

Production synchronization is implemented by the PKD application services,
which validate master lists, certificates, and revocation material through the
native Marty verification backend before persistence.
"""

from __future__ import annotations

from typing import NoReturn

from marty_common.native_backends import NativeOperationError


class SimplePKDMirrorService:
    """Reject the former synthetic-success mirror implementation."""

    def __init__(self, pkd_url: str | None = None, sync_interval: int = 3600) -> None:
        del pkd_url, sync_interval
        raise NativeOperationError(
            "The demonstration PKD mirror is disabled; configure the native-backed "
            "PKD synchronization application service"
        )

    def start_sync_scheduler(self) -> NoReturn:
        raise NativeOperationError("The demonstration PKD mirror is disabled")

    def start_sync_thread(self) -> NoReturn:
        raise NativeOperationError("The demonstration PKD mirror is disabled")

    def sync(self) -> NoReturn:
        raise NativeOperationError("The demonstration PKD mirror is disabled")

    def get_last_sync_time(self) -> None:
        return None


def main() -> NoReturn:
    raise NativeOperationError("The demonstration PKD mirror is disabled")


__all__ = ["SimplePKDMirrorService"]
