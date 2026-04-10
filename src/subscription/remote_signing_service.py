"""
Remote Signing Service

Orchestrates remote signing operations using customer-provided KMS/HSM.
Production tiers (STARTER, PROFESSIONAL, ENTERPRISE) use this service
instead of the service-managed key vault.

Security:
- Timeout protection (30s default)
- Exponential backoff retry (3 attempts)
- TTL cache with auto-invalidation
- Circuit breaker to fast-fail after consecutive failures
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional
from uuid import UUID

from cachetools import TTLCache
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from marty_backend_common.crypto.kms_provider import (
    AWSKMSProvider,
    AzureKeyVaultProvider,
    GCPCloudKMSProvider,
    KMSManager,
    KMSProviderInterface,
    KeyIdentity,
    KeyPurpose,
    SoftwareHSMProvider,
)
from marty_plugin.common.crypto_role import CryptoRole

from .kms_config_service import KMSConfigError, KMSConfigService
from .metrics import kms_signing_duration_seconds, record_operation, kms_errors_total
from .models import Organization, Subscription
from .square_service import PLAN_LIMITS, SquarePlan

logger = logging.getLogger(__name__)


class RemoteSigningError(Exception):
    """Remote signing error."""

    pass


class CircuitBreakerOpen(RemoteSigningError):
    """Raised when the circuit breaker is open and requests are rejected."""

    pass


class CircuitBreaker:
    """
    Simple circuit breaker for KMS operations.

    States:
    - CLOSED: Normal operation, requests pass through.
    - OPEN: Too many failures, requests are rejected immediately.
    - HALF_OPEN: After recovery timeout, one probe request is allowed.

    Transitions:
    - CLOSED -> OPEN: After `failure_threshold` consecutive failures.
    - OPEN -> HALF_OPEN: After `recovery_timeout` seconds.
    - HALF_OPEN -> CLOSED: On success.
    - HALF_OPEN -> OPEN: On failure (resets recovery timer).
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._state = self.CLOSED
        self._failure_count = 0
        self._last_failure_time: float | None = None

    @property
    def state(self) -> str:
        if self._state == self.OPEN and self._last_failure_time is not None:
            if time.monotonic() - self._last_failure_time >= self.recovery_timeout:
                self._state = self.HALF_OPEN
        return self._state

    def record_success(self) -> None:
        self._failure_count = 0
        self._state = self.CLOSED

    def record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count >= self.failure_threshold:
            self._state = self.OPEN

    def check(self) -> None:
        """Raise CircuitBreakerOpen if the circuit is open."""
        current = self.state
        if current == self.OPEN:
            raise CircuitBreakerOpen(
                f"Circuit breaker is open after {self.failure_threshold} consecutive "
                f"failures. Retry after {self.recovery_timeout}s."
            )


