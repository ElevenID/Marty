"""Compatibility models for native ISO/IEC 9796-2 verification.

RSA recovery, signature validation, hashing, and simulator signing are owned by
the canonical ``marty_verification`` Rust extension. This module preserves the
established Python API for passport-service callers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from marty_common.native_backends import NativeBackendError, load_native_backend

if TYPE_CHECKING:
    from cryptography.hazmat.primitives.asymmetric import rsa

logger = logging.getLogger(__name__)


def _native():
    return load_native_backend(
        "marty_verification",
        (
            "hash_data",
            "iso9796_recover",
            "iso9796_scheme1_sign",
            "iso9796_verify",
        ),
    )


def _public_key_der(public_key: rsa.RSAPublicKey) -> bytes:
    from cryptography.hazmat.primitives import serialization

    return public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def _private_key_der(private_key: rsa.RSAPrivateKey) -> bytes:
    from cryptography.hazmat.primitives import serialization

    return private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


class ISO9796Scheme(Enum):
    """ISO 9796-2 signature schemes."""

    SCHEME_1 = 1
    SCHEME_2 = 2
    SCHEME_3 = 3


class _NativeHash:
    def __init__(self, algorithm: str, data: bytes = b"") -> None:
        self._algorithm = algorithm
        self._data = bytes(data)

    def update(self, data: bytes) -> None:
        self._data += bytes(data)

    def digest(self) -> bytes:
        return bytes(_native().hash_data(self._algorithm, self._data))

    def hexdigest(self) -> str:
        return self.digest().hex()


class HashFunction(Enum):
    """Supported hash functions with a native-backed hashlib-compatible factory."""

    SHA1 = (0x33, "sha1", 20)
    SHA224 = (0x38, "sha224", 28)
    SHA256 = (0x34, "sha256", 32)
    SHA384 = (0x36, "sha384", 48)
    SHA512 = (0x35, "sha512", 64)

    def __init__(self, identifier: int, native_name: str, digest_length: int) -> None:
        self.identifier = identifier
        self.native_name = native_name
        self.digest_length = digest_length

    def hash_func(self, data: bytes = b"") -> _NativeHash:
        return _NativeHash(self.native_name, data)


@dataclass
class ISO9796SignatureData:
    """Parsed ISO 9796-2 signature data."""

    scheme: ISO9796Scheme
    hash_function: HashFunction
    recovered_message: bytes
    message_hash: bytes
    is_valid: bool = False
    trailer: bytes | None = None


class ISO9796Verifier:
    """Compatibility adapter over the native ISO 9796 implementation."""

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)
        self.hash_functions = {hf.identifier: hf for hf in HashFunction}

    def verify_signature(
        self,
        signature: bytes,
        message: bytes,
        public_key: rsa.RSAPublicKey,
        scheme: ISO9796Scheme = ISO9796Scheme.SCHEME_1,
    ) -> ISO9796SignatureData:
        native = _native()
        hash_function = HashFunction.SHA256
        try:
            is_valid = bool(
                native.iso9796_verify(
                    _public_key_der(public_key),
                    message,
                    signature,
                    scheme.value,
                    hash_function.native_name,
                )
            )
            recovered = (
                bytes(
                    native.iso9796_recover(
                        _public_key_der(public_key),
                        signature,
                        scheme.value,
                        None if scheme is ISO9796Scheme.SCHEME_1 else hash_function.native_name,
                    )
                )
                if is_valid
                else b""
            )
        except NativeBackendError:
            raise
        except (RuntimeError, TypeError, ValueError):
            self.logger.warning("ISO 9796 signature rejected", exc_info=True)
            return self._create_invalid_result(scheme)

        return ISO9796SignatureData(
            scheme=scheme,
            hash_function=hash_function,
            recovered_message=recovered,
            message_hash=bytes(native.hash_data(hash_function.native_name, message)),
            is_valid=is_valid,
            trailer=b"\xbc" if is_valid else None,
        )

    def _verify_scheme_1(
        self, signature: bytes, message: bytes, public_key: rsa.RSAPublicKey
    ) -> ISO9796SignatureData:
        return self.verify_signature(signature, message, public_key, ISO9796Scheme.SCHEME_1)

    def _verify_scheme_2(
        self, signature: bytes, message: bytes, public_key: rsa.RSAPublicKey
    ) -> ISO9796SignatureData:
        return self.verify_signature(signature, message, public_key, ISO9796Scheme.SCHEME_2)

    def _rsa_verify_with_recovery(
        self, signature: bytes, public_key: rsa.RSAPublicKey
    ) -> bytes | None:
        """Recover a canonical Scheme 1 message through Rust."""

        try:
            return bytes(
                _native().iso9796_recover(
                    _public_key_der(public_key), signature, ISO9796Scheme.SCHEME_1.value, None
                )
            )
        except NativeBackendError:
            raise
        except (RuntimeError, TypeError, ValueError):
            return None

    def _parse_scheme_1_structure(
        self, data: bytes
    ) -> tuple[int, bytes, bytes, HashFunction, bytes] | None:
        """Describe a message already recovered and validated by Rust."""

        if not data:
            return None
        hash_function = HashFunction.SHA256
        message_hash = bytes(_native().hash_data(hash_function.native_name, data))
        return 0x6A, bytes(data), message_hash, hash_function, b"\xbc"

    def _create_invalid_result(self, scheme: ISO9796Scheme) -> ISO9796SignatureData:
        return ISO9796SignatureData(
            scheme=scheme,
            hash_function=HashFunction.SHA256,
            recovered_message=b"",
            message_hash=b"",
            is_valid=False,
        )

    def create_test_signature(
        self,
        message: bytes,
        private_key: rsa.RSAPrivateKey,
        hash_function: HashFunction = HashFunction.SHA256,
    ) -> bytes:
        """Create a native Scheme 1 signature for tests and chip simulators."""

        del hash_function  # Scheme 1 has full recovery and no embedded digest.
        return bytes(_native().iso9796_scheme1_sign(_private_key_der(private_key), message))


class PassportActiveAuthenticationVerifier:
    """High-level compatibility verifier for passport Active Authentication."""

    def __init__(self) -> None:
        self.iso9796_verifier = ISO9796Verifier()
        self.logger = logging.getLogger(__name__)

    def verify_active_authentication_response(
        self, challenge: bytes, signature: bytes, public_key: rsa.RSAPublicKey
    ) -> bool:
        result = self.iso9796_verifier.verify_signature(
            signature, challenge, public_key, ISO9796Scheme.SCHEME_1
        )
        return result.is_valid and result.recovered_message == challenge

    def analyze_signature_structure(
        self, signature: bytes, public_key: rsa.RSAPublicKey
    ) -> dict[str, Any]:
        analysis: dict[str, Any] = {
            "signature_length": len(signature),
            "key_size": public_key.key_size,
            "scheme_detected": None,
            "hash_function": None,
            "structure_valid": False,
            "recovery_successful": False,
        }
        recovered = self.iso9796_verifier._rsa_verify_with_recovery(signature, public_key)
        if recovered is not None:
            analysis.update(
                {
                    "scheme_detected": "Scheme 1",
                    "hash_function": HashFunction.SHA256.name,
                    "structure_valid": True,
                    "recovery_successful": True,
                    "recovered_message_length": len(recovered),
                    "header": "0x6A",
                    "trailer": "bc",
                }
            )
        return analysis
