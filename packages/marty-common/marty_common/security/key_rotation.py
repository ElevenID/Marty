"""
Automated key rotation system for Marty services.

Provides automated key lifecycle management including creation, rotation,
distribution, and revocation of cryptographic keys across all services.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from marty_common.security.hsm import HSMInterface, create_hsm_service

logger = logging.getLogger(__name__)


class KeyType(Enum):
    """Types of cryptographic keys."""

    SIGNING = "signing"
    ENCRYPTION = "encryption"
    ROOT_CA = "root_ca"
    INTERMEDIATE_CA = "intermediate_ca"
    DOCUMENT_SIGNER = "document_signer"
    TLS = "tls"
    API_KEY = "api_key"


class KeyStatus(Enum):
    """Key lifecycle status."""

    ACTIVE = "active"
    PENDING_ROTATION = "pending_rotation"
    ROTATION_IN_PROGRESS = "rotation_in_progress"
    DEPRECATED = "deprecated"
    REVOKED = "revoked"
    EXPIRED = "expired"


@dataclass
class KeyMetadata:
    """Metadata for a cryptographic key."""

    key_id: str
    key_type: KeyType
    algorithm: str
    key_size: int
    service_name: str
    created_at: datetime
    expires_at: datetime
    status: KeyStatus = KeyStatus.ACTIVE
    version: int = 1
    parent_key_id: str | None = None
    rotation_policy_id: str | None = None
    tags: dict[str, str] = field(default_factory=dict)

    def is_expired(self) -> bool:
        """Check if key has expired."""
        return datetime.utcnow() > self.expires_at

    def needs_rotation(self, warning_days: int = 30) -> bool:
        """Check if key needs rotation based on warning period."""
        warning_threshold = datetime.utcnow() + timedelta(days=warning_days)
        return self.expires_at <= warning_threshold


@dataclass
class RotationPolicy:
    """Key rotation policy configuration."""

    policy_id: str
    name: str
    key_type: KeyType
    rotation_interval_days: int
    warning_days: int = 30
    auto_rotate: bool = True
    max_key_age_days: int = 365
    min_overlap_hours: int = 24
    notification_channels: list[str] = field(default_factory=list)
    services: list[str] = field(default_factory=list)

    def should_rotate(self, key_metadata: KeyMetadata) -> bool:
        """Check if key should be rotated according to policy."""
        if not self.auto_rotate:
            return False

        age = datetime.utcnow() - key_metadata.created_at
        return age.days >= self.rotation_interval_days or key_metadata.needs_rotation(
            self.warning_days
        )


class KeyStore(ABC):
    """Abstract interface for key storage backend."""

    @abstractmethod
    def store_key(self, key_id: str, key_data: bytes, metadata: KeyMetadata) -> bool:
        """Store a key with metadata."""

    @abstractmethod
    def get_key(self, key_id: str) -> tuple[bytes, KeyMetadata] | None:
        """Retrieve a key and its metadata."""

    @abstractmethod
    def list_keys(
        self, service_name: str | None = None, key_type: KeyType | None = None
    ) -> list[KeyMetadata]:
        """List keys matching criteria."""

    @abstractmethod
    def delete_key(self, key_id: str) -> bool:
        """Delete a key."""

    @abstractmethod
    def update_key_metadata(self, key_id: str, metadata: KeyMetadata) -> bool:
        """Update key metadata."""


class DatabaseKeyStore(KeyStore):
    """Database-backed key store."""

    def __init__(self, db_connector) -> None:
        self.db = db_connector
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """Ensure key storage tables exist."""
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS key_store (
            key_id VARCHAR(255) PRIMARY KEY,
            key_data BYTEA NOT NULL,
            key_type VARCHAR(50) NOT NULL,
            algorithm VARCHAR(100) NOT NULL,
            key_size INTEGER NOT NULL,
            service_name VARCHAR(100) NOT NULL,
            created_at TIMESTAMP NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            status VARCHAR(50) NOT NULL DEFAULT 'active',
            version INTEGER NOT NULL DEFAULT 1,
            parent_key_id VARCHAR(255),
            rotation_policy_id VARCHAR(255),
            tags JSONB DEFAULT '{}',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_key_store_service
        ON key_store(service_name);

        CREATE INDEX IF NOT EXISTS idx_key_store_type
        ON key_store(key_type);

        CREATE INDEX IF NOT EXISTS idx_key_store_status
        ON key_store(status);

        CREATE INDEX IF NOT EXISTS idx_key_store_expires
        ON key_store(expires_at);
        """

        try:
            self.db.execute(create_table_sql)
        except Exception as e:
            logger.exception(f"Failed to create key store tables: {e}")

    def store_key(self, key_id: str, key_data: bytes, metadata: KeyMetadata) -> bool:
        """Store a key with metadata."""
        try:
            insert_sql = """
            INSERT INTO key_store (
                key_id, key_data, key_type, algorithm, key_size,
                service_name, created_at, expires_at, status, version,
                parent_key_id, rotation_policy_id, tags
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """

            self.db.execute(
                insert_sql,
                (
                    key_id,
                    key_data,
                    metadata.key_type.value,
                    metadata.algorithm,
                    metadata.key_size,
                    metadata.service_name,
                    metadata.created_at,
                    metadata.expires_at,
                    metadata.status.value,
                    metadata.version,
                    metadata.parent_key_id,
                    metadata.rotation_policy_id,
                    json.dumps(metadata.tags),
                ),
            )
        except Exception as e:
            logger.exception(f"Failed to store key {key_id}: {e}")
            return False
        else:
            return True

    def get_key(self, key_id: str) -> tuple[bytes, KeyMetadata] | None:
        """Retrieve a key and its metadata."""
        try:
            select_sql = """
            SELECT key_data, key_type, algorithm, key_size, service_name,
                   created_at, expires_at, status, version, parent_key_id,
                   rotation_policy_id, tags
            FROM key_store WHERE key_id = %s
            """

            result = self.db.fetchone(select_sql, (key_id,))
            if not result:
                return None

            (
                key_data,
                key_type,
                algorithm,
                key_size,
                service_name,
                created_at,
                expires_at,
                status,
                version,
                parent_key_id,
                rotation_policy_id,
                tags,
            ) = result

            metadata = KeyMetadata(
                key_id=key_id,
                key_type=KeyType(key_type),
                algorithm=algorithm,
                key_size=key_size,
                service_name=service_name,
                created_at=created_at,
                expires_at=expires_at,
                status=KeyStatus(status),
                version=version,
                parent_key_id=parent_key_id,
                rotation_policy_id=rotation_policy_id,
                tags=json.loads(tags) if tags else {},
            )
        except Exception as e:
            logger.exception(f"Failed to get key {key_id}: {e}")
            return None
        else:
            return key_data, metadata

    def list_keys(
        self, service_name: str | None = None, key_type: KeyType | None = None
    ) -> list[KeyMetadata]:
        """List keys matching criteria."""
        try:
            conditions = []
            params = []

            if service_name:
                conditions.append("service_name = %s")
                params.append(service_name)

            if key_type:
                conditions.append("key_type = %s")
                params.append(key_type.value)

            where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""

            select_sql = f"""
            SELECT key_id, key_type, algorithm, key_size, service_name,
                   created_at, expires_at, status, version, parent_key_id,
                   rotation_policy_id, tags
            FROM key_store{where_clause}
            ORDER BY created_at DESC
            """

            results = self.db.fetchall(select_sql, params)

            keys = []
            for row in results:
                (
                    key_id,
                    key_type,
                    algorithm,
                    key_size,
                    service_name,
                    created_at,
                    expires_at,
                    status,
                    version,
                    parent_key_id,
                    rotation_policy_id,
                    tags,
                ) = row

                metadata = KeyMetadata(
                    key_id=key_id,
                    key_type=KeyType(key_type),
                    algorithm=algorithm,
                    key_size=key_size,
                    service_name=service_name,
                    created_at=created_at,
                    expires_at=expires_at,
                    status=KeyStatus(status),
                    version=version,
                    parent_key_id=parent_key_id,
                    rotation_policy_id=rotation_policy_id,
                    tags=json.loads(tags) if tags else {},
                )
                keys.append(metadata)
        except Exception as e:
            logger.exception(f"Failed to list keys: {e}")
            return []
        else:
            return keys

    def delete_key(self, key_id: str) -> bool:
        """Delete a key."""
        try:
            delete_sql = "DELETE FROM key_store WHERE key_id = %s"
            self.db.execute(delete_sql, (key_id,))
        except Exception as e:
            logger.exception(f"Failed to delete key {key_id}: {e}")
            return False
        else:
            return True

    def update_key_metadata(self, key_id: str, metadata: KeyMetadata) -> bool:
        """Update key metadata."""
        try:
            update_sql = """
            UPDATE key_store SET
                status = %s, version = %s, parent_key_id = %s,
                rotation_policy_id = %s, tags = %s, updated_at = CURRENT_TIMESTAMP
            WHERE key_id = %s
            """

            self.db.execute(
                update_sql,
                (
                    metadata.status.value,
                    metadata.version,
                    metadata.parent_key_id,
                    metadata.rotation_policy_id,
                    json.dumps(metadata.tags),
                    key_id,
                ),
            )
        except Exception as e:
            logger.exception(f"Failed to update key metadata for {key_id}: {e}")
            return False
        else:
            return True


