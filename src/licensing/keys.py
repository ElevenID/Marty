"""
Ed25519 Key Management for License Signing

Manages the Ed25519 key pair used to sign license JWTs.
Supports loading from environment variables, PEM files, or HashiCorp Vault.
"""
from __future__ import annotations

import base64
import logging
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

logger = logging.getLogger(__name__)

# Environment variable names
ENV_PRIVATE_KEY_PEM = "LICENSE_SIGNING_PRIVATE_KEY"
ENV_PUBLIC_KEY_PEM = "LICENSE_SIGNING_PUBLIC_KEY"
ENV_PRIVATE_KEY_PATH = "LICENSE_SIGNING_PRIVATE_KEY_PATH"
ENV_PUBLIC_KEY_PATH = "LICENSE_SIGNING_PUBLIC_KEY_PATH"


class KeyLoadError(Exception):
    """Failed to load signing keys."""


class LicenseKeyManager:
    """
    Manages the Ed25519 key pair for license JWT signing.

    Load order (first match wins):
    1. PEM strings from environment variables
    2. PEM files from paths in environment variables
    3. Generate ephemeral dev keys (dev mode only, logs a warning)
    """

    def __init__(
        self,
        private_key: Ed25519PrivateKey | None = None,
        public_key: Ed25519PublicKey | None = None,
    ):
        self._private_key = private_key
        self._public_key = public_key

    @classmethod
    def from_env(cls, allow_dev_keys: bool = False) -> LicenseKeyManager:
        """Load keys from environment variables or files."""
        private_key = None
        public_key = None

        # Try PEM strings from env
        private_pem = os.environ.get(ENV_PRIVATE_KEY_PEM)
        if private_pem:
            private_key = _load_private_key_pem(private_pem.encode())
            public_key = private_key.public_key()
            logger.info("Loaded license signing key from environment variable")
            return cls(private_key=private_key, public_key=public_key)

        # Try PEM file paths from env
        private_path = os.environ.get(ENV_PRIVATE_KEY_PATH)
        if private_path:
            private_key = _load_private_key_file(private_path)
            public_key = private_key.public_key()
            logger.info("Loaded license signing key from file: %s", private_path)
            return cls(private_key=private_key, public_key=public_key)

        # Public key only (validation-only mode for containers)
        public_pem = os.environ.get(ENV_PUBLIC_KEY_PEM)
        if public_pem:
            public_key = _load_public_key_pem(public_pem.encode())
            logger.info("Loaded license public key only (validation mode)")
            return cls(private_key=None, public_key=public_key)

        public_path = os.environ.get(ENV_PUBLIC_KEY_PATH)
        if public_path:
            public_key = _load_public_key_file(public_path)
            logger.info("Loaded license public key from file: %s", public_path)
            return cls(private_key=None, public_key=public_key)

        # Dev mode: generate ephemeral keys
        if allow_dev_keys:
            logger.warning(
                "No license signing keys configured — generating ephemeral dev keys. "
                "Licenses signed with these keys will not be valid in production."
            )
            private_key = Ed25519PrivateKey.generate()
            public_key = private_key.public_key()
            return cls(private_key=private_key, public_key=public_key)

        raise KeyLoadError(
            f"No license signing keys found. Set {ENV_PRIVATE_KEY_PEM} or "
            f"{ENV_PRIVATE_KEY_PATH} environment variable."
        )

    @property
    def can_sign(self) -> bool:
        """Whether this manager has a private key and can sign licenses."""
        return self._private_key is not None

    @property
    def private_key(self) -> Ed25519PrivateKey:
        if self._private_key is None:
            raise KeyLoadError("No private key loaded — cannot sign licenses")
        return self._private_key

    @property
    def public_key(self) -> Ed25519PublicKey:
        if self._public_key is None:
            raise KeyLoadError("No public key loaded")
        return self._public_key

    def public_key_pem(self) -> str:
        """Return the public key as a PEM string (for embedding in containers)."""
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()

    def private_key_pem(self) -> str:
        """Return the private key as a PEM string."""
        return self.private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()


def generate_key_pair() -> tuple[str, str]:
    """
    Generate a new Ed25519 key pair and return (private_pem, public_pem).

    Useful for initial setup / key rotation.
    """
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()

    return private_pem, public_pem


def _load_private_key_pem(pem_data: bytes) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(pem_data, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise KeyLoadError(f"Expected Ed25519 private key, got {type(key).__name__}")
    return key


def _load_public_key_pem(pem_data: bytes) -> Ed25519PublicKey:
    key = serialization.load_pem_public_key(pem_data)
    if not isinstance(key, Ed25519PublicKey):
        raise KeyLoadError(f"Expected Ed25519 public key, got {type(key).__name__}")
    return key


def _load_private_key_file(path: str) -> Ed25519PrivateKey:
    try:
        pem_data = Path(path).read_bytes()
    except (OSError, IOError) as e:
        raise KeyLoadError(f"Cannot read private key file {path}: {e}")
    return _load_private_key_pem(pem_data)


def _load_public_key_file(path: str) -> Ed25519PublicKey:
    try:
        pem_data = Path(path).read_bytes()
    except (OSError, IOError) as e:
        raise KeyLoadError(f"Cannot read public key file {path}: {e}")
    return _load_public_key_pem(pem_data)
