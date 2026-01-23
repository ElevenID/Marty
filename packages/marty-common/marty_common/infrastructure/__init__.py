"""Infrastructure integration helpers for Marty services.

This package exposes shared client abstractions for storage, messaging,
and key management so individual services can avoid hard-coding
environment-specific dependencies.
"""

from .database import DatabaseConfig, DatabaseManager
from .event_bus import EventBusConfig, EventBusMessage, EventBusProvider
from .key_vault import KeyVaultClient, KeyVaultConfig, build_key_vault_client
from .models import (
    Base,
    CertificateRecord,
    CredentialEventLog,
    CredentialLedgerEntry,
    DigitalTravelCredentialRecord,
    EventDeadLetterRecord,
    EventOutboxRecord,
    MobileDrivingLicenseRecord,
    PassportRecord,
    TrustEntity,
)
from .object_storage import ObjectStorageClient, ObjectStorageConfig
from .outbox import OutboxDispatcher, OutboxDispatcherSettings, OutboxRepository
from .repositories import (
    CertificateRepository,
    CredentialLedgerRepository,
    DigitalTravelCredentialRepository,
    MobileDrivingLicenseRepository,
    PassportRepository,
    TrustEntityRepository,
)

__all__ = [
    "Base",
    "CertificateRecord",
    "CertificateRepository",
    "CredentialEventLog",
    "CredentialLedgerEntry",
    "CredentialLedgerRepository",
    "DatabaseConfig",
    "DatabaseManager",
    "DigitalTravelCredentialRecord",
    "DigitalTravelCredentialRepository",
    "EventBusConfig",
    "EventBusMessage",
    "EventBusProvider",
    "EventDeadLetterRecord",
    "EventOutboxRecord",
    "KeyVaultClient",
    "KeyVaultConfig",
    "MobileDrivingLicenseRecord",
    "MobileDrivingLicenseRepository",
    "ObjectStorageClient",
    "ObjectStorageConfig",
    "OutboxDispatcher",
    "OutboxDispatcherSettings",
    "OutboxRepository",
    "PassportRecord",
    "PassportRepository",
    "TrustEntity",
    "TrustEntityRepository",
    "build_key_vault_client",
]