class KeyDistributor:
    """Handles key distribution to services."""

    def __init__(self) -> None:
        self._distribution_handlers: dict[str, Callable] = {}

    def register_handler(self, service_name: str, handler: Callable) -> None:
        """Register a key distribution handler for a service."""
        self._distribution_handlers[service_name] = handler

    def distribute_key(self, service_name: str, key_metadata: KeyMetadata, key_data: bytes) -> bool:
        """Distribute a key to a service."""
        handler = self._distribution_handlers.get(service_name)
        if not handler:
            logger.warning(f"No distribution handler for service {service_name}")
            return False

        try:
            return handler(key_metadata, key_data)
        except Exception as e:
            logger.exception(f"Failed to distribute key to {service_name}: {e}")
            return False

    def notify_key_rotation(self, service_name: str, old_key_id: str, new_key_id: str) -> bool:
        """Notify a service about key rotation."""
        handler = self._distribution_handlers.get(service_name)
        if not handler:
            return False

        try:
            # Handler should implement rotation notification
            if hasattr(handler, "on_key_rotation"):
                rotation_result = handler.on_key_rotation(old_key_id, new_key_id)
            else:
                rotation_result = True
        except Exception as e:
            logger.exception(f"Failed to notify {service_name} about rotation: {e}")
            return False
        else:
            return rotation_result


