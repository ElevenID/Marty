"""Shared legacy field formatting for TD2 and visa compatibility adapters."""

import re
from datetime import date


def sanitize_field(text: str, max_length: int, filler: str = "<") -> str:
    if not text:
        return filler * max_length
    text = re.sub(r"[^A-Z0-9<]", "<", text.upper())
    text = re.sub(r"<+", "<", text)
    return text[:max_length] if len(text) > max_length else text.ljust(max_length, filler)


def format_date(date_obj: date) -> str:
    return date_obj.strftime("%y%m%d")