class RemoteSigningService:
    """
    Remote signing service for production tiers.

    Orchestrates signing operations using customer-provided KMS/HSM:
    - Creates KMS provider instances from organization config
    - Manages provider connection lifecycle with caching
    - Validates tier requirements
    - Routes signing operations to appropriate KMS
    - Provides timeout and retry protection
    
    Cache:
    - TTL: 1 hour (3600 seconds)
    - Max size: 100 organizations
    - Auto-invalidation on config changes
    """

    def __init__(
        self,
        db: AsyncSession,
        kms_config_service: KMSConfigService,
        cache_ttl: int = 3600,  # 1 hour cache TTL
        cache_maxsize: int = 100,  # Max 100 cached providers
        operation_timeout: float = 30.0,  # 30 second timeout
        max_retry_attempts: int = 3,  # 3 retry attempts
        cb_failure_threshold: int = 5,  # Circuit breaker: 5 consecutive failures
        cb_recovery_timeout: float = 60.0,  # Circuit breaker: 60s recovery
    ):
        """
        Initialize remote signing service.

        Args:
            db: Database session
            kms_config_service: KMS configuration service
            cache_ttl: Cache time-to-live in seconds (default: 3600 = 1 hour)
            cache_maxsize: Maximum cache size (default: 100)
            operation_timeout: Timeout for KMS operations in seconds (default: 30)
            max_retry_attempts: Maximum retry attempts (default: 3)
            cb_failure_threshold: Failures before circuit opens (default: 5)
            cb_recovery_timeout: Seconds before half-open probe (default: 60)
        """
        self.db = db
        self.kms_config_service = kms_config_service
        self.operation_timeout = operation_timeout
        self.max_retry_attempts = max_retry_attempts
        self.logger = logging.getLogger(__name__)

        # TTL cache: automatically evicts entries after ttl seconds
        self._provider_cache: TTLCache = TTLCache(
            maxsize=cache_maxsize,
            ttl=cache_ttl,
        )
        self._manager_cache: TTLCache = TTLCache(
            maxsize=cache_maxsize,
            ttl=cache_ttl,
        )
        self._cache_lock = asyncio.Lock()

        # Per-organization circuit breakers
        self._circuit_breakers: dict[UUID, CircuitBreaker] = {}
        self._cb_failure_threshold = cb_failure_threshold
        self._cb_recovery_timeout = cb_recovery_timeout

    def _get_circuit_breaker(self, org_id: UUID) -> CircuitBreaker:
        """Get or create a circuit breaker for an organization."""
        if org_id not in self._circuit_breakers:
            self._circuit_breakers[org_id] = CircuitBreaker(
                failure_threshold=self._cb_failure_threshold,
                recovery_timeout=self._cb_recovery_timeout,
            )
        return self._circuit_breakers[org_id]

    async def get_provider(
        self,
        organization: Organization,
    ) -> KMSProviderInterface:
        """
        Get or create KMS provider for organization.

        Args:
            organization: Organization

        Returns:
            KMS provider instance

        Raises:
            RemoteSigningError: If provider creation fails or tier invalid
        """
        # Check cache
        if organization.id in self._provider_cache:
            return self._provider_cache[organization.id]

        # Get configuration and credentials
        try:
            config, credentials = await self.kms_config_service.get_kms_config(
                organization
            )
        except KMSConfigError as e:
            raise RemoteSigningError(str(e)) from e

        # Create provider based on type
        provider = self._create_provider(
            organization.kms_provider, config, credentials
        )

        # Cache for reuse
        self._provider_cache[organization.id] = provider

        self.logger.info(
            f"Created {organization.kms_provider} provider for organization {organization.id}"
        )

        return provider

    async def get_manager(
        self,
        organization: Organization,
    ) -> KMSManager:
        """
        Get or create KMS manager for organization.

        Args:
            organization: Organization

        Returns:
            KMS manager with role enforcement

        Raises:
            RemoteSigningError: If manager creation fails
        """
        # Check cache
        if organization.id in self._manager_cache:
            return self._manager_cache[organization.id]

        # Get provider
        provider = await self.get_provider(organization)

        # Create manager
        manager = KMSManager(provider)

        # Cache for reuse
        self._manager_cache[organization.id] = manager

        return manager

    async def sign(
        self,
        organization: Organization,
        key_id: str,
        payload: bytes,
        algorithm: Optional[str] = None,
        requesting_role: CryptoRole = CryptoRole.DOCUMENT_SIGNER,
    ) -> bytes:
        """
        Sign payload using organization's remote KMS.

        Args:
            organization: Organization performing the signing
            key_id: Key identifier in the KMS
            payload: Data to sign
            algorithm: Signing algorithm (uses org config if None)
            requesting_role: Role making the signing request

        Returns:
            Signature bytes

        Raises:
            RemoteSigningError: If signing fails or tier invalid
        """
        # Fast-fail if circuit breaker is open (no I/O needed)
        cb = self._get_circuit_breaker(organization.id)
        cb.check()

        # Verify tier requires remote signing
        await self._validate_tier_requires_remote_signing(organization)

        # Get KMS manager
        manager = await self.get_manager(organization)

        # Get configured algorithm if not specified
        if not algorithm:
            config, _ = await self.kms_config_service.get_kms_config(organization)
            algorithm = config.algorithm

        # Create key identity
        key_identity = KeyIdentity(
            role=requesting_role,
            purpose=KeyPurpose.DOCUMENT_SIGNING,
            key_id=key_id,
        )

        # Perform signing with timeout and retry
        provider = organization.kms_provider or "unknown"
        sign_timer = kms_signing_duration_seconds.labels(provider=provider)
        start_time = time.monotonic()
        try:
            # Use tenacity for exponential backoff retry
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(self.max_retry_attempts),
                wait=wait_exponential(multiplier=1, min=1, max=10),
                retry=retry_if_exception_type((ConnectionError, TimeoutError)),
                reraise=True,
            ):
                with attempt:
                    # Wrap in timeout
                    signature = await asyncio.wait_for(
                        manager.sign_with_role_validation(
                            key_identity=key_identity,
                            data=payload,
                            requesting_role=requesting_role,
                            algorithm=algorithm,
                        ),
                        timeout=self.operation_timeout,
                    )

            self.logger.info(
                f"Remote signing successful for org {organization.id} "
                f"using {organization.kms_provider}"
            )

            cb.record_success()
            sign_timer.observe(time.monotonic() - start_time)
            record_operation("sign", provider, "success")
            return signature

        except asyncio.TimeoutError as e:
            cb.record_failure()
            sign_timer.observe(time.monotonic() - start_time)
            kms_errors_total.labels(error_type="timeout", provider=provider).inc()
            error_msg = (
                f"KMS signing operation timed out after {self.operation_timeout}s. "
                f"Please check your KMS connectivity."
            )
            self.logger.error(
                f"Timeout signing for org {organization.id}: {error_msg}"
            )
            raise RemoteSigningError(error_msg) from e
        except ConnectionError as e:
            cb.record_failure()
            sign_timer.observe(time.monotonic() - start_time)
            kms_errors_total.labels(error_type="connection", provider=provider).inc()
            error_msg = (
                f"Failed to connect to KMS provider {organization.kms_provider}. "
                f"Please verify your configuration and network connectivity."
            )
            self.logger.error(
                f"Connection error signing for org {organization.id}: {e}"
            )
            raise RemoteSigningError(error_msg) from e
        except Exception as e:
            cb.record_failure()
            sign_timer.observe(time.monotonic() - start_time)
            kms_errors_total.labels(error_type=type(e).__name__, provider=provider).inc()
            self.logger.error(f"Remote signing failed for org {organization.id}: {e}")
            raise RemoteSigningError(f"Remote signing failed: {e}") from e

    async def get_public_key(
        self,
        organization: Organization,
        key_id: str,
        requesting_role: CryptoRole = CryptoRole.READER,
    ) -> bytes:
        """
        Get public key from organization's KMS.

        Args:
            organization: Organization
            key_id: Key identifier
            requesting_role: Role requesting the key

        Returns:
            Public key PEM bytes

        Raises:
            RemoteSigningError: If retrieval fails
        """
        # Get KMS manager
        manager = await self.get_manager(organization)

        # Create key identity
        key_identity = KeyIdentity(
            role=CryptoRole.DOCUMENT_SIGNER,  # The key's role
            purpose=KeyPurpose.DOCUMENT_SIGNING,
            key_id=key_id,
        )

        # Get public key
        try:
            public_key_pem = await manager.get_public_key_for_verification(
                key_identity=key_identity,
                requesting_role=requesting_role,
            )

            return public_key_pem

        except Exception as e:
            self.logger.error(
                f"Failed to get public key for org {organization.id}: {e}"
            )
            raise RemoteSigningError(f"Failed to get public key: {e}") from e

    async def verify_connectivity(
        self,
        organization: Organization,
    ) -> bool:
        """
        Test KMS connectivity for organization.

        Args:
            organization: Organization

        Returns:
            True if connected successfully
        """
        try:
            provider = await self.get_provider(organization)

            # Probe connectivity with a lightweight operation
            key_identity = KeyIdentity(
                role=CryptoRole.READER,
                purpose=KeyPurpose.DOCUMENT_SIGNING,
                key_id="connectivity-test",
            )

            if isinstance(provider, AWSKMSProvider):
                await provider.key_exists(key_identity)
            elif isinstance(provider, AzureKeyVaultProvider):
                # list_keys is the lightest call that touches the vault
                await provider.list_keys()
            elif isinstance(provider, GCPCloudKMSProvider):
                await provider.list_keys()
            else:
                # SoftwareHSM / PKCS11 / Vault — provider creation
                # already validates connectivity
                pass

            return True

        except Exception as e:
            self.logger.error(f"KMS connectivity test failed: {e}")
            return False

    async def clear_cache(self, organization_id: Optional[UUID] = None) -> None:
        """
        Clear provider/manager cache.

        Args:
            organization_id: If specified, clear only this org. Otherwise clear all.
        """
        async with self._cache_lock:
            if organization_id:
                self._provider_cache.pop(organization_id, None)
                self._manager_cache.pop(organization_id, None)
                self.logger.info(f"Cleared KMS cache for organization {organization_id}")
            else:
                self._provider_cache.clear()
                self._manager_cache.clear()
                self.logger.info("Cleared all KMS provider caches")

    async def _validate_tier_requires_remote_signing(
        self,
        organization: Organization,
    ) -> None:
        """
        Validate that organization's tier requires remote signing.

        Raises:
            RemoteSigningError: If tier doesn't require remote signing
        """
        # Get active subscription
        result = await self.db.execute(
            select(Subscription)
            .where(Subscription.organization_id == organization.id)
            .where(Subscription.status == "active")
            .limit(1)
        )
        subscription = result.scalar_one_or_none()

        if not subscription:
            raise RemoteSigningError("No active subscription found")

        plan = SquarePlan(subscription.plan)
        plan_limits = PLAN_LIMITS.get(plan)

        if not plan_limits or not plan_limits.requires_remote_signing:
            raise RemoteSigningError(
                f"Tier {plan.value} should use service key vault, not remote signing. "
                f"Remote signing is only for STARTER, PROFESSIONAL, and ENTERPRISE tiers."
            )

    def _create_provider(
        self,
        provider_type: str,
        config,
        credentials: dict,
    ) -> KMSProviderInterface:
        """
        Create KMS provider instance.

        Args:
            provider_type: Provider type (aws_kms, etc.)
            config: Provider configuration
            credentials: Provider credentials

        Returns:
            KMS provider instance

        Raises:
            RemoteSigningError: If provider creation fails
        """
        try:
            if provider_type == "aws_kms":
                # Note: AWSKMSProvider expects credentials in environment or boto3 config
                # For production, we'd integrate credentials properly
                return AWSKMSProvider(
                    region_name=config.region,
                    endpoint_url=config.endpoint_url,
                )

            elif provider_type == "software_hsm":
                # For development/testing
                storage_path = config.metadata.get(
                    "storage_path", "/tmp/marty_software_hsm"
                )
                return SoftwareHSMProvider(storage_path=storage_path)

            elif provider_type == "azure_key_vault":
                return AzureKeyVaultProvider(
                    vault_url=config.endpoint_url or credentials.get("vault_url", ""),
                    tenant_id=credentials.get("tenant_id"),
                    client_id=credentials.get("client_id"),
                    client_secret=credentials.get("client_secret"),
                )

            elif provider_type == "gcp_kms":
                return GCPCloudKMSProvider(
                    project_id=credentials.get("project_id", config.metadata.get("project_id", "")),
                    location=config.region or "global",
                    key_ring=config.metadata.get("key_ring", "marty"),
                    credentials_json=credentials.get("credentials_json"),
                )

            elif provider_type == "pkcs11_hsm":
                # PKCS#11 requires python-pkcs11 package
                from marty_backend_common.crypto.kms_provider import PKCS11HSMProvider

                return PKCS11HSMProvider(
                    library_path=config.metadata["library_path"],
                    token_label=config.metadata["token_label"],
                    user_pin=credentials["user_pin"],
                )

            else:
                raise RemoteSigningError(f"Unsupported provider: {provider_type}")

        except Exception as e:
            self.logger.error(f"Failed to create {provider_type} provider: {e}")
            raise RemoteSigningError(f"Failed to create provider: {e}") from e
