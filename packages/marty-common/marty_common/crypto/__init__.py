"""Native-backed cryptographic entry points for Marty common services."""

from __future__ import annotations

import base64
import hmac
import secrets
from typing import Literal

from marty_common import crypto_bridge
from marty_common.native_backends import NativeOperationError

from .data_group_hasher import DataGroupHashComputer, verify_passport_data_groups
from .sod_parser import SODProcessor, extract_sod_hashes, parse_sod
from .sod_signer import build_lds_security_object, create_sod, load_sod, verify_sod_signature

HashAlgorithm = Literal["SHA-256", "SHA-384", "SHA-512"]
SigningAlgorithm = Literal["RS256", "RS384", "RS512", "ES256", "ES384"]
KeyAlgorithm = Literal["RSA", "EC"]

_SIGNATURE_ALGORITHMS = {
    "RS256": "rsa-pkcs1-sha256",
    "RS384": "rsa-pkcs1-sha384",
    "RS512": "rsa-pkcs1-sha512",
    "RSA-SHA256": "rsa-pkcs1-sha256",
    "RSA-SHA384": "rsa-pkcs1-sha384",
    "RSA-SHA512": "rsa-pkcs1-sha512",
    "ES256": "ecdsa-p256-sha256",
    "ES384": "ecdsa-p384-sha384",
    "ECDSA-SHA256": "ecdsa-p256-sha256",
    "ECDSA-SHA384": "ecdsa-p384-sha384",
}
_PBKDF2_ITERATIONS = 600_000


def encode_base64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def decode_base64(data: str) -> bytes:
    return base64.b64decode(data, validate=True)


def hash_data(data: bytes, algorithm: HashAlgorithm = "SHA-256") -> bytes:
    return crypto_bridge.hash_data(algorithm.lower().replace("-", ""), data)


def generate_hash(data: str | bytes, algorithm: HashAlgorithm = "SHA-256") -> str:
    payload = data.encode("utf-8") if isinstance(data, str) else data
    return hash_data(payload, algorithm).hex()


def generate_key_pair(algorithm: KeyAlgorithm = "RSA", key_size: int = 2048) -> tuple[bytes, bytes]:
    if algorithm == "RSA":
        if key_size < 2048:
            raise ValueError("RSA key size must be at least 2048 bits")
        private_der, public_der = crypto_bridge.rsa_generate(key_size)
    elif algorithm == "EC":
        if key_size == 256:
            private_raw, public_raw = crypto_bridge.ecdsa_p256_generate()
            key_type = "P256"
        elif key_size == 384:
            private_raw, public_raw = crypto_bridge.ecdsa_p384_generate()
            key_type = "P384"
        else:
            raise ValueError("EC key size must be 256 or 384 bits")
        private_der = crypto_bridge.raw_private_key_to_pkcs8(private_raw, key_type)
        public_der = crypto_bridge.raw_public_key_to_spki(public_raw, key_type)
    else:
        raise ValueError(f"Unsupported key algorithm: {algorithm}")
    return (
        crypto_bridge.save_private_key_pem(private_der).encode("ascii"),
        crypto_bridge.save_public_key_pem(public_der).encode("ascii"),
    )


def _private_der(private_key: bytes) -> bytes:
    if private_key.lstrip().startswith(b"-----BEGIN"):
        return crypto_bridge.load_private_key_pem(private_key.decode("ascii"))
    return crypto_bridge.load_private_key_der(private_key)


def _public_der(public_key: bytes) -> bytes:
    if public_key.lstrip().startswith(b"-----BEGIN"):
        return crypto_bridge.load_public_key_pem(public_key.decode("ascii"))
    return crypto_bridge.load_public_key_der(public_key)


def sign_data(
    data: bytes,
    private_key: bytes,
    algorithm: SigningAlgorithm = "RS256",
) -> bytes:
    canonical = _SIGNATURE_ALGORITHMS.get(algorithm.upper())
    if canonical is None:
        raise ValueError(f"Unsupported signing algorithm: {algorithm}")
    private_der = _private_der(private_key)
    functions = {
        "rsa-pkcs1-sha256": crypto_bridge.rsa_pkcs1_sha256_sign,
        "rsa-pkcs1-sha384": crypto_bridge.rsa_pkcs1_sha384_sign,
        "rsa-pkcs1-sha512": crypto_bridge.rsa_pkcs1_sha512_sign,
        "ecdsa-p256-sha256": lambda key, value: crypto_bridge.ecdsa_p256_sign(
            crypto_bridge.pkcs8_to_raw_private_key(key)[0], value
        ),
        "ecdsa-p384-sha384": lambda key, value: crypto_bridge.ecdsa_p384_sign(
            crypto_bridge.pkcs8_to_raw_private_key(key)[0], value
        ),
    }
    return functions[canonical](private_der, data)


def verify_signature(
    data: bytes,
    signature: bytes,
    public_key: bytes,
    algorithm: str = "RS256",
) -> bool:
    canonical = _SIGNATURE_ALGORITHMS.get(algorithm.upper())
    if canonical is None:
        raise ValueError(f"Unsupported signature algorithm: {algorithm}")
    try:
        return bool(
            crypto_bridge.verify_signature(
                canonical,
                _public_der(public_key),
                data,
                signature,
            )
        )
    except (TypeError, ValueError, RuntimeError) as exc:
        raise NativeOperationError(f"Native signature verification failed: {exc}") from exc


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = crypto_bridge.pbkdf2_sha256(password.encode("utf-8"), salt, _PBKDF2_ITERATIONS, 32)
    return "$".join(
        (
            "pbkdf2-sha256",
            str(_PBKDF2_ITERATIONS),
            base64.urlsafe_b64encode(salt).decode("ascii").rstrip("="),
            base64.urlsafe_b64encode(digest).decode("ascii").rstrip("="),
        )
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, iterations_text, salt_text, digest_text = encoded.split("$", 3)
        if scheme != "pbkdf2-sha256":
            return False
        iterations = int(iterations_text)
        if iterations < _PBKDF2_ITERATIONS:
            return False
        salt = base64.urlsafe_b64decode(salt_text + "=" * (-len(salt_text) % 4))
        expected = base64.urlsafe_b64decode(digest_text + "=" * (-len(digest_text) % 4))
    except (ValueError, TypeError):
        return False
    actual = crypto_bridge.pbkdf2_sha256(password.encode("utf-8"), salt, iterations, len(expected))
    return hmac.compare_digest(actual, expected)


__all__ = [
    "DataGroupHashComputer",
    "SODProcessor",
    "build_lds_security_object",
    "create_sod",
    "decode_base64",
    "encode_base64",
    "extract_sod_hashes",
    "generate_hash",
    "generate_key_pair",
    "hash_data",
    "hash_password",
    "load_sod",
    "parse_sod",
    "sign_data",
    "verify_passport_data_groups",
    "verify_password",
    "verify_signature",
    "verify_sod_signature",
]
