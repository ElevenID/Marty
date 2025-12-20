"""
Common utilities used across Marty services.
"""

from __future__ import annotations

from datetime import datetime


def datetime_to_string(dt: datetime) -> str:
    """Converts a datetime object to a string."""
    if dt is None:
        return ""
    return dt.isoformat()


def string_to_datetime(dt_str: str) -> datetime | None:
    """Converts a string to a datetime object."""
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str)
    except ValueError:
        return None  # Or raise an error, depending on desired handling
