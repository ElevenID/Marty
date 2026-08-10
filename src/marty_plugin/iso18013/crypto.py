"""Retired Python ISO 18013 cryptographic surface.

Session key agreement, key derivation, encryption, counters, and authentication
are owned by the native ``Session`` implementation. Legacy direct-crypto entry
points fail closed so callers cannot accidentally recreate protocol state in
Python.
"""

from __future__ import annotations

from typing import Any

from marty_plugin.native_backends import NativeOperationError


class CryptoError(NativeOperationError):
    """Base error for retired direct ISO cryptographic operations."""


class KeyDerivationError(CryptoError):
    """Direct key derivation is unavailable outside a native session."""


class EncryptionError(CryptoError):
    """Direct encryption is unavailable outside a native session."""


class SignatureError(CryptoError):
    """Direct ISO signature operations are unavailable from this module."""


class _NativeSessionOnly:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise NativeOperationError(
            "Direct Python ISO 18013 cryptography was removed; use "
            "marty_plugin.iso18013_bridge.Session so key material and protocol "
            "state remain in Rust"
        )


KeyDerivation = _NativeSessionOnly
SessionEncryption = _NativeSessionOnly
MessageAuthentication = _NativeSessionOnly
DigitalSignature = _NativeSessionOnly
SelectiveDisclosureCrypto = _NativeSessionOnly
KeyManager = _NativeSessionOnly


def generate_random_bytes(_length: int = 32) -> bytes:
    raise NativeOperationError(
        "Protocol randomness is generated internally by the native ISO session"
    )


def constant_time_compare(_left: bytes, _right: bytes) -> bool:
    raise NativeOperationError(
        "Protocol authentication is performed internally by the native ISO session"
    )


__all__ = [
    "CryptoError",
    "DigitalSignature",
    "EncryptionError",
    "KeyDerivation",
    "KeyDerivationError",
    "KeyManager",
    "MessageAuthentication",
    "SelectiveDisclosureCrypto",
    "SessionEncryption",
    "SignatureError",
    "constant_time_compare",
    "generate_random_bytes",
]
