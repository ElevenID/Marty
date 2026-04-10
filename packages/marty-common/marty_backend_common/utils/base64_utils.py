"""Base64url encoding utilities (RFC 4648 §5)."""

from __future__ import annotations

import base64


def b64url_encode(data: bytes) -> str:
    """Return base64url-encoded string without padding."""
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def b64url_decode(data: str) -> bytes:
    """Decode a base64url string, adding padding as needed."""
    padding = 4 - (len(data) % 4)
    if padding != 4:
        data += "=" * padding
    return base64.urlsafe_b64decode(data)


def int_to_b64url(value: int) -> str:
    """Encode an integer as base64url (for JWK components)."""
    byte_length = (value.bit_length() + 7) // 8 or 1
    value_bytes = value.to_bytes(byte_length, byteorder="big")
    return b64url_encode(value_bytes)
