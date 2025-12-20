"""
Cryptographic Components for ISO/IEC 18013-5

This module implements the cryptographic operations required for:
- Session establishment and key derivation
- Message encryption and authentication
- Digital signatures and verification
- Selective disclosure cryptography
"""

from __future__ import annotations

import hashlib
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
    generate_random_bytes,
)

# For signature operations, we still need cryptography types until
# full migration to Rust-based signing is complete.
# TODO: Migrate to Rust-based ECDSA/RSA signing
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey


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
            # Create salt from session transcript hash
            salt = hashlib.sha256(session_transcript).digest()

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
            h = hmac.new(self.mac_key, digestmod=hashlib.sha256)
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

    Supports both ECDSA and RSA signatures for different use cases.
    """

    @staticmethod
    def sign_with_ecdsa(
        private_key: ec.EllipticCurvePrivateKey,
        message: bytes,
        hash_algorithm: hashes.HashAlgorithm = hashes.SHA256(),
    ) -> bytes:
        """
        Create ECDSA signature

        Args:
            private_key: ECDSA private key
            message: Message to sign
            hash_algorithm: Hash algorithm to use

        Returns:
            DER-encoded signature
        """
        try:
            signature = private_key.sign(message, ec.ECDSA(hash_algorithm))
            return signature

        except Exception as e:
            raise SignatureError(f"ECDSA signing failed: {e}")

    @staticmethod
    def verify_ecdsa(
        public_key: ec.EllipticCurvePublicKey,
        message: bytes,
        signature: bytes,
        hash_algorithm: hashes.HashAlgorithm = hashes.SHA256(),
    ) -> bool:
        """
        Verify ECDSA signature

        Args:
            public_key: ECDSA public key
            message: Original message
            signature: DER-encoded signature
            hash_algorithm: Hash algorithm used

        Returns:
            True if signature is valid
        """
        try:
            public_key.verify(signature, message, ec.ECDSA(hash_algorithm))
            return True

        except Exception:
            return False

    @staticmethod
    def sign_with_rsa(
        private_key: RSAPrivateKey,
        message: bytes,
        hash_algorithm: hashes.HashAlgorithm = hashes.SHA256(),
    ) -> bytes:
        """
        Create RSA-PSS signature

        Args:
            private_key: RSA private key
            message: Message to sign
            hash_algorithm: Hash algorithm to use

        Returns:
            RSA signature
        """
        try:
            signature = private_key.sign(
                message,
                padding.PSS(mgf=padding.MGF1(hash_algorithm), salt_length=padding.PSS.MAX_LENGTH),
                hash_algorithm,
            )
            return signature

        except Exception as e:
            raise SignatureError(f"RSA signing failed: {e}")

    @staticmethod
    def verify_rsa(
        public_key: RSAPublicKey,
        message: bytes,
        signature: bytes,
        hash_algorithm: hashes.HashAlgorithm = hashes.SHA256(),
    ) -> bool:
        """
        Verify RSA-PSS signature

        Args:
            public_key: RSA public key
            message: Original message
            signature: RSA signature
            hash_algorithm: Hash algorithm used

        Returns:
            True if signature is valid
        """
        try:
            public_key.verify(
                signature,
                message,
                padding.PSS(mgf=padding.MGF1(hash_algorithm), salt_length=padding.PSS.MAX_LENGTH),
                hash_algorithm,
            )
            return True

        except Exception:
            return False


class SelectiveDisclosureCrypto:
    """
    Cryptographic operations for selective disclosure

    Implements hash-based selective disclosure according to ISO 18013-5.
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
                hashlib.sha256(
                    namespace.encode("utf-8") + element_identifier.encode("utf-8") + random_value
                ).digest()[:4],
                "big",
            )

            digest_data = [digest_id, random_value, element_identifier, element_value]

            # Encode as CBOR and hash
            cbor_data = cbor2.dumps(digest_data)
            digest_hash = hashlib.sha256(cbor_data).digest()

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

                # Create digest for verification
                digest_data = [digest_id, random_value, element_id, element_value]
                cbor_data = cbor2.dumps(digest_data)
                digest_hash = hashlib.sha256(cbor_data).digest()

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
            private_bytes = device_private_key.private_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PrivateFormat.Raw,
                encryption_algorithm=serialization.NoEncryption(),
            )

            # Derive binding key using HKDF
            hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=b"", info=key_info)

            return hkdf.derive(private_bytes)

        except Exception as e:
            raise CryptoError(f"Device binding key derivation failed: {e}")


def generate_random_bytes(length: int) -> bytes:
    """
    Generate cryptographically secure random bytes

    Args:
        length: Number of bytes to generate

    Returns:
        Random bytes
    """
    return os.urandom(length)


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
