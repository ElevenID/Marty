#!/usr/bin/env python3
"""
Key Management Service.

This service is responsible for:
1. Key generation and management (RSA, EC)
2. Key rotation and lifecycle management
3. HSM integration for secure key storage
4. Key backup and recovery
5. Key usage auditing and tracking

This module can use Rust implementations from marty-verification for key
generation when available, providing better performance and security.
"""

from __future__ import annotations

import datetime
import enum
import json
import logging
import os
import uuid
from dataclasses import dataclass
from typing import Any

from marty_common import crypto_bridge
from marty_common.crypto_bridge import Certificate
from marty_common.native_backends import NativeOperationError

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class KeyType(enum.Enum):
    """Types of cryptographic keys supported by the service."""

    RSA = "rsa"
    EC = "ec"
    # Can be extended with other key types as needed


class KeyUsage(enum.Enum):
    """Purposes for which keys can be used."""

    DOCUMENT_SIGNING = "document_signing"
    AUTHENTICATION = "authentication"
    ENCRYPTION = "encryption"
    CERTIFICATE_SIGNING = "certificate_signing"
    # Can be extended with other usages as needed


class KeyNotFoundException(Exception):
    """Exception raised when a requested key cannot be found."""


class KeyManagementError(Exception):
    """Exception raised for general key management errors."""


