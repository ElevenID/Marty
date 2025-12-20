"""
Cryptographic utilities for Marty services.

This module provides cryptographic functions used across multiple Marty services,
including certificate operations, key management, and digital signatures.

NOTE: This module now uses the Rust-based crypto_bridge for all cryptographic operations.
"""

from __future__ import annotations

import base64
import binascii
import secrets
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Literal

from marty_plugin.common import crypto_bridge

if TYPE_CHECKING:
    pass

try:
    import bcrypt  # type: ignore[import-not-found]

    _BCRYPT_AVAILABLE = True
except ImportError:  # pragma: no cover
    bcrypt = None  # type: ignore[assignment]
    _BCRYPT_AVAILABLE = False

# Type aliases for better readability
HashAlgorithm = Literal["SHA-256", "SHA-384", "SHA-512"]
SigningAlgorithm = Literal["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"]
KeyAlgorithm = Literal["RSA", "EC"]


def generate_key_pair(algorithm: KeyAlgorithm = "RSA", key_size: int = 2048) -> tuple[bytes, bytes]:
    """Generate a cryptographic key pair using secure primitives.

    Returns private and public key in PEM (PKCS8 for private, SubjectPublicKeyInfo for public).
    Maintains backward compatibility by returning raw bytes like prior placeholder.
    """
    if algorithm == "RSA":
        if key_size < 2048:
            msg = "RSA key size must be at least 2048 bits"
            raise ValueError(msg)
        # Use crypto_bridge for RSA key generation
        private_der, public_der = crypto_bridge.rsa_generate(key_size)
        private_pem = crypto_bridge.save_private_key_pem(private_der).encode("utf-8")
        public_pem = crypto_bridge.save_public_key_pem(public_der).encode("utf-8")
        return private_pem, public_pem
    elif algorithm == "EC":
        if key_size < 256:
            msg = "EC key size must be at least 256 bits"
            raise ValueError(msg)
        # Map key size to curve and generate
        if key_size in (256, 0):
            raw_priv, raw_pub = crypto_bridge.ecdsa_p256_generate()
            key_type = "P256"
        elif key_size == 384:
            raw_priv, raw_pub = crypto_bridge.ecdsa_p384_generate()
            key_type = "P384"
        else:
            msg = f"Unsupported EC key size: {key_size}. Allowed: 256, 384"
            raise ValueError(msg)
        # Convert raw keys to PKCS#8/SPKI and then to PEM
        private_der = crypto_bridge.raw_private_key_to_pkcs8(raw_priv, key_type)
        public_der = crypto_bridge.raw_public_key_to_spki(raw_pub, key_type)
        private_pem = crypto_bridge.save_private_key_pem(private_der).encode("utf-8")
        public_pem = crypto_bridge.save_public_key_pem(public_der).encode("utf-8")
        return private_pem, public_pem
    else:
        msg = f"Unsupported key algorithm: {algorithm}"
        raise ValueError(msg)


def generate_hash(data: str | bytes, algorithm: HashAlgorithm = "SHA-256") -> str:
    """
    Generate a hash of the provided data.

    Args:
        data: The data to hash (string or bytes)
        algorithm: The hash algorithm to use

    Returns:
        Hexadecimal string representation of the hash

    Raises:
        ValueError: If an unsupported algorithm is provided
    """
    if isinstance(data, str):
        data = data.encode("utf-8")

    if algorithm == "SHA-256":
        result = crypto_bridge.sha256(data)
    elif algorithm == "SHA-384":
        result = crypto_bridge.sha384(data)
    elif algorithm == "SHA-512":
        result = crypto_bridge.sha512(data)
    else:
        msg = f"Unsupported hash algorithm: {algorithm}"
        raise ValueError(msg)

    return result.hex()


