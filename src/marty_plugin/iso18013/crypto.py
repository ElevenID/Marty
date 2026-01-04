"""
Cryptographic Components for ISO/IEC 18013-5

This module implements the cryptographic operations required for:
- Session establishment and key derivation
- Message encryption and authentication
- Digital signatures and verification
- Selective disclosure cryptography

All cryptographic operations use Rust bindings via marty_rs for
correctness and performance.
"""

from __future__ import annotations

import hmac
import os
from typing import Any, Dict, List, Optional, Tuple

import cbor2

# Use crypto_bridge for Rust-backed cryptographic operations
from marty_plugin.common.crypto_bridge import (
    hkdf_sha256,
    pbkdf2_sha256,
    aes_gcm_encrypt,
    aes_gcm_decrypt,
    p256_generate,
    p256_agree,
    generate_random_bytes as _generate_random_bytes,
    sha256,
    ecdsa_p256_sign,
    ecdsa_p256_verify,
    ecdsa_p384_sign,
    ecdsa_p384_verify,
    rsa_pss_sha256_sign,
    rsa_pss_sha256_verify,
    rsa_pss_sha384_sign,
    rsa_pss_sha384_verify,
    rsa_pss_sha512_sign,
    rsa_pss_sha512_verify,
    save_private_key_pem,
    save_public_key_pem,
    load_private_key_pem,
    load_public_key_pem,
    pkcs8_to_raw_private_key,
    spki_to_raw_public_key,
)


class CryptoError(Exception):
    """Base exception for cryptographic errors"""

    pass


class KeyDerivationError(CryptoError):
    """Key derivation specific errors"""

    pass


class EncryptionError(CryptoError):
    """Encryption/decryption specific errors"""

    pass


class SignatureError(CryptoError):
    """Digital signature specific errors"""

    pass


class KeyDerivation:
    """
    Key derivation functions according to ISO 18013-5 Section 9.1.1

    Implements HKDF-based key derivation for session keys and
    other cryptographic material.
    """

    @staticmethod
    def derive_session_key(
        shared_secret: bytes,
        session_transcript: bytes,
        info_label: str = "SessionKey",
        key_length: int = 32,
    ) -> bytes:
        """
        Derive session key from ECDH shared secret

        Args:
            shared_secret: ECDH shared secret
            session_transcript: Session establishment transcript
            info_label: Key derivation info label
            key_length: Desired key length in bytes

        Returns:
            Derived session key
        """
        try:
            # Create salt from session transcript hash using Rust
            salt = sha256(session_transcript)

            # Create info parameter
            info = f"ISO18013-5 {info_label}".encode()

            # Perform HKDF using Rust crypto
            return hkdf_sha256(shared_secret, salt, info, key_length)

        except Exception as e:
            raise KeyDerivationError(f"Session key derivation failed: {e}")

    @staticmethod
    def derive_encryption_key(
        session_key: bytes, purpose: str = "MessageEncryption", key_length: int = 32
    ) -> bytes:
        """
        Derive encryption key from session key

        Args:
            session_key: Base session key
            purpose: Purpose label for key derivation
            key_length: Desired key length in bytes

        Returns:
            Derived encryption key
        """
        try:
            info = f"ISO18013-5 {purpose}".encode()

            # Perform HKDF using Rust crypto
            return hkdf_sha256(session_key, None, info, key_length)

        except Exception as e:
            raise KeyDerivationError(f"Encryption key derivation failed: {e}")

    @staticmethod
    def derive_mac_key(
        session_key: bytes, purpose: str = "MessageAuthentication", key_length: int = 32
    ) -> bytes:
        """
        Derive MAC key from session key

        Args:
            session_key: Base session key
            purpose: Purpose label for key derivation
            key_length: Desired key length in bytes

        Returns:
            Derived MAC key
        """
        try:
            info = f"ISO18013-5 {purpose}".encode()

            # Perform HKDF using Rust crypto
            return hkdf_sha256(session_key, None, info, key_length)

        except Exception as e:
            raise KeyDerivationError(f"MAC key derivation failed: {e}")


