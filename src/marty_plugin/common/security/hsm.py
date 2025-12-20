"""
Hardware Security Module (HSM) integration interface.

Provides abstraction layer for HSM operations to enable secure key management
and cryptographic operations using hardware-backed security.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class HSMKeyType(Enum):
    """HSM key types."""

    RSA = "rsa"
    EC = "ec"
    AES = "aes"


class HSMOperationError(Exception):
    """Exception raised for HSM operation failures."""

    def __init__(self, message: str, error_code: str | None = None) -> None:
        self.error_code = error_code
        super().__init__(message)


class HSMInterface(ABC):
    """Abstract interface for HSM operations."""

    @abstractmethod
    def initialize(self, config: dict[str, Any]) -> bool:
        """
        Initialize HSM connection.

        Args:
            config: HSM configuration parameters

        Returns:
            True if initialization successful
        """

    @abstractmethod
    def generate_key(
        self,
        key_id: str,
        key_type: HSMKeyType,
        key_size: int | None = None,
        curve_name: str | None = None,
    ) -> dict[str, Any]:
        """
        Generate a new key in HSM.

        Args:
            key_id: Unique identifier for the key
            key_type: Type of key to generate
            key_size: Key size in bits (for RSA)
            curve_name: Curve name (for EC)

        Returns:
            Key metadata dictionary
        """

    @abstractmethod
    def get_public_key(self, key_id: str) -> bytes:
        """
        Get public key from HSM.

        Args:
            key_id: Key identifier

        Returns:
            Public key in DER format
        """

    @abstractmethod
    def sign(self, key_id: str, data: bytes, algorithm: str) -> bytes:
        """
        Sign data using HSM key.

        Args:
            key_id: Key identifier
            data: Data to sign
            algorithm: Signing algorithm

        Returns:
            Signature bytes
        """

    @abstractmethod
    def verify(self, key_id: str, data: bytes, signature: bytes, algorithm: str) -> bool:
        """
        Verify signature using HSM key.

        Args:
            key_id: Key identifier
            data: Original data
            signature: Signature to verify
            algorithm: Signature algorithm

        Returns:
            True if signature is valid
        """

    @abstractmethod
    def delete_key(self, key_id: str) -> bool:
        """
        Delete key from HSM.

        Args:
            key_id: Key identifier

        Returns:
            True if deletion successful
        """

    @abstractmethod
    def list_keys(self) -> list[str]:
        """
        List all key identifiers in HSM.

        Returns:
            List of key identifiers
        """

    @abstractmethod
    def get_key_info(self, key_id: str) -> dict[str, Any]:
        """
        Get key information from HSM.

        Args:
            key_id: Key identifier

        Returns:
            Key information dictionary
        """


class MockHSMService(HSMInterface):
    """Mock HSM service for testing and development."""

    def __init__(self) -> None:
        self._keys: dict[str, dict[str, Any]] = {}
        self._initialized = False

    def initialize(self, config: dict[str, Any]) -> bool:
        """Initialize mock HSM."""
        logger.info("Initializing mock HSM service")
        self._initialized = True
        return True

    def generate_key(
        self,
        key_id: str,
        key_type: HSMKeyType,
        key_size: int | None = None,
        curve_name: str | None = None,
    ) -> dict[str, Any]:
        """Generate a mock key."""
        if not self._initialized:
            msg = "HSM not initialized"
            raise HSMOperationError(msg)

        if key_id in self._keys:
            msg = f"Key {key_id} already exists"
            raise HSMOperationError(msg)

        key_info = {
            "key_id": key_id,
            "key_type": key_type.value,
            "key_size": key_size,
            "curve_name": curve_name,
            "created_at": "2024-01-01T00:00:00Z",  # Mock timestamp
            "status": "active",
        }

        self._keys[key_id] = key_info
        logger.info("Generated mock key: %s", key_id)
        return key_info

    def get_public_key(self, key_id: str) -> bytes:
        """Get mock public key."""
        if key_id not in self._keys:
            msg = f"Key {key_id} not found"
            raise HSMOperationError(msg)

        # Return mock DER-encoded public key
        return b"MOCK_PUBLIC_KEY_DER_DATA"

    def sign(self, key_id: str, data: bytes, algorithm: str) -> bytes:
        """Create mock signature."""
        if key_id not in self._keys:
            msg = f"Key {key_id} not found"
            raise HSMOperationError(msg)

        # Return mock signature
        return b"MOCK_SIGNATURE_DATA"

    def verify(self, key_id: str, data: bytes, signature: bytes, algorithm: str) -> bool:
        """Verify mock signature."""
        if key_id not in self._keys:
            msg = f"Key {key_id} not found"
            raise HSMOperationError(msg)

        # Mock verification always succeeds for correct mock signature
        return signature == b"MOCK_SIGNATURE_DATA"

    def delete_key(self, key_id: str) -> bool:
        """Delete mock key."""
        if key_id in self._keys:
            del self._keys[key_id]
            logger.info("Deleted mock key: %s", key_id)
            return True
        return False

    def list_keys(self) -> list[str]:
        """List mock keys."""
        return list(self._keys.keys())

    def get_key_info(self, key_id: str) -> dict[str, Any]:
        """Get mock key info."""
        if key_id not in self._keys:
            msg = f"Key {key_id} not found"
            raise HSMOperationError(msg)

        return self._keys[key_id].copy()


def create_hsm_service(
    hsm_type: str = "mock", config: dict[str, Any] | None = None
) -> HSMInterface:
    """
    Factory function to create HSM service instance.

    Args:
        hsm_type: Type of HSM service ("mock", "pkcs11", etc.)
        config: HSM configuration

    Returns:
        HSM service instance
    """
    if hsm_type == "mock":
        service = MockHSMService()
    else:
        msg = f"Unsupported HSM type: {hsm_type}"
        raise ValueError(msg)

    service.initialize(config or {})
    return service