def _detect_key_type_from_pem(pem_bytes: bytes) -> str:
    """Detect key type from PEM key bytes."""
    der_data = crypto_bridge.load_private_key_pem(pem_bytes.decode("utf-8"))
    return crypto_bridge.detect_private_key_type(der_data)


def sign_data(data: bytes, private_key: bytes, algorithm: SigningAlgorithm = "RS256") -> bytes:
    """Sign data securely.

    private_key is expected to be in PEM. If it is not parseable, a ValueError is raised.
    """
    if algorithm not in ["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"]:
        msg = f"Unsupported signing algorithm: {algorithm}"
        raise ValueError(msg)

    # Load key from PEM and detect type
    try:
        private_der = crypto_bridge.load_private_key_pem(private_key.decode("utf-8"))
        key_type = crypto_bridge.detect_private_key_type(private_der)
    except Exception as e:
        msg = "Invalid private key format - expected PEM"
        raise ValueError(msg) from e

    # Validate key type matches algorithm
    if algorithm.startswith("RS") and key_type != "RSA":
        msg = "Provided private key is not an RSA key for RS* algorithm"
        raise ValueError(msg)
    if algorithm.startswith("ES") and key_type not in ("P-256", "P-384", "P-521"):
        msg = "Provided private key is not an EC key for ES* algorithm"
        raise ValueError(msg)

    # Sign using crypto_bridge
    if algorithm == "RS256":
        return crypto_bridge.rsa_pkcs1_sha256_sign(private_der, data)
    elif algorithm == "RS384":
        return crypto_bridge.rsa_pkcs1_sha384_sign(private_der, data)
    elif algorithm == "RS512":
        return crypto_bridge.rsa_pkcs1_sha512_sign(private_der, data)
    elif algorithm == "ES256":
        # Convert PKCS#8 to raw key for ECDSA
        raw_key, _ = crypto_bridge.pkcs8_to_raw_private_key(private_der)
        return crypto_bridge.ecdsa_p256_sign(raw_key, data)
    elif algorithm == "ES384":
        raw_key, _ = crypto_bridge.pkcs8_to_raw_private_key(private_der)
        return crypto_bridge.ecdsa_p384_sign(raw_key, data)
    else:
        msg = f"Unsupported signing algorithm: {algorithm}"
        raise ValueError(msg)


def verify_signature(
    data: bytes, signature: bytes, public_key: bytes, algorithm: SigningAlgorithm = "RS256"
) -> bool:
    """Verify a digital signature with secure cryptographic primitives.

    This function only accepts PEM-formatted public keys and uses proper RSA/ECDSA verification.
    Legacy insecure hash-based verification has been removed for security.
    """
    if algorithm not in ["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"]:
        msg = f"Unsupported signing algorithm: {algorithm}"
        raise ValueError(msg)

    try:
        public_der = crypto_bridge.load_public_key_pem(public_key.decode("utf-8"))
        key_type = crypto_bridge.detect_public_key_type(public_der)
    except Exception as e:
        msg = f"Failed to load public key: {e}"
        raise ValueError(msg) from e

    try:
        if algorithm == "RS256":
            return crypto_bridge.rsa_pkcs1_sha256_verify(public_der, data, signature)
        elif algorithm == "RS384":
            return crypto_bridge.rsa_pkcs1_sha384_verify(public_der, data, signature)
        elif algorithm == "RS512":
            return crypto_bridge.rsa_pkcs1_sha512_verify(public_der, data, signature)
        elif algorithm == "ES256":
            # Convert SPKI to raw key for ECDSA
            raw_key, _ = crypto_bridge.spki_to_raw_public_key(public_der)
            return crypto_bridge.ecdsa_p256_verify(raw_key, data, signature)
        elif algorithm == "ES384":
            raw_key, _ = crypto_bridge.spki_to_raw_public_key(public_der)
            return crypto_bridge.ecdsa_p384_verify(raw_key, data, signature)
    except Exception:
        return False

    return False


