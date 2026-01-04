"""
Challenge Signing

RSA keypair management and challenge signing for push notifications.
Server signs outgoing challenges so mobile clients can verify authenticity.
"""
from __future__ import annotations

import base64
import logging
import os
from functools import lru_cache
from typing import Optional

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey

from .types import MartyChallengePayload

logger = logging.getLogger(__name__)


class SigningKeyNotConfiguredError(Exception):
    """Raised when signing key is not configured."""
    pass


class ChallengeSigner:
    """
    RSA-based challenge signer.
    
    Signs outgoing challenges using the server's private key.
    The corresponding public key is shared with mobile clients
    during device registration for signature verification.
    """
    
    def __init__(
        self,
        private_key: RSAPrivateKey,
        public_key: RSAPublicKey,
        key_id: Optional[str] = None,
    ):
        """
        Initialize the signer with an RSA keypair.
        
        Args:
            private_key: RSA private key for signing
            public_key: RSA public key for distribution
            key_id: Optional key identifier for key rotation
        """
        self._private_key = private_key
        self._public_key = public_key
        self._key_id = key_id or "default"
    
    @classmethod
    def from_pem(cls, private_key_pem: str, password: Optional[bytes] = None) -> "ChallengeSigner":
        """
        Create signer from PEM-encoded private key.
        
        Args:
            private_key_pem: PEM-encoded RSA private key
            password: Optional password for encrypted keys
            
        Returns:
            ChallengeSigner instance
        """
        private_key = serialization.load_pem_private_key(
            private_key_pem.encode("utf-8"),
            password=password,
        )
        if not isinstance(private_key, RSAPrivateKey):
            raise ValueError("Key must be an RSA private key")
        
        public_key = private_key.public_key()
        return cls(private_key, public_key)
    
    @classmethod
    def from_env(cls) -> Optional["ChallengeSigner"]:
        """
        Create signer from environment variables.
        
        Looks for:
        - MARTY_SIGNING_PRIVATE_KEY: PEM-encoded private key (required)
        - MARTY_SIGNING_KEY_PASSWORD: Optional key password
        - MARTY_SIGNING_KEY_ID: Optional key identifier
        
        Returns:
            ChallengeSigner instance or None if not configured
        """
        private_key_pem = os.environ.get("MARTY_SIGNING_PRIVATE_KEY")
        if not private_key_pem:
            logger.warning(
                "MARTY_SIGNING_PRIVATE_KEY not set. "
                "Challenge signing is disabled. "
                "Generate a key with: openssl genrsa -out private.pem 2048"
            )
            return None
        
        password = os.environ.get("MARTY_SIGNING_KEY_PASSWORD")
        password_bytes = password.encode("utf-8") if password else None
        
        signer = cls.from_pem(private_key_pem, password_bytes)
        signer._key_id = os.environ.get("MARTY_SIGNING_KEY_ID", "default")
        
        logger.info(f"Challenge signer initialized with key ID: {signer._key_id}")
        return signer
    
    @classmethod
    def generate_keypair(cls, key_size: int = 2048) -> "ChallengeSigner":
        """
        Generate a new RSA keypair.
        
        For development/testing only. In production, use managed keys.
        
        Args:
            key_size: RSA key size in bits (2048 or 4096 recommended)
            
        Returns:
            ChallengeSigner with newly generated keypair
        """
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=key_size,
        )
        return cls(private_key, private_key.public_key(), key_id="generated")
    
    @property
    def key_id(self) -> str:
        """Return the key identifier."""
        return self._key_id
    
    def get_public_key_pem(self) -> str:
        """
        Get the public key in PEM format.
        
        Returns:
            PEM-encoded public key string
        """
        return self._public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")
    
    def get_public_key_der_base64(self) -> str:
        """
        Get the public key in base64-encoded DER format.
        
        This format is compact and suitable for mobile clients.
        
        Returns:
            Base64-encoded DER public key
        """
        der_bytes = self._public_key.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return base64.b64encode(der_bytes).decode("utf-8")
    
    def sign(self, data: str) -> str:
        """
        Sign a string using RSA-SHA256.
        
        Args:
            data: String to sign
            
        Returns:
            Base64-encoded signature
        """
        signature = self._private_key.sign(
            data.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode("utf-8")
    
    def sign_challenge(self, challenge: MartyChallengePayload) -> str:
        """
        Sign a challenge payload.
        
        Uses the canonical string representation of the challenge.
        
        Args:
            challenge: Challenge payload to sign
            
        Returns:
            Base64-encoded signature
        """
        canonical = challenge.canonical_string()
        return self.sign(canonical)


# =============================================================================
# Global Signer Instance
# =============================================================================

_signer: Optional[ChallengeSigner] = None


def configure_signer(signer: ChallengeSigner) -> None:
    """Configure the global challenge signer. Called at app startup."""
    global _signer
    _signer = signer
    logger.info(f"Challenge signer configured with key ID: {signer.key_id}")


def get_signer() -> Optional[ChallengeSigner]:
    """Get the configured challenge signer, or None if not configured."""
    return _signer


@lru_cache(maxsize=1)
def init_signer_from_env() -> Optional[ChallengeSigner]:
    """
    Initialize signer from environment variables (cached).
    
    Returns:
        ChallengeSigner or None if not configured
    """
    signer = ChallengeSigner.from_env()
    if signer:
        configure_signer(signer)
    return signer


def get_server_public_key() -> Optional[str]:
    """
    Get the server's public key in PEM format.
    
    Returns:
        PEM-encoded public key or None if signer not configured
    """
    signer = get_signer()
    if signer:
        return signer.get_public_key_pem()
    return None


def get_server_public_key_der_base64() -> Optional[str]:
    """
    Get the server's public key in base64-encoded DER format.
    
    Returns:
        Base64-encoded DER public key or None if signer not configured
    """
    signer = get_signer()
    if signer:
        return signer.get_public_key_der_base64()
    return None


def sign_challenge(challenge: MartyChallengePayload) -> MartyChallengePayload:
    """
    Sign a challenge and return it with the signature populated.
    
    Args:
        challenge: Challenge to sign
        
    Returns:
        Challenge with signature field populated
        
    Raises:
        SigningKeyNotConfiguredError: If no signer is configured
    """
    signer = get_signer()
    if not signer:
        raise SigningKeyNotConfiguredError(
            "Challenge signing is not configured. "
            "Set MARTY_SIGNING_PRIVATE_KEY environment variable."
        )
    
    challenge.signature = signer.sign_challenge(challenge)
    return challenge
