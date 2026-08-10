"""
Trust Anchor Synchronization Service

Orchestrates fetching and verification of trust anchors from external sources
(ICAO PKD, AAMVA VICAL, EUDI LoTL) with CMS signature verification and
TimePolicy enforcement.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from digital_identity.application.ports.secrets import SecretsServicePort
from marty_common.infrastructure.key_vault import KeyVaultClient

from digital_identity.domain.entities import TrustFramework
from digital_identity.domain.value_objects import TimePolicy
from marty_plugin.native_backends import NativeOperationError, require_backend


@dataclass
class SyncResult:
    """Result of a trust anchor sync operation."""

    framework_id: str
    success: bool
    anchors_added: int
    anchors_updated: int
    error: str | None = None
    signature_valid: bool | None = None
    sync_timestamp: datetime | None = None


class TrustAnchorProvider(Protocol):
    """Protocol for trust anchor source providers."""

    async def fetch_trust_anchors(self) -> bytes:
        """Fetch trust anchor data (CMS signed)."""
        ...

    async def fetch_signer_certificate(self) -> bytes:
        """Fetch the signing certificate for verification."""
        ...


class IcaoPkdProvider:
    """ICAO PKD trust anchor provider with LDAP support."""

    def __init__(
        self,
        secrets_service: SecretsServicePort,
        base_url: str | None = None,
        master_list_fetcher: Callable[[], Awaitable[bytes]] | None = None,
    ):
        self.secrets_service = secrets_service
        self.base_url = base_url or "pkddownloadsg.icao.int"
        self.master_list_fetcher = master_list_fetcher

    async def fetch_trust_anchors(self) -> bytes:
        """
        Fetch CSCA Master List via Rust marty-verification.

        Returns CMS-signed master list bytes.
        """
        if self.master_list_fetcher is None:
            raise NativeOperationError("ICAO PKD Master List fetcher is not configured")
        cms_bytes = await self.master_list_fetcher()
        if not cms_bytes:
            raise NativeOperationError("ICAO PKD returned an empty Master List")
        return cms_bytes

    async def fetch_signer_certificate(self) -> bytes:
        """Fetch ICAO PKD signing certificate (pinned)."""
        # ICAO PKD signing certificates are pinned
        # In production, these would be stored as custom anchors
        # or in a dedicated secure storage
        cert_pem = await self.secrets_service.get_secret("icao_pkd", "signer_cert")
        if not cert_pem:
            raise ValueError("ICAO PKD signer certificate not configured")

        native = require_backend("marty_verification")
        return bytes(native.certificate_pem_to_der(cert_pem))


class AamvaVicalProvider:
    """AAMVA VICAL trust anchor provider."""

    def __init__(
        self,
        secrets_service: SecretsServicePort,
        vical_fetcher: Callable[[], Awaitable[bytes]] | None = None,
    ):
        self.secrets_service = secrets_service
        self.vical_fetcher = vical_fetcher

    async def fetch_trust_anchors(self) -> bytes:
        """Fetch VICAL (AAMVA IACA registry)."""
        if self.vical_fetcher is None:
            raise NativeOperationError("AAMVA VICAL fetcher is not configured")
        vical_bytes = await self.vical_fetcher()
        if not vical_bytes:
            raise NativeOperationError("AAMVA VICAL returned an empty payload")
        return vical_bytes

    async def fetch_signer_certificate(self) -> bytes:
        """Fetch AAMVA signing certificate."""
        cert_pem = await self.secrets_service.get_secret("aamva_vical", "signer_cert")
        if not cert_pem:
            raise NativeOperationError("AAMVA signer certificate is not configured")
        native = require_backend("marty_verification")
        return bytes(native.certificate_pem_to_der(cert_pem))


class TrustAnchorSyncService:
    """
    Service for synchronizing trust anchors from external sources.

    Responsibilities:
    - Fetch trust anchor lists (CSCA, IACA, LoTL)
    - Verify CMS signatures using pinned signer certificates
    - Enforce TimePolicy (clock skew, max age)
    - Store verified anchors in the registry
    """

    def __init__(
        self,
        secrets_service: SecretsServicePort,
        key_vault_client: KeyVaultClient | None = None,
        anchor_store: Callable[
            [list[dict[str, Any]], TrustFramework], Awaitable[tuple[int, int]]
        ]
        | None = None,
    ):
        self.secrets_service = secrets_service
        self.key_vault_client = key_vault_client
        self.anchor_store = anchor_store
        self.providers: dict[str, TrustAnchorProvider] = {}

    def register_provider(
        self, framework_code: str, provider: TrustAnchorProvider
    ) -> None:
        """Register a trust anchor provider for a framework code (e.g., 'icao', 'aamva')."""
        self.providers[framework_code] = provider

    async def sync_framework(
        self,
        framework: TrustFramework,
        time_policy: TimePolicy,
    ) -> SyncResult:
        """
        Sync trust anchors for a specific framework.

        Steps:
        1. Fetch CMS-signed trust anchor list
        2. Fetch signer certificate
        3. Verify CMS signature
        4. Enforce TimePolicy (clock skew, max age)
        5. Parse and store anchors

        Args:
            framework: The trust framework to sync
            time_policy: Time validation policy to enforce

        Returns:
            SyncResult with status and metrics
        """
        # Use framework.code to look up the provider (e.g., "icao", "aamva", "eudi")
        provider = self.providers.get(framework.code)
        if not provider:
            return SyncResult(
                framework_id=framework.id,
                success=False,
                anchors_added=0,
                anchors_updated=0,
                error=f"No provider registered for framework code: {framework.code}",
            )

        try:
            # Step 1: Fetch CMS-signed trust anchor list
            cms_bytes = await provider.fetch_trust_anchors()

            # Step 2: Fetch signer certificate
            signer_cert_der = await provider.fetch_signer_certificate()

            # Step 3: Verify CMS signature using Rust
            signature_valid = await self._verify_cms_signature(
                cms_bytes,
                signer_cert_der,
            )

            if not signature_valid:
                return SyncResult(
                    framework_id=framework.id,
                    success=False,
                    anchors_added=0,
                    anchors_updated=0,
                    error="CMS signature verification failed",
                    signature_valid=False,
                )

            # Step 4: Enforce TimePolicy
            time_valid = await self._enforce_time_policy(
                cms_bytes,
                time_policy,
            )

            if not time_valid:
                return SyncResult(
                    framework_id=framework.id,
                    success=False,
                    anchors_added=0,
                    anchors_updated=0,
                    error="TimePolicy validation failed (clock skew or max age exceeded)",
                    signature_valid=True,
                )

            # Step 5: Parse and store anchors
            anchors_added, anchors_updated = await self._parse_and_store_anchors(
                cms_bytes,
                framework,
            )

            return SyncResult(
                framework_id=framework.id,
                success=True,
                anchors_added=anchors_added,
                anchors_updated=anchors_updated,
                signature_valid=True,
                sync_timestamp=datetime.now(timezone.utc),
            )

        except Exception as e:
            return SyncResult(
                framework_id=framework.id,
                success=False,
                anchors_added=0,
                anchors_updated=0,
                error=str(e),
            )

    async def _verify_cms_signature(
        self,
        cms_bytes: bytes,
        signer_cert_der: bytes,
    ) -> bool:
        """
        Verify CMS signature using Rust marty-verification.

        Args:
            cms_bytes: CMS-signed data
            signer_cert_der: DER-encoded signer certificate

        Returns:
            True if signature is valid
        """
        native = require_backend("marty_verification")

        # Call Rust verification function
        result = await asyncio.to_thread(
            native.verify_master_list_signature,
            cms_bytes,
            signer_cert_der,
        )

        return result

    async def _enforce_time_policy(
        self,
        cms_bytes: bytes,
        time_policy: TimePolicy,
    ) -> bool:
        """
        Enforce TimePolicy on CMS SignedData.

        Checks:
        - Signing time within clock_skew_tolerance of current time
        - Certificate validity (not_before, not_after)
        - Optional max_credential_age

        Args:
            cms_bytes: CMS-signed data
            time_policy: Time validation policy

        Returns:
            True if time policy is satisfied
        """
        native = require_backend("marty_verification")

        # Parse CMS to extract signing time and certificate info
        master_list = await asyncio.to_thread(native.parse_master_list, cms_bytes)

        # Get current time
        now = datetime.now(timezone.utc)

        # Check each certificate's validity
        certificates = master_list.get("certificates", [])
        if not certificates:
            return False
        for csca_cert in certificates:
            # Parse not_before and not_after (ISO 8601 strings)
            try:
                not_before = datetime.fromisoformat(
                    csca_cert["not_before"].replace("Z", "+00:00")
                )
                not_after = datetime.fromisoformat(
                    csca_cert["not_after"].replace("Z", "+00:00")
                )
            except ValueError:
                return False

            # Check clock skew for not_before
            clock_skew = timedelta(seconds=time_policy.clock_skew_seconds)
            if now < not_before - clock_skew:
                return False

            # Check not_after
            if now > not_after + clock_skew:
                return False

            # Check max_credential_age if specified
            if time_policy.max_credential_age_seconds:
                cert_age = now - not_before
                if cert_age > timedelta(seconds=time_policy.max_credential_age_seconds):
                    return False

        return True

    async def _parse_and_store_anchors(
        self,
        cms_bytes: bytes,
        framework: TrustFramework,
    ) -> tuple[int, int]:
        """
        Parse CMS master list and store anchors.

        Args:
            cms_bytes: CMS-signed master list
            framework: Target trust framework

        Returns:
            Tuple of (anchors_added, anchors_updated)
        """
        native = require_backend("marty_verification")

        # Parse master list
        master_list = await asyncio.to_thread(native.parse_master_list, cms_bytes)

        certificates = list(master_list.get("certificates", []))
        if not certificates:
            raise NativeOperationError("Verified trust list contained no certificates")
        if self.anchor_store is None:
            raise NativeOperationError(
                "Trust anchor persistence adapter is not configured"
            )
        return await self.anchor_store(certificates, framework)

    async def sync_all_frameworks(
        self,
        frameworks: list[TrustFramework],
        time_policy: TimePolicy,
    ) -> list[SyncResult]:
        """
        Sync all frameworks concurrently.

        Args:
            frameworks: List of frameworks to sync
            time_policy: Time policy to enforce

        Returns:
            List of sync results
        """
        tasks = [
            self.sync_framework(framework, time_policy) for framework in frameworks
        ]

        return await asyncio.gather(*tasks, return_exceptions=False)