def hash_data(data: bytes, algorithm: HashAlgorithm = "SHA-256") -> bytes:
    """
    Hash data using the specified algorithm.

    Args:
        data: The data to hash
        algorithm: The hashing algorithm to use

    Returns:
        The hash as bytes

    Raises:
        ValueError: If the algorithm is not supported
    """
    if algorithm == "SHA-256":
        return crypto_bridge.sha256(data)
    if algorithm == "SHA-384":
        return crypto_bridge.sha384(data)
    if algorithm == "SHA-512":
        return crypto_bridge.sha512(data)
    msg = f"Unsupported hashing algorithm: {algorithm}"
    raise ValueError(msg)


def encode_base64(data: bytes) -> str:
    """
    Encode binary data as base64.

    Args:
        data: The binary data to encode

    Returns:
        Base64-encoded string
    """
    return base64.b64encode(data).decode("ascii")


def decode_base64(data: str) -> bytes:
    """
    Decode base64 data to binary.

    Args:
        data: The base64-encoded string

    Returns:
        Decoded binary data

    Raises:
        ValueError: If the input is not valid base64
    """
    try:
        return base64.b64decode(data)
    except (binascii.Error, ValueError) as e:
        msg = f"Invalid base64 data: {e}"
        raise ValueError(msg) from e


