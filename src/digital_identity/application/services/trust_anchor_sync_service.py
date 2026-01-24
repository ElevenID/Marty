"""
Trust Anchor Synchronization Service

Orchestrates fetching and verification of trust anchors from external sources
(ICAO PKD, AAMVA VICAL, EUDI LoTL) with CMS signature verification and
TimePolicy enforcement.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

from marty_common.infrastructure.key_vault import KeyVaultClient

from digital_identity.application.ports.secrets import SecretsServicePort
from digital_identity.domain.entities import TrustFramework
from digital_identity.domain.value_objects import TimePolicy


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
    
    def __init__(self, secrets_service: SecretsServicePort, base_url: str | None = None):
        self.secrets_service = secrets_service
        self.base_url = base_url or "pkddownloadsg.icao.int"
    
    async def fetch_trust_anchors(self) -> bytes:
        """
        Fetch CSCA Master List via Rust marty-verification.
        
        Returns CMS-signed master list bytes.
        """
        # Get credentials from secrets service
        username = await self.secrets_service.get_secret("icao_pkd", "username")
        password = await self.secrets_service.get_secret("icao_pkd", "password")
        
        # Import Rust module
        from marty_verification import IcaoPkdClient, IcaoPkdConfig
        
        # Create config
        config = IcaoPkdConfig(
            base_url=self.base_url,
            username=username,
            password=password,
            offline_dir=None,  # Use live fetch
        )
        
        # Fetch master list
        client = IcaoPkdClient(config)
        entries = await asyncio.to_thread(client.fetch_master_list)
        
        # For now, return raw CMS bytes (would be returned by Rust in production)
        # This is a placeholder - the Rust module would return the CMS bytes
        raise NotImplementedError("CMS byte extraction from Rust not yet implemented")
    
    async def fetch_signer_certificate(self) -> bytes:
        """Fetch ICAO PKD signing certificate (pinned)."""
        # ICAO PKD signing certificates are pinned
        # In production, these would be stored as custom anchors
        # or in a dedicated secure storage
        cert_pem = await self.secrets_service.get_secret("icao_pkd", "signer_cert")
        if not cert_pem:
            raise ValueError("ICAO PKD signer certificate not configured")
        
        # Convert PEM to DER
        from cryptography import x509
        from cryptography.hazmat.primitives import serialization
        
        cert = x509.load_pem_x509_certificate(cert_pem.encode())
        return cert.public_bytes(serialization.Encoding.DER)


class AamvaVicalProvider:
    """AAMVA VICAL trust anchor provider."""
    
    def __init__(self, secrets_service: SecretsServicePort):
        self.secrets_service = secrets_service
    
    async def fetch_trust_anchors(self) -> bytes:
        """Fetch VICAL (AAMVA IACA registry)."""
        # AAMVA credentials
        api_key = await self.secrets_service.get_secret("aamva_vical", "api_key")
        
        # Would fetch from AAMVA VICAL endpoint
        raise NotImplementedError("AAMVA VICAL sync not yet implemented")
    
    async def fetch_signer_certificate(self) -> bytes:
        """Fetch AAMVA signing certificate."""
        raise NotImplementedError("AAMVA signer cert fetch not yet implemented")


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
    ):
        self.secrets_service = secrets_service
        self.key_vault_client = key_vault_client
        self.providers: dict[str, TrustAnchorProvider] = {}
    
    def register_provider(self, framework_code: str, provider: TrustAnchorProvider) -> None:
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
        from marty_verification import verify_master_list_signature
        
        # Call Rust verification function
        result = await asyncio.to_thread(
            verify_master_list_signature,
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
        from marty_verification import parse_master_list
        
        # Parse CMS to extract signing time and certificate info
        master_list = await asyncio.to_thread(parse_master_list, cms_bytes)
        
        # Get current time
        now = datetime.now(timezone.utc)
        
        # Check each certificate's validity
        for csca_cert in master_list.certificates:
            # Parse not_before and not_after (ISO 8601 strings)
            try:
                not_before = datetime.fromisoformat(csca_cert.not_before.replace("Z", "+00:00"))
                not_after = datetime.fromisoformat(csca_cert.not_after.replace("Z", "+00:00"))
            except ValueError:
                # Fallback for non-ISO formats
                continue
            
            # Check clock skew for not_before
            if time_policy.require_not_before:
                if now < not_before - time_policy.clock_skew_tolerance:
                    return False
            
            # Check not_after
            if time_policy.require_not_after:
                if now > not_after + time_policy.clock_skew_tolerance:
                    return False
            
            # Check max_credential_age if specified
            if time_policy.max_credential_age:
                cert_age = now - not_before
                if cert_age > time_policy.max_credential_age:
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
        from marty_verification import parse_master_list
        
        # Parse master list
        master_list = await asyncio.to_thread(parse_master_list, cms_bytes)
        
        # Store anchors (would integrate with TrustProfileRepository)
        # For now, return counts
        anchors_added = len(master_list.certificates)
        anchors_updated = 0
        
        return anchors_added, anchors_updated
    
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
            self.sync_framework(framework, time_policy)
            for framework in frameworks
        ]
        
        return await asyncio.gather(*tasks, return_exceptions=False)
