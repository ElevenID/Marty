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
    """Retired compatibility class that cannot provide cryptographic results."""

    def __init__(self) -> None:
        self._keys: dict[str, dict[str, Any]] = {}
        self._initialized = False

    def initialize(self, config: dict[str, Any]) -> bool:
        del config
        raise HSMOperationError("The mock HSM provider is disabled")

    def generate_key(
        self,
        key_id: str,
        key_type: HSMKeyType,
        key_size: int | None = None,
        curve_name: str | None = None,
    ) -> dict[str, Any]:
        del key_id, key_type, key_size, curve_name
        raise HSMOperationError("The mock HSM provider is disabled")

    def get_public_key(self, key_id: str) -> bytes:
        del key_id
        raise HSMOperationError("The mock HSM provider is disabled")

    def sign(self, key_id: str, data: bytes, algorithm: str) -> bytes:
        del key_id, data, algorithm
        raise HSMOperationError("The mock HSM provider is disabled")

    def verify(self, key_id: str, data: bytes, signature: bytes, algorithm: str) -> bool:
        del key_id, data, signature, algorithm
        raise HSMOperationError("The mock HSM provider is disabled")

    def delete_key(self, key_id: str) -> bool:
        del key_id
        raise HSMOperationError("The mock HSM provider is disabled")

    def list_keys(self) -> list[str]:
        raise HSMOperationError("The mock HSM provider is disabled")

    def get_key_info(self, key_id: str) -> dict[str, Any]:
        del key_id
        raise HSMOperationError("The mock HSM provider is disabled")


def create_hsm_service(hsm_type: str = "mock", config: dict[str, Any] | None = None) -> HSMInterface:
    """
    Factory function to create HSM service instance.

    Args:
        hsm_type: Type of HSM service ("mock", "pkcs11", etc.)
        config: HSM configuration

    Returns:
        HSM service instance
    """
    del config
    if hsm_type == "mock":
        raise HSMOperationError("The mock HSM provider is disabled")
    raise HSMOperationError(f"Unsupported HSM type: {hsm_type}")
