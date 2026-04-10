"""
Container Registry Gating Service

Manages per-org pull credentials for the private GHCR container registry.
Credentials are issued when a license with ``registry_access=True`` is created
and revoked when the subscription is canceled.

The actual token generation is delegated to a pluggable ``RegistryTokenProvider``
so deployments can use GitHub App installation tokens, fine-grained PATs,
or a custom registry proxy.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Base, JSONBType, RegistryCredential, RegistryCredentialStatus

logger = logging.getLogger(__name__)

# Container images available per product in the registry
PRODUCT_IMAGE_MAP: dict[str, str] = {
    "csca-service": "csca-service",
    "document-signer": "document-signer",
    "document-processing": "document-processing",
    "inspection-system": "inspection-system",
    "passport-engine": "passport-engine",
    "dtc-engine": "dtc-engine",
    "mdl-engine": "mdl-engine",
    "mdoc-engine": "mdoc-engine",
    "pkd-service": "pkd-service",
    "trust-anchor": "trust-anchor",
    "ui-app": "ui-app",
    "oid4vc-api": "oid4vc-api",
    "open-badges": "open-badges",
}


@dataclass
class RegistryToken:
    """Token issued by a RegistryTokenProvider."""
    username: str
    token: str
    expires_at: datetime | None
    scopes: list[str]


class RegistryTokenProvider(ABC):
    """
    Abstract interface for generating registry pull credentials.

    Implementations could use:
    - GitHub App installation tokens (fine-grained, per-org)
    - Fine-grained PATs scoped to read:packages
    - A self-hosted registry proxy with its own auth
    """

    @abstractmethod
    async def create_token(
        self,
        org_id: UUID,
        allowed_images: list[str],
        expires_at: datetime | None = None,
    ) -> RegistryToken:
        """Generate a new pull token scoped to the given images."""

    @abstractmethod
    async def revoke_token(self, token_id: str) -> bool:
        """Revoke a previously issued token. Returns True if revoked."""


class StaticTokenProvider(RegistryTokenProvider):
    """
    Token provider that generates random bearer tokens stored in the database.

    For use with a registry proxy that validates tokens against the Marty API.
    This is the simplest deployment model — no external GitHub App needed.
    """

    def __init__(self, registry_url: str = "ghcr.io"):
        self._registry_url = registry_url

    async def create_token(
        self,
        org_id: UUID,
        allowed_images: list[str],
        expires_at: datetime | None = None,
    ) -> RegistryToken:
        token = secrets.token_urlsafe(48)
        return RegistryToken(
            username=f"marty-org-{org_id.hex[:12]}",
            token=token,
            expires_at=expires_at,
            scopes=[f"pull:{img}" for img in allowed_images],
        )

    async def revoke_token(self, token_id: str) -> bool:
        # Static tokens are revoked by removing them from the DB;
        # the proxy checks the DB on each pull.
        return True


@dataclass
class IssuedRegistryCredential:
    """Result of issuing registry credentials."""
    credential_id: UUID
    org_id: UUID
    registry_url: str
    username: str
    token: str
    allowed_images: list[str]
    expires_at: datetime | None


class RegistryGatingError(Exception):
    """Base error for registry gating operations."""


class RegistryGatingService:
    """
    Manages per-org container registry pull credentials.

    Lifecycle:
        1. License issued with registry_access=True → generate pull credentials
        2. License upgraded → regenerate with new image scope
        3. License revoked / subscription canceled → revoke credentials
    """

    def __init__(
        self,
        db: AsyncSession,
        token_provider: RegistryTokenProvider,
        registry_url: str = "ghcr.io",
    ):
        self._db = db
        self._provider = token_provider
        self._registry_url = registry_url

    def _allowed_images_for_products(
        self, entitled_products: list[str], registry_prefix: str,
    ) -> list[str]:
        """Map entitled product IDs to GHCR image paths."""
        if "*" in entitled_products:
            return [
                f"{registry_prefix}/{img}" for img in PRODUCT_IMAGE_MAP.values()
            ]
        images = []
        for product in entitled_products:
            image_name = PRODUCT_IMAGE_MAP.get(product)
            if image_name:
                images.append(f"{registry_prefix}/{image_name}")
        return sorted(set(images))

    async def issue_credentials(
        self,
        org_id: UUID,
        license_jti: str,
        entitled_products: list[str],
        *,
        registry_prefix: str = "",
        expires_at: datetime | None = None,
    ) -> IssuedRegistryCredential:
        """
        Issue registry pull credentials for an organization.

        Automatically revokes any existing credentials for the same org.
        """
        # Revoke existing credentials
        await self.revoke_org_credentials(org_id, "Superseded by new credentials")

        allowed_images = self._allowed_images_for_products(
            entitled_products, registry_prefix,
        )

        reg_token = await self._provider.create_token(
            org_id, allowed_images, expires_at,
        )

        # Store credential record (token stored as hash for security)
        token_hash = hashlib.sha256(reg_token.token.encode()).hexdigest()
        credential = RegistryCredential(
            id=uuid4(),
            org_id=org_id,
            license_jti=license_jti,
            registry_url=self._registry_url,
            username=reg_token.username,
            token_hash=token_hash,
            allowed_images=allowed_images,
            status=RegistryCredentialStatus.ACTIVE.value,
            issued_at=datetime.now(timezone.utc),
            expires_at=reg_token.expires_at,
        )

        self._db.add(credential)
        await self._db.commit()

        logger.info(
            "Issued registry credentials %s for org %s (%d images)",
            credential.id, org_id, len(allowed_images),
        )

        return IssuedRegistryCredential(
            credential_id=credential.id,
            org_id=org_id,
            registry_url=self._registry_url,
            username=reg_token.username,
            token=reg_token.token,
            allowed_images=allowed_images,
            expires_at=reg_token.expires_at,
        )

    async def revoke_org_credentials(
        self, org_id: UUID, reason: str = "Subscription canceled",
    ) -> int:
        """Revoke all active registry credentials for an organization."""
        now = datetime.now(timezone.utc)
        result = await self._db.execute(
            update(RegistryCredential)
            .where(
                RegistryCredential.org_id == org_id,
                RegistryCredential.status == RegistryCredentialStatus.ACTIVE.value,
            )
            .values(
                status=RegistryCredentialStatus.REVOKED.value,
                revoked_at=now,
                revocation_reason=reason,
            )
        )
        await self._db.commit()
        count = result.rowcount
        if count:
            logger.info("Revoked %d registry credential(s) for org %s", count, org_id)
        return count

    async def get_org_credential(self, org_id: UUID) -> RegistryCredential | None:
        """Get the current active registry credential for an org."""
        result = await self._db.execute(
            select(RegistryCredential).where(
                RegistryCredential.org_id == org_id,
                RegistryCredential.status == RegistryCredentialStatus.ACTIVE.value,
            )
        )
        return result.scalar_one_or_none()

    async def validate_token(self, username: str, token: str) -> dict | None:
        """
        Validate a pull token presented by a registry proxy.

        Returns credential info if valid, None if invalid/revoked/expired.
        """
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        result = await self._db.execute(
            select(RegistryCredential).where(
                RegistryCredential.username == username,
                RegistryCredential.token_hash == token_hash,
                RegistryCredential.status == RegistryCredentialStatus.ACTIVE.value,
            )
        )
        credential = result.scalar_one_or_none()
        if credential is None:
            return None

        # Check expiry
        if credential.expires_at and credential.expires_at < datetime.now(timezone.utc):
            credential.status = RegistryCredentialStatus.EXPIRED.value
            await self._db.commit()
            return None

        return {
            "org_id": str(credential.org_id),
            "allowed_images": credential.allowed_images,
            "expires_at": credential.expires_at.isoformat() if credential.expires_at else None,
        }