class KeyRotationManager:
    """Main key rotation management system."""

    def __init__(
        self, hsm_service: HSMInterface, key_store: KeyStore, distributor: KeyDistributor
    ) -> None:
        self.hsm = hsm_service
        self.key_store = key_store
        self.distributor = distributor
        self.policies: dict[str, RotationPolicy] = {}

        self._running = False
        self._check_interval = 3600  # 1 hour
        self._rotation_thread: threading.Thread | None = None
        self._executor = ThreadPoolExecutor(max_workers=5)

    def add_rotation_policy(self, policy: RotationPolicy) -> None:
        """Add a key rotation policy."""
        self.policies[policy.policy_id] = policy
        logger.info(f"Added rotation policy: {policy.name}")

    def remove_rotation_policy(self, policy_id: str) -> None:
        """Remove a key rotation policy."""
        self.policies.pop(policy_id, None)
        logger.info(f"Removed rotation policy: {policy_id}")

    def create_key(
        self,
        service_name: str,
        key_type: KeyType,
        algorithm: str,
        key_size: int,
        validity_days: int = 365,
        rotation_policy_id: str | None = None,
    ) -> str | None:
        """Create a new key."""
        try:
            # Generate key using HSM
            key_id = f"{service_name}_{key_type.value}_{uuid.uuid4().hex[:8]}"
            key_data = self.hsm.generate_key(key_id, algorithm, key_size)

            if not key_data:
                logger.error(f"Failed to generate key {key_id}")
                return None

            # Create metadata
            metadata = KeyMetadata(
                key_id=key_id,
                key_type=key_type,
                algorithm=algorithm,
                key_size=key_size,
                service_name=service_name,
                created_at=datetime.utcnow(),
                expires_at=datetime.utcnow() + timedelta(days=validity_days),
                rotation_policy_id=rotation_policy_id,
            )

            # Store key
            if not self.key_store.store_key(key_id, key_data, metadata):
                logger.error(f"Failed to store key {key_id}")
                return None

            # Distribute to service
            if not self.distributor.distribute_key(service_name, metadata, key_data):
                logger.warning(f"Failed to distribute key {key_id} to {service_name}")

            logger.info(f"Created key {key_id} for {service_name}")
        except Exception as e:
            logger.exception(f"Failed to create key: {e}")
            return None
        else:
            return key_id

    def rotate_key(self, key_id: str) -> str | None:
        """Rotate a specific key."""
        try:
            # Get existing key
            key_result = self.key_store.get_key(key_id)
            if not key_result:
                logger.error(f"Key {key_id} not found for rotation")
                return None

            _, old_metadata = key_result

            # Mark old key as pending rotation
            old_metadata.status = KeyStatus.PENDING_ROTATION
            self.key_store.update_key_metadata(key_id, old_metadata)

            # Create new key
            new_key_id = self.create_key(
                service_name=old_metadata.service_name,
                key_type=old_metadata.key_type,
                algorithm=old_metadata.algorithm,
                key_size=old_metadata.key_size,
                rotation_policy_id=old_metadata.rotation_policy_id,
            )

            if not new_key_id:
                # Revert status if rotation failed
                old_metadata.status = KeyStatus.ACTIVE
                self.key_store.update_key_metadata(key_id, old_metadata)
                return None

            # Update new key to reference old key
            new_key_result = self.key_store.get_key(new_key_id)
            if new_key_result:
                _, new_metadata = new_key_result
                new_metadata.parent_key_id = key_id
                new_metadata.version = old_metadata.version + 1
                self.key_store.update_key_metadata(new_key_id, new_metadata)

            # Notify service about rotation
            self.distributor.notify_key_rotation(old_metadata.service_name, key_id, new_key_id)

            # After grace period, mark old key as deprecated
            def deprecate_old_key() -> None:
                time.sleep(86400)  # 24 hour grace period
                old_metadata.status = KeyStatus.DEPRECATED
                self.key_store.update_key_metadata(key_id, old_metadata)

            threading.Thread(target=deprecate_old_key, daemon=True).start()

            logger.info(f"Rotated key {key_id} -> {new_key_id}")
        except Exception as e:
            logger.exception(f"Failed to rotate key {key_id}: {e}")
            return None
        else:
            return new_key_id

    def revoke_key(self, key_id: str, reason: str = "") -> bool:
        """Revoke a key."""
        try:
            key_result = self.key_store.get_key(key_id)
            if not key_result:
                return False

            _, metadata = key_result
            metadata.status = KeyStatus.REVOKED
            metadata.tags["revocation_reason"] = reason
            metadata.tags["revoked_at"] = datetime.utcnow().isoformat()

            if self.key_store.update_key_metadata(key_id, metadata):
                # Revoke in HSM
                self.hsm.revoke_key(key_id)
                logger.info(f"Revoked key {key_id}: {reason}")
                success = True
            else:
                success = False
        except Exception as e:
            logger.exception(f"Failed to revoke key {key_id}: {e}")
            return False
        else:
            return success

    def start_automatic_rotation(self, check_interval: int = 3600) -> None:
        """Start automatic key rotation monitoring."""
        self._check_interval = check_interval
        self._running = True
        self._rotation_thread = threading.Thread(target=self._rotation_loop, daemon=True)
        self._rotation_thread.start()
        logger.info("Started automatic key rotation")

    def stop_automatic_rotation(self) -> None:
        """Stop automatic key rotation."""
        self._running = False
        if self._rotation_thread:
            self._rotation_thread.join(timeout=5.0)
        self._executor.shutdown(wait=True)
        logger.info("Stopped automatic key rotation")

    def _rotation_loop(self) -> None:
        """Main rotation monitoring loop."""
        while self._running:
            try:
                self._check_for_rotations()
                time.sleep(self._check_interval)
            except Exception as e:
                logger.exception(f"Error in rotation loop: {e}")
                time.sleep(60)  # Brief pause before retry

    def _check_for_rotations(self) -> None:
        """Check for keys that need rotation."""
        all_keys = self.key_store.list_keys()

        for key_metadata in all_keys:
            if key_metadata.status not in [KeyStatus.ACTIVE, KeyStatus.DEPRECATED]:
                continue

            # Check if key has expired
            if key_metadata.is_expired():
                logger.warning(f"Key {key_metadata.key_id} has expired")
                key_metadata.status = KeyStatus.EXPIRED
                self.key_store.update_key_metadata(key_metadata.key_id, key_metadata)
                continue

            # Check rotation policies
            if key_metadata.rotation_policy_id:
                policy = self.policies.get(key_metadata.rotation_policy_id)
                if policy and policy.should_rotate(key_metadata):
                    logger.info(f"Scheduling rotation for {key_metadata.key_id}")
                    self._executor.submit(self.rotate_key, key_metadata.key_id)

    def get_key_status(self, key_id: str) -> dict[str, Any] | None:
        """Get detailed status for a key."""
        key_result = self.key_store.get_key(key_id)
        if not key_result:
            return None

        _, metadata = key_result

        return {
            "key_id": metadata.key_id,
            "service": metadata.service_name,
            "type": metadata.key_type.value,
            "algorithm": metadata.algorithm,
            "status": metadata.status.value,
            "created_at": metadata.created_at.isoformat(),
            "expires_at": metadata.expires_at.isoformat(),
            "version": metadata.version,
            "parent_key_id": metadata.parent_key_id,
            "is_expired": metadata.is_expired(),
            "needs_rotation": metadata.needs_rotation(),
            "tags": metadata.tags,
        }