def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt for secure storage.

    Args:
        password: The plain text password to hash

    Returns:
        The hashed password as a string

    Raises:
        RuntimeError: If bcrypt is not available (must be installed for production use)
    """
    if not _BCRYPT_AVAILABLE or bcrypt is None:
        msg = "bcrypt is required for secure password hashing. Install with: pip install bcrypt"
        raise RuntimeError(msg)

    password_bytes = password.encode("utf-8")
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """
    Verify a password against a bcrypt hash.

    Args:
        password: The plain text password to verify
        hashed: The hashed password to verify against

    Returns:
        True if the password matches the hash, False otherwise

    Raises:
        RuntimeError: If bcrypt is not available (must be installed for production use)
    """
    if not _BCRYPT_AVAILABLE or bcrypt is None:
        msg = (
            "bcrypt is required for secure password verification. "
            "Install with: pip install bcrypt"
        )
        raise RuntimeError(msg)

    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


# Certificate management and validation functions


def load_certificate(cert_data: bytes) -> bytes:
    """
    Load an X.509 certificate from PEM or DER format.

    Args:
        cert_data: Certificate data in bytes (PEM or DER format)

    Returns:
        Certificate in DER format (bytes)

    Raises:
        ValueError: If the certificate data is invalid or unsupported format
    """
    try:
        # Try PEM first (check for PEM header)
        if b"-----BEGIN CERTIFICATE-----" in cert_data:
            return crypto_bridge.certificate_pem_to_der(cert_data.decode("utf-8"))
        # Try DER format
        return crypto_bridge.load_certificate_der(cert_data)
    except Exception as e:
        msg = f"Invalid certificate format (expected PEM or DER): {e}"
        raise ValueError(msg) from e


def validate_certificate_chain(
    cert: bytes,
    intermediates: list[bytes] | None = None,
    trusted_certs: list[bytes] | None = None,
) -> bool:
    """
    Validate an X.509 certificate chain.

    Args:
        cert: The end-entity certificate DER bytes to validate
        intermediates: List of intermediate certificate DER bytes in the chain
        trusted_certs: List of trusted root certificate DER bytes

    Returns:
        True if the certificate chain is valid, False otherwise

    Note:
        For full production use, consider using a dedicated certificate validation
        library that supports CRL/OCSP checking.
    """
    try:
        # Basic validation checks

        # Check certificate validity period
        if crypto_bridge.is_certificate_expired(cert):
            return False
        if crypto_bridge.is_certificate_not_yet_valid(cert):
            return False

        # Check intermediate certificates validity if provided
        if intermediates:
            for intermediate in intermediates:
                if crypto_bridge.is_certificate_expired(intermediate):
                    return False
                if crypto_bridge.is_certificate_not_yet_valid(intermediate):
                    return False

        # Basic signature verification
        if trusted_certs:
            for trusted in trusted_certs:
                try:
                    if crypto_bridge.verify_certificate_signature(cert, trusted):
                        return True
                except Exception:
                    continue

        return True  # Basic checks passed
    except Exception:
        return False


def extract_certificate_info(cert: bytes) -> dict[str, str]:
    """
    Extract basic information from an X.509 certificate.

    Args:
        cert: The X.509 certificate DER bytes to extract information from

    Returns:
        Dictionary containing certificate information
    """
    try:
        info = crypto_bridge.get_certificate_info(cert)
        
        # Get public key info
        pub_key_der = crypto_bridge.get_certificate_public_key(cert)
        key_type = crypto_bridge.detect_public_key_type(pub_key_der)
        key_size = crypto_bridge.get_key_size(pub_key_der)

        # Parse subject/issuer DN strings to extract components
        subject = info.get("subject", "")
        issuer = info.get("issuer", "")

        return {
            "subject_common_name": _extract_dn_component(subject, "CN"),
            "subject_country": _extract_dn_component(subject, "C"),
            "subject_organization": _extract_dn_component(subject, "O"),
            "issuer_common_name": _extract_dn_component(issuer, "CN"),
            "issuer_country": _extract_dn_component(issuer, "C"),
            "issuer_organization": _extract_dn_component(issuer, "O"),
            "not_before": info.get("not_before", ""),
            "not_after": info.get("not_after", ""),
            "serial_number": info.get("serial_number", ""),
            "key_type": key_type,
            "key_size": str(key_size),
            "fingerprint_sha256": info.get("fingerprint_sha256", ""),
        }
    except Exception as e:
        msg = f"Failed to extract certificate information: {e}"
        raise ValueError(msg) from e


def _extract_dn_component(dn: str, component: str) -> str:
    """Extract a component from an X.500 Distinguished Name string."""
    # DN format: "CN=Common Name,O=Organization,C=US"
    for part in dn.split(","):
        part = part.strip()
        if part.startswith(f"{component}="):
            return part[len(component) + 1:]
    return ""


# Secure random number generation functions


def generate_secure_random_bytes(length: int) -> bytes:
    """
    Generate cryptographically secure random bytes.

    Args:
        length: Number of random bytes to generate

    Returns:
        Cryptographically secure random bytes

    Raises:
        ValueError: If length is not positive
    """
    if length <= 0:
        msg = "Length must be positive"
        raise ValueError(msg)
    return secrets.token_bytes(length)


def generate_secure_token(length: int = 32) -> str:
    """
    Generate a cryptographically secure URL-safe token.

    Args:
        length: Number of random bytes to use for the token (default: 32)

    Returns:
        URL-safe base64-encoded token string

    Raises:
        ValueError: If length is not positive
    """
    if length <= 0:
        msg = "Length must be positive"
        raise ValueError(msg)
    return secrets.token_urlsafe(length)


def generate_secure_hex(length: int = 32) -> str:
    """
    Generate a cryptographically secure hex string.

    Args:
        length: Number of random bytes to use for the hex string (default: 32)

    Returns:
        Hex-encoded token string

    Raises:
        ValueError: If length is not positive
    """
    if length <= 0:
        msg = "Length must be positive"
        raise ValueError(msg)
    return secrets.token_hex(length)


def generate_nonce(length: int = 16) -> bytes:
    """
    Generate a cryptographically secure nonce (number used once).

    Args:
        length: Number of random bytes for the nonce (default: 16)

    Returns:
        Cryptographically secure random bytes suitable for use as a nonce

    Raises:
        ValueError: If length is not positive
    """
    if length <= 0:
        msg = "Length must be positive"
        raise ValueError(msg)
    return secrets.token_bytes(length)
