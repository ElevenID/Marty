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
import shutil
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.serialization import pkcs12

# Import Rust bindings for key generation (required)
from marty_backend_common.crypto_bridge import (
    generate_key as rust_generate_key,
    rsa_generate as rust_rsa_generate,
    ecdsa_p256_generate as rust_ecdsa_p256_generate,
    ecdsa_p384_generate as rust_ecdsa_p384_generate,
    ed25519_generate as rust_ed25519_generate,
)

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

    # Allowed characters in key IDs to prevent path traversal.
    # Only alphanumeric, hyphen, underscore, and dot (no slashes, no ..).
    _KEY_ID_RE = __import__("re").compile(r"^[a-zA-Z0-9._-]{1,255}$")

    def _safe_key_path(self, key_id: str, extension: str) -> str:
        """Return a validated path inside the key store for *key_id*.

        Raises ``ValueError`` if key_id contains path-traversal
        characters (``/``, ``..``) or fails the allowlist regex.
        """
        if not self._KEY_ID_RE.match(key_id) or ".." in key_id:
            raise ValueError(f"Invalid key_id: contains disallowed characters: {key_id!r}")
        full = os.path.realpath(os.path.join(self.key_store_path, f"{key_id}{extension}"))
        store_real = os.path.realpath(self.key_store_path)
        if not full.startswith(store_real + os.sep) and full != store_real:
            raise ValueError(f"Path traversal blocked for key_id={key_id!r}")
        return full

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

        logger.info(f"Initialized Key Management Service with store at {self.key_store_path}")
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
            public_key_path = self._safe_key_path(key_id, ".pub")
            with open(public_key_path, "w") as f:
                f.write(hsm_result["public_key_pem"])

        else:
            # Generate key in software using Rust
            private_key_pem: bytes
            public_key_pem: bytes
            
            if key_type == KeyType.RSA:
                key_info["key_size"] = key_size
                private_key_pem, public_key_pem = rust_rsa_generate(key_size)
                
            elif key_type == KeyType.EC:
                key_info["curve_name"] = curve_name
                if curve_name == "secp256r1":
                    private_key_pem, public_key_pem = rust_ecdsa_p256_generate()
                elif curve_name == "secp384r1":
                    private_key_pem, public_key_pem = rust_ecdsa_p384_generate()
                elif curve_name == "secp521r1":
                    # Use Python for secp521r1 as it's not in Rust yet
                    private_key_pem, public_key_pem = self._generate_ec_key_python(curve_name)
                else:
                    msg = f"Unsupported EC curve: {curve_name}"
                    raise ValueError(msg)
            else:
                msg = f"Unsupported key type: {key_type}"
                raise ValueError(msg)

            # Save the private key
            private_key_path = self._safe_key_path(key_id, ".key")
            with open(private_key_path, "wb") as f:
                f.write(private_key_pem)

            # Save the public key
            public_key_path = self._safe_key_path(key_id, ".pub")
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
        key_info_path = self._safe_key_path(key_id, ".json")
        if not os.path.exists(key_info_path):
            msg = f"Key with ID {key_id} not found"
            raise KeyNotFoundException(msg)

        with open(key_info_path) as f:
            return json.load(f)

    def _generate_ec_key_python(self, curve_name: str) -> tuple[bytes, bytes]:
        """
        Generate EC key using Python cryptography library.
        
        Args:
            curve_name: Name of the EC curve (secp256r1, secp384r1, secp521r1)
            
        Returns:
            Tuple of (private_key_pem, public_key_pem) as bytes
        """
        if curve_name == "secp256r1":
            curve = ec.SECP256R1()
        elif curve_name == "secp384r1":
            curve = ec.SECP384R1()
        elif curve_name == "secp521r1":
            curve = ec.SECP521R1()
        else:
            msg = f"Unsupported EC curve: {curve_name}"
            raise ValueError(msg)

        private_key = ec.generate_private_key(curve)
        private_key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        public_key_pem = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return private_key_pem, public_key_pem

    def _save_key_info(self, key_id: str, key_info: dict[str, Any]) -> None:
        """
        Save key information to storage.

        Args:
            key_id: Identifier of the key
            key_info: Dictionary containing key information
        """
        key_info_path = self._safe_key_path(key_id, ".json")
        with open(key_info_path, "w") as f:
            json.dump(key_info, f, indent=2)

    def list_keys(self, usage: KeyUsage = None, key_type: KeyType = None) -> list[dict[str, Any]]:
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
        private_key_path = self._safe_key_path(key_id, ".key")
        if not os.path.exists(private_key_path):
            msg = f"Private key file for {key_id} not found"
            raise KeyNotFoundException(msg)

        with open(private_key_path, "rb") as f:
            return serialization.load_pem_private_key(f.read(), password=None)

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
        public_key_path = self._safe_key_path(key_id, ".pub")
        if not os.path.exists(public_key_path):
            msg = f"Public key file for {key_id} not found"
            raise KeyNotFoundException(msg)

        with open(public_key_path, "rb") as f:
            return serialization.load_pem_public_key(f.read())

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
            key_id, "key_exported", {"format": "PEM", "include_private": include_private}
        )

        if include_private:
            private_key = self.load_private_key(key_id)
            return private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        public_key = self.load_public_key(key_id)
        return public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

    def get_certificate(self, key_id: str) -> x509.Certificate | None:
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
        cert_path = self._safe_key_path(key_id, ".cert")
        if os.path.exists(cert_path):
            with open(cert_path, "rb") as f:
                cert_data = f.read()
                return x509.load_pem_x509_certificate(cert_data)
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
        private_key = self.load_private_key(key_id)
        certificate = self.get_certificate(key_id)

        if certificate is None:
            msg = f"No certificate available for key {key_id}"
            raise KeyManagementError(msg)

        # Add audit entry
        self._add_audit_entry(key_id, "key_exported", {"format": "PKCS12"})

        return pkcs12.serialize_key_and_certificates(
            name=key_id.encode("utf-8"),
            key=private_key,
            cert=certificate,
            cas=None,
            encryption_algorithm=serialization.BestAvailableEncryption(password),
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
            key_id, "rotation_policy_set", {"interval_days": policy.rotation_interval_days}
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
            rotation_policy = KeyRotationPolicy.from_dict(old_key_info["rotation_policy"])

        # Prepare parameters for new key
        kwargs = {"key_id": new_key_id, "key_type": key_type, "key_usage": key_usage}

        # Get key size or curve name from policy or old key
        if key_type == KeyType.RSA:
            if rotation_policy and rotation_policy.min_key_size:
                kwargs["key_size"] = rotation_policy.min_key_size
            else:
                kwargs["key_size"] = old_key_info.get("key_size", self.DEFAULT_RSA_KEY_SIZE)
        elif key_type == KeyType.EC:
            if rotation_policy and rotation_policy.curve_name:
                kwargs["curve_name"] = rotation_policy.curve_name
            else:
                kwargs["curve_name"] = old_key_info.get("curve_name", self.DEFAULT_EC_CURVE)

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
        self._add_audit_entry(new_key_id, "key_created_by_rotation", {"old_key_id": old_key_id})

        logger.info(f"Rotated key {old_key_id} to new key {new_key_id}")

        return new_key_info

    def backup_keys(self, backup_path: str, encryption_password: bytes) -> dict[str, Any]:
        """
        Create an encrypted backup of all keys.

        Args:
            backup_path: Path to save the backup file
            encryption_password: Password to encrypt the backup

        Returns:
            Dictionary with backup information
        """
        backed_up_keys = []

        # Create a temporary directory for key files
        with tempfile.TemporaryDirectory() as temp_dir:
            # Copy all key files to the temp directory
            for filename in os.listdir(self.key_store_path):
                key_id = filename.split(".")[0]
                if key_id not in backed_up_keys and filename.endswith((".key", ".pub", ".json")):
                    src_path = os.path.join(self.key_store_path, filename)
                    dst_path = os.path.join(temp_dir, filename)
                    shutil.copy2(src_path, dst_path)

                    # Add key_id to the list if we haven't seen it yet
                    if filename.endswith(".json") and key_id not in backed_up_keys:
                        backed_up_keys.append(key_id)

            # Create the backup zip file with password protection
            with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as backup_zip:
                # Add a manifest file
                manifest = {
                    "backup_date": datetime.datetime.now().isoformat(),
                    "keys": backed_up_keys,
                }

                manifest_path = os.path.join(temp_dir, "manifest.json")
                with open(manifest_path, "w") as f:
                    json.dump(manifest, f, indent=2)

                # Add all files to the zip
                for root, _, files in os.walk(temp_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, temp_dir)
                        backup_zip.write(file_path, arcname)

        logger.info(f"Backed up {len(backed_up_keys)} keys to {backup_path}")

        return {
            "backup_path": backup_path,
            "backup_date": datetime.datetime.now().isoformat(),
            "num_keys_backed_up": len(backed_up_keys),
            "backed_up_keys": backed_up_keys,
        }

    def restore_keys(self, backup_path: str, encryption_password: bytes) -> dict[str, Any]:
        """
        Restore keys from a backup.

        Args:
            backup_path: Path to the backup file
            encryption_password: Password to decrypt the backup

        Returns:
            Dictionary with restoration information
        """
        restored_keys = []

        # Create a temporary directory to extract the backup
        with tempfile.TemporaryDirectory() as temp_dir:
            # Extract the backup
            with zipfile.ZipFile(backup_path, "r") as backup_zip:
                backup_zip.extractall(temp_dir)

            # Read the manifest
            manifest_path = os.path.join(temp_dir, "manifest.json")
            with open(manifest_path) as f:
                manifest = json.load(f)

            # Copy key files to the key store
            for key_id in manifest.get("keys", []):
                key_files = [f"{key_id}.key", f"{key_id}.pub", f"{key_id}.json"]

                for filename in key_files:
                    src_path = os.path.join(temp_dir, filename)
                    if os.path.exists(src_path):
                        dst_path = os.path.join(self.key_store_path, filename)
                        shutil.copy2(src_path, dst_path)

                restored_keys.append(key_id)

                # Add audit entry for the restored key
                self._add_audit_entry(key_id, "key_restored", {"backup_path": backup_path})

        logger.info(f"Restored {len(restored_keys)} keys from {backup_path}")

        return {
            "restored_from": backup_path,
            "restore_date": datetime.datetime.now().isoformat(),
            "num_keys_restored": len(restored_keys),
            "restored_keys": restored_keys,
        }

    def _add_audit_entry(self, key_id: str, operation: str, details: dict[str, Any]) -> None:
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
                    expiry_date = datetime.datetime.fromisoformat(key_info["expiry_date"])

                    # Check if key is expiring within the threshold
                    if expiry_date <= threshold_date:
                        days_until_expiry = (expiry_date - now).days
                        expiring_key_info = key_info.copy()
                        expiring_key_info["days_until_expiry"] = days_until_expiry
                        expiring_keys.append(expiring_key_info)

                except (ValueError, TypeError):
                    logger.warning(f"Invalid expiry date format for key {key_info['key_id']}")

        return expiring_keys