@dataclass
class KeyRotationPolicy:
    """Policy defining key rotation parameters."""

    rotation_interval_days: int
    key_usage: KeyUsage
    min_key_size: int | None = None
    curve_name: str | None = None
    auto_rotate: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert the policy to a dictionary for storage."""
        result = {
            "rotation_interval_days": self.rotation_interval_days,
            "key_usage": self.key_usage.value,
            "auto_rotate": self.auto_rotate,
        }

        if self.min_key_size:
            result["min_key_size"] = self.min_key_size

        if self.curve_name:
            result["curve_name"] = self.curve_name

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KeyRotationPolicy:
        """Create a policy object from dictionary data."""
        return cls(
            rotation_interval_days=data["rotation_interval_days"],
            key_usage=KeyUsage(data["key_usage"]),
            min_key_size=data.get("min_key_size"),
            curve_name=data.get("curve_name"),
            auto_rotate=data.get("auto_rotate", False),
        )


class KeyManagementService:
    """
    Service for managing cryptographic keys throughout their lifecycle.

    This service handles key generation, storage, rotation, backup,
    and HSM integration. It supports both software keys and
    hardware-backed keys stored in HSMs.
    """

    DEFAULT_KEY_STORE_PATH = os.path.join(os.environ.get("DATA_DIR", "data"), "keys")
    DEFAULT_RSA_KEY_SIZE = 2048
    DEFAULT_EC_CURVE = "secp256r1"

    def __init__(
        self,
        key_store_path: str | None = None,
        use_hsm: bool = False,
        hsm_service=None,
    ) -> None:
        """
        Initialize the Key Management Service.

        Args:
            key_store_path: Directory where keys will be stored
            use_hsm: Whether to use a Hardware Security Module for key operations
            hsm_service: Instance of HSM service to use (if use_hsm is True)
        """
        self.key_store_path = key_store_path or self.DEFAULT_KEY_STORE_PATH
        self.use_hsm = use_hsm
        self.hsm_service = hsm_service

        # Create key store directory if it doesn't exist
        if not os.path.exists(self.key_store_path):
            os.makedirs(self.key_store_path, exist_ok=True)

        logger.info(
            f"Initialized Key Management Service with store at {self.key_store_path}"
        )
        logger.info(f"HSM integration {'enabled' if use_hsm else 'disabled'}")
        logger.info("Using Rust bindings for key generation")

    def generate_key(
        self,
        key_id: str,
        key_type: KeyType,
        key_usage: KeyUsage,
        key_size: int | None = None,
        curve_name: str | None = None,
        metadata: dict[str, Any] | None = None,
        expiry_date: str | None = None,
    ) -> dict[str, Any]:
        """
        Generate a new cryptographic key.

        Args:
            key_id: Unique identifier for the key
            key_type: Type of key (RSA, EC, etc.)
            key_usage: Intended usage of the key
            key_size: Size in bits for RSA keys
            curve_name: Curve name for EC keys
            metadata: Additional metadata to store with the key
            expiry_date: ISO format date when the key expires

        Returns:
            Dictionary containing the key information
        """
        logger.info(f"Generating {key_type.value.upper()} key with ID {key_id}")

        if key_type == KeyType.RSA and not key_size:
            key_size = self.DEFAULT_RSA_KEY_SIZE

        if key_type == KeyType.EC and not curve_name:
            curve_name = self.DEFAULT_EC_CURVE

        key_info = {
            "key_id": key_id,
            "key_type": key_type.value,
            "key_usage": key_usage.value,
            "created_at": datetime.datetime.now().isoformat(),
            "metadata": metadata or {},
            "rotated": False,
            "hsm_backed": self.use_hsm,
        }

        if expiry_date:
            key_info["expiry_date"] = expiry_date

        # Create the key
        if self.use_hsm and self.hsm_service:
            # Generate key in HSM
            hsm_result = self.hsm_service.generate_key(
                key_id=key_id, key_type=key_type.value, key_size=key_size
            )

            key_info["hsm_key_handle"] = hsm_result["key_handle"]

            # For HSM keys, we only store the public key locally
            public_key_path = os.path.join(self.key_store_path, f"{key_id}.pub")
            with open(public_key_path, "w") as f:
                f.write(hsm_result["public_key_pem"])

        else:
            # Generate key in software using Rust
            if key_type == KeyType.RSA:
                key_info["key_size"] = key_size
                private_key_der, public_key_der = crypto_bridge.rsa_generate(key_size)
            elif key_type == KeyType.EC:
                key_info["curve_name"] = curve_name
                generators = {
                    "secp256r1": (crypto_bridge.ecdsa_p256_generate, "P256"),
                    "secp384r1": (crypto_bridge.ecdsa_p384_generate, "P384"),
                }
                if curve_name == "secp521r1":
                    raise NativeOperationError(
                        "P-521 key generation cannot be serialized by the required native backend"
                    )
                generator = generators.get(curve_name)
                if generator is None:
                    msg = f"Unsupported EC curve: {curve_name}"
                    raise ValueError(msg)
                generate, native_key_type = generator
                private_key_raw, public_key_raw = generate()
                private_key_der = crypto_bridge.raw_private_key_to_pkcs8(
                    private_key_raw, native_key_type
                )
                public_key_der = crypto_bridge.raw_public_key_to_spki(
                    public_key_raw, native_key_type
                )
            else:
                msg = f"Unsupported key type: {key_type}"
                raise ValueError(msg)

            private_key_pem = crypto_bridge.save_private_key_pem(
                private_key_der
            ).encode("ascii")
            public_key_pem = crypto_bridge.save_public_key_pem(public_key_der).encode(
                "ascii"
            )

            # Save the private key
            private_key_path = os.path.join(self.key_store_path, f"{key_id}.key")
            with open(private_key_path, "wb") as f:
                f.write(private_key_pem)

            # Save the public key
            public_key_path = os.path.join(self.key_store_path, f"{key_id}.pub")
            with open(public_key_path, "wb") as f:
                f.write(public_key_pem)

        # Save the key info
        self._save_key_info(key_id, key_info)

        # Add audit trail entry
        self._add_audit_entry(key_id, "key_generated", {})

        return key_info

    def get_key_info(self, key_id: str) -> dict[str, Any]:
        """
        Get information about a key.

        Args:
            key_id: Identifier of the key to retrieve info for

        Returns:
            Dictionary containing key information

        Raises:
            KeyNotFoundException: If the key does not exist
        """
        key_info_path = os.path.join(self.key_store_path, f"{key_id}.json")
        if not os.path.exists(key_info_path):
            msg = f"Key with ID {key_id} not found"
            raise KeyNotFoundException(msg)

        with open(key_info_path) as f:
            return json.load(f)

    def _save_key_info(self, key_id: str, key_info: dict[str, Any]) -> None:
        """
        Save key information to storage.

        Args:
            key_id: Identifier of the key
            key_info: Dictionary containing key information
        """
        key_info_path = os.path.join(self.key_store_path, f"{key_id}.json")
        with open(key_info_path, "w") as f:
            json.dump(key_info, f, indent=2)

    def list_keys(
        self, usage: KeyUsage = None, key_type: KeyType = None
    ) -> list[dict[str, Any]]:
        """
        List all keys or filter by usage/type.

        Args:
            usage: Optional usage filter
            key_type: Optional key type filter

        Returns:
            List of key info dictionaries
        """
        results = []

        for filename in os.listdir(self.key_store_path):
            if not filename.endswith(".json"):
                continue

            key_id = filename.replace(".json", "")
            try:
                key_info = self.get_key_info(key_id)

                # Apply filters if provided
                if usage and KeyUsage(key_info["key_usage"]) != usage:
                    continue

                if key_type and KeyType(key_info["key_type"]) != key_type:
                    continue

                results.append(key_info)

            except (KeyNotFoundException, json.JSONDecodeError):
                # Skip invalid key files
                continue

        return results

    def load_private_key(self, key_id: str):
        """
        Load a private key for use.

        Args:
            key_id: Identifier of the key to load

        Returns:
            Private key object for software keys, or HSM key reference for HSM keys

        Raises:
            KeyNotFoundException: If the key does not exist
        """
        try:
            key_info = self.get_key_info(key_id)
        except KeyNotFoundException:
            msg = f"Key with ID {key_id} not found"
            raise KeyNotFoundException(msg)

        # For HSM-backed keys, get the key from the HSM
        if key_info.get("hsm_backed", False) and self.hsm_service:
            if "hsm_key_handle" not in key_info:
                msg = f"HSM key handle not found for key {key_id}"
                raise KeyManagementError(msg)

            return self.hsm_service.get_key(key_info["hsm_key_handle"])

        # For software keys, load from file
        private_key_path = os.path.join(self.key_store_path, f"{key_id}.key")
        if not os.path.exists(private_key_path):
            msg = f"Private key file for {key_id} not found"
            raise KeyNotFoundException(msg)

        with open(private_key_path, "rb") as f:
            private_key_pem = f.read()
        crypto_bridge.load_private_key_pem(private_key_pem.decode("ascii"))
        return private_key_pem

    def load_public_key(self, key_id: str):
        """
        Load a public key.

        Args:
            key_id: Identifier of the key to load

        Returns:
            Public key object

        Raises:
            KeyNotFoundException: If the key does not exist
        """
        public_key_path = os.path.join(self.key_store_path, f"{key_id}.pub")
        if not os.path.exists(public_key_path):
            msg = f"Public key file for {key_id} not found"
            raise KeyNotFoundException(msg)

        with open(public_key_path, "rb") as f:
            public_key_pem = f.read()
        crypto_bridge.load_public_key_pem(public_key_pem.decode("ascii"))
        return public_key_pem

    def export_key_as_pem(self, key_id: str, include_private: bool = False) -> bytes:
        """
        Export a key in PEM format.

        Args:
            key_id: Identifier of the key to export
            include_private: Whether to include the private key

        Returns:
            PEM-encoded key data

        Raises:
            KeyNotFoundException: If the key does not exist
        """
        try:
            self.get_key_info(key_id)
        except KeyNotFoundException:
            msg = f"Key with ID {key_id} not found"
            raise KeyNotFoundException(msg)

        # Add audit entry
        self._add_audit_entry(
            key_id,
            "key_exported",
            {"format": "PEM", "include_private": include_private},
        )

        if include_private:
            return self.load_private_key(key_id)
        return self.load_public_key(key_id)

    def get_certificate(self, key_id: str) -> Certificate | None:
        """
        Get a certificate associated with a key.

        Args:
            key_id: Identifier of the key

        Returns:
            Certificate object or None if no certificate exists
        """
        # This method would be implemented to retrieve a certificate
        # associated with the key. For this example, we return None
        # as it's expected to be mocked in tests.
        cert_path = os.path.join(self.key_store_path, f"{key_id}.cert")
        if os.path.exists(cert_path):
            with open(cert_path, "rb") as f:
                cert_data = f.read()
                return Certificate.from_pem(cert_data)
        return None

    def export_key_as_pkcs12(self, key_id: str, password: bytes) -> bytes:
        """
        Export a key and its certificate in PKCS12 format.

        Args:
            key_id: Identifier of the key to export
            password: Password to protect the PKCS12 file

        Returns:
            PKCS12-encoded key and certificate

        Raises:
            KeyNotFoundException: If the key does not exist
        """
        del password
        self.get_key_info(key_id)
        raise NativeOperationError(
            "PKCS#12 serialization is not exposed by the required native backend"
        )

    def set_rotation_policy(self, key_id: str, policy: KeyRotationPolicy) -> None:
        """
        Set a rotation policy for a key.

        Args:
            key_id: Identifier of the key
            policy: Rotation policy to apply

        Raises:
            KeyNotFoundException: If the key does not exist
        """
        key_info = self.get_key_info(key_id)
        key_info["rotation_policy"] = policy.to_dict()

        # Save updated key info
        self._save_key_info(key_id, key_info)

        # Add audit entry
        self._add_audit_entry(
            key_id,
            "rotation_policy_set",
            {"interval_days": policy.rotation_interval_days},
        )

        logger.info(
            f"Set rotation policy for key {key_id} with {policy.rotation_interval_days} day interval"
        )

    def rotate_key(self, old_key_id: str) -> dict[str, Any]:
        """
        Rotate a key, creating a new key with the same properties.

        Args:
            old_key_id: Identifier of the key to rotate

        Returns:
            Dictionary with information about the new key

        Raises:
            KeyNotFoundException: If the key does not exist
        """
        old_key_info = self.get_key_info(old_key_id)

        # Generate a new key ID
        new_key_id = f"{uuid.uuid4().hex}-{old_key_info['key_usage']}"

        # Get key type and other parameters from old key
        key_type = KeyType(old_key_info["key_type"])
        key_usage = KeyUsage(old_key_info["key_usage"])

        # Get rotation policy if it exists
        rotation_policy = None
        if "rotation_policy" in old_key_info:
            rotation_policy = KeyRotationPolicy.from_dict(
                old_key_info["rotation_policy"]
            )

        # Prepare parameters for new key
        kwargs = {"key_id": new_key_id, "key_type": key_type, "key_usage": key_usage}

        # Get key size or curve name from policy or old key
        if key_type == KeyType.RSA:
            if rotation_policy and rotation_policy.min_key_size:
                kwargs["key_size"] = rotation_policy.min_key_size
            else:
                kwargs["key_size"] = old_key_info.get(
                    "key_size", self.DEFAULT_RSA_KEY_SIZE
                )
        elif key_type == KeyType.EC:
            if rotation_policy and rotation_policy.curve_name:
                kwargs["curve_name"] = rotation_policy.curve_name
            else:
                kwargs["curve_name"] = old_key_info.get(
                    "curve_name", self.DEFAULT_EC_CURVE
                )

        # Copy over metadata and add rotation info
        metadata = old_key_info.get("metadata", {}).copy()
        metadata["rotated_from"] = old_key_id
        kwargs["metadata"] = metadata

        # Generate the new key
        new_key_info = self.generate_key(**kwargs)

        # Update old key to mark as rotated
        old_key_info["rotated"] = True
        old_key_info["rotated_to"] = new_key_id
        old_key_info["rotated_at"] = datetime.datetime.now().isoformat()
        self._save_key_info(old_key_id, old_key_info)

        # Add audit entries
        self._add_audit_entry(old_key_id, "key_rotated", {"new_key_id": new_key_id})
        self._add_audit_entry(
            new_key_id, "key_created_by_rotation", {"old_key_id": old_key_id}
        )

        logger.info(f"Rotated key {old_key_id} to new key {new_key_id}")

        return new_key_info

    def backup_keys(
        self, backup_path: str, encryption_password: bytes
    ) -> dict[str, Any]:
        """Reject the retired ZIP backup path, which did not encrypt key material."""
        del backup_path, encryption_password
        raise NativeOperationError(
            "Encrypted key backup is unavailable without a native or HSM-backed implementation"
        )

    def restore_keys(
        self, backup_path: str, encryption_password: bytes
    ) -> dict[str, Any]:
        """Reject archives from the retired unauthenticated ZIP restore path."""
        del backup_path, encryption_password
        raise NativeOperationError(
            "Encrypted key restore is unavailable without a native or HSM-backed implementation"
        )

    def _add_audit_entry(
        self, key_id: str, operation: str, details: dict[str, Any]
    ) -> None:
        """
        Add an entry to the key's audit trail.

        Args:
            key_id: Identifier of the key
            operation: Type of operation performed
            details: Additional details about the operation
        """
        try:
            key_info = self.get_key_info(key_id)
        except KeyNotFoundException:
            logger.warning(f"Cannot add audit entry for non-existent key {key_id}")
            return

        # Initialize audit trail if it doesn't exist
        if "audit_trail" not in key_info:
            key_info["audit_trail"] = []

        # Add the new entry
        entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "operation": operation,
            "details": details,
        }

        key_info["audit_trail"].append(entry)

        # Save updated key info
        self._save_key_info(key_id, key_info)

    def get_key_audit_trail(self, key_id: str) -> list[dict[str, Any]]:
        """
        Get the audit trail for a key.

        Args:
            key_id: Identifier of the key

        Returns:
            List of audit trail entries

        Raises:
            KeyNotFoundException: If the key does not exist
        """
        key_info = self.get_key_info(key_id)
        return key_info.get("audit_trail", [])

    def check_expiring_keys(self, days_threshold: int = 30) -> list[dict[str, Any]]:
        """
        Check for keys that will expire soon.

        Args:
            days_threshold: Number of days threshold for expiry warning

        Returns:
            List of keys that will expire within the threshold
        """
        expiring_keys = []
        now = datetime.datetime.now()
        threshold_date = now + datetime.timedelta(days=days_threshold)

        for key_info in self.list_keys():
            if "expiry_date" in key_info:
                try:
                    expiry_date = datetime.datetime.fromisoformat(
                        key_info["expiry_date"]
                    )

                    # Check if key is expiring within the threshold
                    if expiry_date <= threshold_date:
                        days_until_expiry = (expiry_date - now).days
                        expiring_key_info = key_info.copy()
                        expiring_key_info["days_until_expiry"] = days_until_expiry
                        expiring_keys.append(expiring_key_info)

                except (ValueError, TypeError):
                    logger.warning(
                        f"Invalid expiry date format for key {key_info['key_id']}"
                    )

        return expiring_keys