class SessionEncryption:
    """
    Session encryption according to ISO 18013-5 Section 9.1.2

    Implements AES-256-GCM encryption for session messages.
    """

    def __init__(self, session_key: bytes):
        self.encryption_key = KeyDerivation.derive_encryption_key(session_key)
        self.mac_key = KeyDerivation.derive_mac_key(session_key)
        self.send_counter = 0
        self.receive_counter = 0

    def encrypt_message(self, plaintext: bytes, associated_data: bytes | None = None) -> bytes:
        """
        Encrypt a message using AES-256-GCM

        Args:
            plaintext: Message to encrypt
            associated_data: Additional authenticated data

        Returns:
            Encrypted message (nonce + tag + ciphertext)
        """
        try:
            # Generate nonce using counter
            nonce = self.send_counter.to_bytes(12, "big")
            self.send_counter += 1

            # Encrypt using Rust crypto via crypto_bridge
            _, ciphertext, tag = aes_gcm_encrypt(
                self.encryption_key, plaintext, associated_data, nonce
            )

            # Return nonce + tag + ciphertext (ISO 18013-5 format)
            return nonce + tag + ciphertext

        except Exception as e:
            raise EncryptionError(f"Message encryption failed: {e}")

    def decrypt_message(self, encrypted_data: bytes, associated_data: bytes | None = None) -> bytes:
        """
        Decrypt a message using AES-256-GCM

        Args:
            encrypted_data: Encrypted message (nonce + tag + ciphertext)
            associated_data: Additional authenticated data

        Returns:
            Decrypted plaintext
        """
        try:
            # Extract components
            nonce = encrypted_data[:12]
            tag = encrypted_data[12:28]
            ciphertext = encrypted_data[28:]

            # Decrypt using Rust crypto via crypto_bridge
            plaintext = aes_gcm_decrypt(
                self.encryption_key, nonce, ciphertext, associated_data, tag
            )

            self.receive_counter += 1
            return plaintext

        except Exception as e:
            raise EncryptionError(f"Message decryption failed: {e}")


class MessageAuthentication:
    """
    Message authentication according to ISO 18013-5 Section 9.1.3

    Implements HMAC-SHA256 for message authentication.
    """

    def __init__(self, mac_key: bytes):
        self.mac_key = mac_key

    def create_mac(self, message: bytes, context: bytes | None = None) -> bytes:
        """
        Create HMAC for a message

        Args:
            message: Message to authenticate
            context: Optional context data

        Returns:
            HMAC tag
        """
        try:
            import hashlib as _hashlib  # Use Python hmac with hashlib for HMAC
            h = hmac.new(self.mac_key, digestmod=_hashlib.sha256)
            h.update(message)

            if context:
                h.update(context)

            return h.digest()

        except Exception as e:
            raise CryptoError(f"MAC creation failed: {e}")

    def verify_mac(self, message: bytes, mac_tag: bytes, context: bytes | None = None) -> bool:
        """
        Verify HMAC for a message

        Args:
            message: Message to verify
            mac_tag: HMAC tag to verify
            context: Optional context data

        Returns:
            True if MAC is valid
        """
        try:
            expected_mac = self.create_mac(message, context)
            return hmac.compare_digest(expected_mac, mac_tag)

        except Exception as e:
            raise CryptoError(f"MAC verification failed: {e}")