def create_default_rotation_manager(
    db_connector, hsm_service: HSMInterface | None = None
) -> KeyRotationManager:
    """Create a key rotation manager with default configuration."""
    if not hsm_service:
        hsm_service = create_hsm_service()

    key_store = DatabaseKeyStore(db_connector)
    distributor = KeyDistributor()

    manager = KeyRotationManager(hsm_service, key_store, distributor)

    # Add default policies
    manager.add_rotation_policy(
        RotationPolicy(
            policy_id="standard_signing",
            name="Standard Signing Key Rotation",
            key_type=KeyType.SIGNING,
            rotation_interval_days=90,
            warning_days=30,
            auto_rotate=True,
        )
    )

    manager.add_rotation_policy(
        RotationPolicy(
            policy_id="ca_keys",
            name="Certificate Authority Key Rotation",
            key_type=KeyType.ROOT_CA,
            rotation_interval_days=1095,  # 3 years
            warning_days=90,
            auto_rotate=False,  # Manual rotation for CA keys
        )
    )

    manager.add_rotation_policy(
        RotationPolicy(
            policy_id="tls_keys",
            name="TLS Key Rotation",
            key_type=KeyType.TLS,
            rotation_interval_days=365,
            warning_days=30,
            auto_rotate=True,
        )
    )

    return manager
