"""In-memory state for tracking recent UI operations."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime


@dataclass
class OperationRecord:
    """Represents a user-triggered workflow outcome."""

    timestamp: datetime
    category: str
    identifier: str
    status: str
    message: str


class OperationLog:
    """Ring buffer of recent operations to surface in the UI."""

    def __init__(self, max_items: int = 25) -> None:
        self._items: deque[OperationRecord] = deque(maxlen=max_items)

    def add(self, record: OperationRecord) -> None:
        self._items.appendleft(record)

    def items(self) -> Iterable[OperationRecord]:
        return list(self._items)

    def summary(self) -> dict[str, int]:
        summary: dict[str, int] = {}
        for record in self._items:
            summary[record.category] = summary.get(record.category, 0) + 1
        return summary


operation_log = OperationLog()

__all__ = ["OperationLog", "OperationRecord", "operation_log"]