class DigitalSignature:
    """
    Digital signature operations for ISO 18013-5

    Supports both ECDSA and RSA signatures using Rust bindings.
    Keys are expected as raw bytes (for EC) or DER-encoded (for RSA).
    """

    @staticmethod
    def sign_with_ecdsa_p256(
        private_key: bytes,
        message: bytes,
    ) -> bytes:
        """
        Create ECDSA P-256 signature using Rust.

        Args:
            private_key: Raw 32-byte private key scalar
            message: Message to sign

        Returns:
            DER-encoded signature
        """
        try:
            return ecdsa_p256_sign(private_key, message)
        except Exception as e:
            raise SignatureError(f"ECDSA P-256 signing failed: {e}")

    @staticmethod
    def sign_with_ecdsa_p384(
        private_key: bytes,
        message: bytes,
    ) -> bytes:
        """
        Create ECDSA P-384 signature using Rust.

        Args:
            private_key: Raw 48-byte private key scalar
            message: Message to sign

        Returns:
            DER-encoded signature
        """
        try:
            return ecdsa_p384_sign(private_key, message)
        except Exception as e:
            raise SignatureError(f"ECDSA P-384 signing failed: {e}")

    @staticmethod
    def verify_ecdsa_p256(
        public_key: bytes,
        message: bytes,
        signature: bytes,
    ) -> bool:
        """
        Verify ECDSA P-256 signature using Rust.

        Args:
            public_key: Raw 64-byte uncompressed public key (without 0x04 prefix)
            message: Original message
            signature: DER-encoded signature

        Returns:
            True if signature is valid
        """
        try:
            return ecdsa_p256_verify(public_key, message, signature)
        except Exception:
            return False

    @staticmethod
    def verify_ecdsa_p384(
        public_key: bytes,
        message: bytes,
        signature: bytes,
    ) -> bool:
        """
        Verify ECDSA P-384 signature using Rust.

        Args:
            public_key: Raw 96-byte uncompressed public key (without 0x04 prefix)
            message: Original message
            signature: DER-encoded signature

        Returns:
            True if signature is valid
        """
        try:
            return ecdsa_p384_verify(public_key, message, signature)
        except Exception:
            return False

    @staticmethod
    def sign_with_rsa_pss(
        private_key_der: bytes,
        message: bytes,
        hash_algorithm: str = "sha256",
    ) -> bytes:
        """
        Create RSA-PSS signature using Rust.

        Args:
            private_key_der: DER-encoded PKCS#8 private key
            message: Message to sign
            hash_algorithm: Hash algorithm ("sha256", "sha384", "sha512")

        Returns:
            RSA signature
        """
        try:
            if hash_algorithm == "sha256":
                return rsa_pss_sha256_sign(private_key_der, message)
            elif hash_algorithm == "sha384":
                return rsa_pss_sha384_sign(private_key_der, message)
            elif hash_algorithm == "sha512":
                return rsa_pss_sha512_sign(private_key_der, message)
            else:
                raise ValueError(f"Unsupported hash algorithm: {hash_algorithm}")
        except Exception as e:
            raise SignatureError(f"RSA-PSS signing failed: {e}")

    @staticmethod
    def verify_rsa_pss(
        public_key_der: bytes,
        message: bytes,
        signature: bytes,
        hash_algorithm: str = "sha256",
    ) -> bool:
        """
        Verify RSA-PSS signature using Rust.

        Args:
            public_key_der: DER-encoded SubjectPublicKeyInfo
            message: Original message
            signature: RSA signature
            hash_algorithm: Hash algorithm ("sha256", "sha384", "sha512")

        Returns:
            True if signature is valid
        """
        try:
            if hash_algorithm == "sha256":
                return rsa_pss_sha256_verify(public_key_der, message, signature)
            elif hash_algorithm == "sha384":
                return rsa_pss_sha384_verify(public_key_der, message, signature)
            elif hash_algorithm == "sha512":
                return rsa_pss_sha512_verify(public_key_der, message, signature)
            else:
                return False
        except Exception:
            return False

    # Legacy compatibility methods that accept cryptography key objects
    @staticmethod
    def sign_with_ecdsa(
        private_key,  # ec.EllipticCurvePrivateKey
        message: bytes,
        hash_algorithm=None,  # Ignored, using SHA-256
    ) -> bytes:
        """
        Legacy ECDSA signing - converts cryptography key to raw bytes.
        
        Deprecated: Use sign_with_ecdsa_p256() or sign_with_ecdsa_p384() directly.
        """
        from cryptography.hazmat.primitives import serialization
        
        try:
            # Get raw private key bytes
            raw_key = private_key.private_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PrivateFormat.Raw,
                encryption_algorithm=serialization.NoEncryption(),
            )
            
            # Detect curve size
            if len(raw_key) == 32:
                return ecdsa_p256_sign(raw_key, message)
            elif len(raw_key) == 48:
                return ecdsa_p384_sign(raw_key, message)
            else:
                raise SignatureError(f"Unsupported key size: {len(raw_key)}")
        except Exception as e:
            raise SignatureError(f"ECDSA signing failed: {e}")

    @staticmethod
    def verify_ecdsa(
        public_key,  # ec.EllipticCurvePublicKey  
        message: bytes,
        signature: bytes,
        hash_algorithm=None,  # Ignored
    ) -> bool:
        """
        Legacy ECDSA verification - converts cryptography key to raw bytes.
        
        Deprecated: Use verify_ecdsa_p256() or verify_ecdsa_p384() directly.
        """
        from cryptography.hazmat.primitives import serialization
        
        try:
            # Get uncompressed public key bytes
            raw_key = public_key.public_bytes(
                encoding=serialization.Encoding.X962,
                format=serialization.PublicFormat.UncompressedPoint,
            )
            
            # Remove 0x04 prefix for uncompressed point
            if raw_key[0] == 0x04:
                raw_key = raw_key[1:]
            
            # Detect curve size
            if len(raw_key) == 64:
                return ecdsa_p256_verify(raw_key, message, signature)
            elif len(raw_key) == 96:
                return ecdsa_p384_verify(raw_key, message, signature)
            else:
                return False
        except Exception:
            return False

    @staticmethod
    def sign_with_rsa(
        private_key,  # RSAPrivateKey
        message: bytes,
        hash_algorithm=None,  # Ignored, using SHA-256
    ) -> bytes:
        """
        Legacy RSA-PSS signing - converts cryptography key to DER bytes.
        
        Deprecated: Use sign_with_rsa_pss() directly with DER key.
        """
        from cryptography.hazmat.primitives import serialization
        
        try:
            der_key = private_key.private_bytes(
                encoding=serialization.Encoding.DER,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
            return rsa_pss_sha256_sign(der_key, message)
        except Exception as e:
            raise SignatureError(f"RSA-PSS signing failed: {e}")

    @staticmethod
    def verify_rsa(
        public_key,  # RSAPublicKey
        message: bytes,
        signature: bytes,
        hash_algorithm=None,  # Ignored
    ) -> bool:
        """
        Legacy RSA-PSS verification - converts cryptography key to DER bytes.
        
        Deprecated: Use verify_rsa_pss() directly with DER key.
        """
        from cryptography.hazmat.primitives import serialization
        
        try:
            der_key = public_key.public_bytes(
                encoding=serialization.Encoding.DER,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            return rsa_pss_sha256_verify(der_key, message, signature)
        except Exception:
            return False


class SelectiveDisclosureCrypto:
    """
    Cryptographic operations for selective disclosure

    Implements hash-based selective disclosure according to ISO 18013-5.
    Uses Rust bindings for cryptographic operations.
    """

    @staticmethod
    def create_element_digest(
        namespace: str, element_identifier: str, element_value: Any, random_value: bytes
    ) -> tuple[int, bytes]:
        """
        Create digest for a data element

        Args:
            namespace: Element namespace
            element_identifier: Element identifier
            element_value: Element value
            random_value: Random value for this element

        Returns:
            Tuple of (digest_id, digest_hash)
        """
        try:
            # Create digest array [DigestID, Random, ElementIdentifier, ElementValue]
            digest_id = int.from_bytes(
                sha256(
                    namespace.encode("utf-8") + element_identifier.encode("utf-8") + random_value
                )[:4],
                "big",
            )

            digest_data = [digest_id, random_value, element_identifier, element_value]

            # Encode as CBOR and hash using Rust
            cbor_data = cbor2.dumps(digest_data)
            digest_hash = sha256(cbor_data)

            return digest_id, digest_hash

        except Exception as e:
            raise CryptoError(f"Element digest creation failed: {e}")

    @staticmethod
    def create_value_digest_mapping(issuer_signed_items: list[dict[str, Any]]) -> dict[int, bytes]:
        """
        Create mapping of digest IDs to element values

        Args:
            issuer_signed_items: List of issuer signed items

        Returns:
            Dictionary mapping digest ID to digest hash
        """
        try:
            digest_mapping = {}

            for item in issuer_signed_items:
                digest_id = item["digestID"]
                random_value = item["random"]
                element_id = item["elementIdentifier"]
                element_value = item["elementValue"]

                # Create digest for verification using Rust
                digest_data = [digest_id, random_value, element_id, element_value]
                cbor_data = cbor2.dumps(digest_data)
                digest_hash = sha256(cbor_data)

                digest_mapping[digest_id] = digest_hash

            return digest_mapping

        except Exception as e:
            raise CryptoError(f"Value digest mapping creation failed: {e}")


class KeyManager:
    """
    Key management utilities for ISO 18013-5

    Handles key generation, storage, and lifecycle management.
    """

    @staticmethod
    def generate_ephemeral_keypair() -> (
        tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey]
    ):
        """
        Generate ephemeral ECDSA key pair for session establishment

        Returns:
            Tuple of (private_key, public_key)
        """
        try:
            private_key = ec.generate_private_key(ec.SECP256R1())
            public_key = private_key.public_key()
            return private_key, public_key

        except Exception as e:
            raise CryptoError(f"Ephemeral key generation failed: {e}")

    @staticmethod
    def public_key_to_cose(public_key: ec.EllipticCurvePublicKey) -> dict[int, Any]:
        """
        Convert EC public key to COSE key format

        Args:
            public_key: EC public key

        Returns:
            COSE key dictionary
        """
        try:
            numbers = public_key.public_numbers()

            return {
                1: 2,  # kty: EC2
                3: -7,  # alg: ES256
                -1: 1,  # crv: P-256
                -2: numbers.x.to_bytes(32, "big"),  # x coordinate
                -3: numbers.y.to_bytes(32, "big"),  # y coordinate
            }

        except Exception as e:
            raise CryptoError(f"Public key COSE conversion failed: {e}")

    @staticmethod
    def cose_to_public_key(cose_key: dict[int, Any]) -> ec.EllipticCurvePublicKey:
        """
        Convert COSE key to EC public key

        Args:
            cose_key: COSE key dictionary

        Returns:
            EC public key
        """
        try:
            x = int.from_bytes(cose_key[-2], "big")
            y = int.from_bytes(cose_key[-3], "big")

            numbers = ec.EllipticCurvePublicNumbers(x, y, ec.SECP256R1())
            return numbers.public_key()

        except Exception as e:
            raise CryptoError(f"COSE key conversion failed: {e}")

    @staticmethod
    def derive_device_binding_key(
        device_private_key: ec.EllipticCurvePrivateKey, document_id: str
    ) -> bytes:
        """
        Derive device binding key for document

        Args:
            device_private_key: Device's long-term private key
            document_id: Document identifier

        Returns:
            Device binding key
        """
        try:
            # Create key derivation input
            key_info = f"ISO18013-5 DeviceBinding {document_id}".encode()

            # Get private key scalar
            from cryptography.hazmat.primitives import serialization
            private_bytes = device_private_key.private_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PrivateFormat.Raw,
                encryption_algorithm=serialization.NoEncryption(),
            )

            # Derive binding key using Rust HKDF
            return hkdf_sha256(private_bytes, b"", key_info, 32)

        except Exception as e:
            raise CryptoError(f"Device binding key derivation failed: {e}")


def generate_random_bytes(length: int) -> bytes:
    """
    Generate cryptographically secure random bytes using Rust.

    Args:
        length: Number of bytes to generate

    Returns:
        Random bytes
    """
    return _generate_random_bytes(length)


def constant_time_compare(a: bytes, b: bytes) -> bool:
    """
    Constant-time comparison of byte strings

    Args:
        a: First byte string
        b: Second byte string

    Returns:
        True if strings are equal
    """
    return hmac.compare_digest(a, b)
