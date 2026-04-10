"""
REST API endpoints for organization KMS configuration.

Provides endpoints for configuring and managing customer-provided KMS/HSM
for remote signing operations (production tiers only).

Security:
- Authentication via X-User-ID header
- Authorization via organization membership verification
- Rate limiting to prevent abuse
- Audit logging for compliance
- Input validation against SSRF and injection attacks
"""

import ipaddress
import logging
import os
import re
import socket
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any, Literal
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, validator
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.subscription.audit import configure_audit_logging
from src.subscription.auth import AuthenticatedUser, get_authenticated_user
from src.subscription.kms_config_service import (
    KMSConfigError,
    KMSConfigService,
    KMSProviderConfig,
)
from src.subscription.models import Organization
from src.subscription.remote_signing_service import (
    RemoteSigningError,
    RemoteSigningService,
)
from src.subscription.metrics import record_auth_failure, record_operation

logger = logging.getLogger(__name__)

# Rate limiter configuration
limiter = Limiter(key_func=get_remote_address)

# Audit logger — structured JSON via configure_audit_logging()
audit_logger = configure_audit_logging()

# Router definition
kms_router = APIRouter(
    prefix="/v1/subscriptions/organizations",
    tags=["KMS Configuration"],
)


# =========================================================
# Request/Response Models
# =========================================================


class KMSConfigRequest(BaseModel):
    """Request model for KMS configuration with strict validation."""

    provider: Literal[
        "aws_kms",
        "azure_key_vault",
        "gcp_kms",
        "hashicorp_vault",
        "pkcs11_hsm",
        "software_hsm",
    ] = Field(..., description="KMS provider (strictly validated)")
    
    credentials: dict[str, Any] = Field(
        ...,
        description="Provider credentials (will be encrypted)",
        max_length=10240,  # Max 10KB for credentials
    )
    
    config: dict[str, Any] = Field(
        ...,
        description="Provider configuration",
        max_length=10240,  # Max 10KB for config
    )

    @validator("config")
    def validate_config(cls, v, values):
        """Validate provider-specific configuration and prevent SSRF."""
        provider = values.get("provider")

        # Validate endpoint URL if present (SSRF protection)
        if "endpoint_url" in v:
            endpoint = v["endpoint_url"]
            
            # Parse URL
            try:
                parsed = urlparse(endpoint)
            except Exception as e:
                raise ValueError(f"Invalid endpoint URL: {e}")
            
            # Block private IP addresses (SSRF protection)
            if parsed.hostname:
                try:
                    ip = ipaddress.ip_address(parsed.hostname)
                    if ip.is_private or ip.is_loopback or ip.is_link_local:
                        raise ValueError(
                            "Endpoint URL cannot point to private/loopback IP addresses"
                        )
                except ValueError as e:
                    # Re-raise our own SSRF error
                    if "point to private" in str(e):
                        raise
                    # Not an IP literal — resolve hostname and check all results
                    try:
                        results = socket.getaddrinfo(
                            parsed.hostname, None, proto=socket.IPPROTO_TCP
                        )
                        for family, _, _, _, sockaddr in results:
                            resolved_ip = ipaddress.ip_address(sockaddr[0])
                            if (
                                resolved_ip.is_private
                                or resolved_ip.is_loopback
                                or resolved_ip.is_link_local
                            ):
                                raise ValueError(
                                    "Endpoint URL hostname resolves to a "
                                    "private/loopback IP address"
                                )
                    except socket.gaierror:
                        raise ValueError(
                            "Endpoint URL hostname cannot be resolved"
                        )
            
            # Require HTTPS for external endpoints (unless localhost for dev)
            if parsed.scheme not in ["https", "http"]:
                raise ValueError("Endpoint URL must use HTTP or HTTPS")
            
            # In production, require HTTPS
            if os.getenv("ENVIRONMENT", "development") == "production":
                if parsed.scheme != "https":
                    raise ValueError("Endpoint URL must use HTTPS in production")

        # Validate key_id format and size
        if "key_id" in v:
            key_id = v["key_id"]
            
            # Size limit (prevent buffer overflows)
            if len(key_id) > 1024:
                raise ValueError("Key ID exceeds maximum length of 1024 characters")
            
            # Provider-specific validation
            if provider == "aws_kms":
                # AWS KMS ARN or key ID format
                aws_pattern = r"^(arn:aws:kms:[a-z0-9-]+:\d{12}:key/)?[a-f0-9-]+$"
                if not re.match(aws_pattern, key_id, re.IGNORECASE):
                    raise ValueError(
                        "Invalid AWS KMS key ID format. "
                        "Expected: key-id or arn:aws:kms:region:account:key/key-id"
                    )
            elif provider == "azure_key_vault":
                # Azure Key Vault key URL format
                azure_pattern = r"^https://[a-z0-9-]+\.vault\.azure\.net/keys/[a-zA-Z0-9-]+(/[a-f0-9]+)?$"
                if not re.match(azure_pattern, key_id, re.IGNORECASE):
                    raise ValueError(
                        "Invalid Azure Key Vault key identifier format"
                    )

        # Validate region format
        if "region" in v:
            region = v["region"]
            if len(region) > 50:
                raise ValueError("Region name exceeds maximum length")
            # Simple alphanumeric plus hyphens
            if not re.match(r"^[a-z0-9-]+$", region, re.IGNORECASE):
                raise ValueError("Invalid region format")

        return v
    
    class Config:
        # Strict mode - reject extra fields
        extra = "forbid"


class KMSConfigResponse(BaseModel):
    """Response model for KMS configuration (credentials redacted)."""

    provider: str
    region: str | None = None
    algorithm: str = "ES256"
    endpoint_url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    configured_at: str | None = None


class KMSConnectivityResponse(BaseModel):
    """Response model for KMS connectivity test."""

    connected: bool
    provider: str | None = None
    error: str | None = None
    note: str | None = None


class SigningTestRequest(BaseModel):
    """Request model for testing remote signing."""

    key_id: str = Field(..., description="Key identifier in the KMS")
    test_payload: str = Field(
        default="test signing operation", description="Test data to sign"
    )
    algorithm: str = Field(default="ES256", description="Signing algorithm")


class SigningTestResponse(BaseModel):
    """Response model for signing test."""

    success: bool
    signature: str | None = None
    error: str | None = None


# =========================================================
# Dependency Injection
# =========================================================

# Global database engine (initialized at app startup)
_db_engine = None
_db_session_factory = None


def configure_database(database_url: str | None = None):
    """Configure database connection for KMS router.
    
    Call this during application startup:
        from src.subscription.kms_router import configure_database
        configure_database("postgresql+asyncpg://user:pass@host:port/db")
    """
    global _db_engine, _db_session_factory
    
    url = database_url or os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://marty:marty@localhost:5432/marty"
    )
    
    _db_engine = create_async_engine(
        url,
        echo=False,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,  # Verify connections before using
    )
    
    _db_session_factory = sessionmaker(
        _db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    logger.info("KMS router database configured")


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Get database session with proper transaction handling."""
    if _db_session_factory is None:
        # Try to auto-configure from environment
        configure_database()
    
    async with _db_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# Re-export for backward compatibility; prefer get_authenticated_user.
get_current_user = get_authenticated_user


async def get_organization(
    org_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    user: AuthenticatedUser = Depends(get_authenticated_user),
) -> Organization:
    """Get organization by ID with authorization check.

    Verifies:
    1. User is authenticated (JWT or trusted proxy).
    2. JWT ``org_ids`` claim (if present) includes this org.
    3. Organization exists in the database.
    """
    # ── Org-level authorization from JWT claims ──
    if user.org_ids is not None:
        if str(org_id) not in user.org_ids:
            audit_logger.warning(
                "Org access denied",
                extra={"action": "org_access_denied", "user_id": user.user_id,
                       "org_id": str(org_id), "allowed_orgs": user.org_ids},
            )
            record_auth_failure("org_access_denied")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this organization",
            )

    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()

    if not org:
        audit_logger.warning(
            "Organization not found",
            extra={"action": "org_not_found", "org_id": str(org_id),
                   "user_id": user.user_id},
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization {org_id} not found",
        )

    audit_logger.info(
        "Organization access granted",
        extra={"action": "org_access_granted", "user_id": user.user_id,
               "org_id": str(org_id), "org_name": org.name},
    )

    return org


async def get_kms_config_service(
    db: AsyncSession = Depends(get_db_session),
) -> KMSConfigService:
    """Get KMS configuration service."""
    return KMSConfigService(db)


async def get_remote_signing_service(
    db: AsyncSession = Depends(get_db_session),
    kms_service: KMSConfigService = Depends(get_kms_config_service),
) -> RemoteSigningService:
    """Get remote signing service."""
    return RemoteSigningService(db, kms_service)


# =========================================================
# Endpoints
# =========================================================


@kms_router.post(
    "/{org_id}/kms/configure",
    response_model=KMSConfigResponse,
    status_code=status.HTTP_200_OK,
    summary="Configure Organization KMS",
    description="""
    Configure KMS/HSM for remote signing operations.
    
    **Required for production tiers:** STARTER, PROFESSIONAL, ENTERPRISE
    
    **Supported providers:**
    - `aws_kms` - AWS Key Management Service
    - `azure_key_vault` - Azure Key Vault
    - `gcp_kms` - Google Cloud KMS
    - `hashicorp_vault` - HashiCorp Vault Transit
    - `pkcs11_hsm` - PKCS#11 Hardware Security Module
    - `software_hsm` - Software HSM (development/testing only)
    
    **Security:** Credentials are encrypted at rest using Fernet encryption.
    
    **Rate Limit:** 10 configuration changes per hour per IP address.
    """,
)
@limiter.limit("10/hour")  # Rate limit: 10 config changes per hour
async def configure_organization_kms(
    request: Request,  # Required for rate limiting
    org_id: UUID,
    config_request: KMSConfigRequest,
    org: Organization = Depends(get_organization),  # Includes auth check
    kms_service: KMSConfigService = Depends(get_kms_config_service),
    user: AuthenticatedUser = Depends(get_authenticated_user),
) -> KMSConfigResponse:
    """
    Configure KMS for organization.

    Validates subscription tier, encrypts credentials, and stores configuration.
    """
    user_id = user.user_id
    try:
        # Parse config into KMSProviderConfig
        provider_config = KMSProviderConfig(
            provider=config_request.provider,
            region=config_request.config.get("region"),
            key_id=config_request.config.get("key_id"),
            endpoint_url=config_request.config.get("endpoint_url"),
            algorithm=config_request.config.get("algorithm", "ES256"),
            metadata=config_request.config.get("metadata", {}),
        )

        # Configure KMS
        await kms_service.configure_kms(
            organization=org,
            provider=config_request.provider,
            credentials=config_request.credentials,
            config=provider_config,
        )

        # Return safe config (credentials redacted)
        safe_config = await kms_service.get_kms_config_safe(org)

        # Audit log successful configuration
        audit_logger.info(
            "KMS configured",
            extra={"action": "kms_configured", "user_id": user_id,
                   "org_id": str(org_id), "org_name": org.name,
                   "provider": config_request.provider,
                   "region": provider_config.region},
        )
        record_operation("configure", config_request.provider, "success")
        logger.info(
            f"Configured {config_request.provider} for organization {org_id}"
        )

        return KMSConfigResponse(
            provider=safe_config["provider"],
            region=safe_config.get("region"),
            algorithm=safe_config.get("algorithm", "ES256"),
            endpoint_url=safe_config.get("endpoint_url"),
            metadata=safe_config.get("metadata", {}),
            configured_at=datetime.now(timezone.utc).isoformat(),
        )

    except KMSConfigError as e:
        # Audit log failed configuration
        audit_logger.warning(
            "KMS configuration failed",
            extra={"action": "kms_configure_failed", "user_id": user_id,
                   "org_id": str(org_id),
                   "provider": config_request.provider,
                   "error": str(e)},
        )
        record_operation("configure", config_request.provider, "error")
        logger.error(f"KMS configuration failed for org {org_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        # Audit log unexpected error
        audit_logger.error(
            "KMS configuration error",
            extra={"action": "kms_configure_error", "user_id": user_id,
                   "org_id": str(org_id),
                   "provider": config_request.provider,
                   "error": str(e)},
            exc_info=True,
        )
        logger.exception(f"Unexpected error configuring KMS for org {org_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error configuring KMS",
        )


@kms_router.get(
    "/{org_id}/kms",
    response_model=KMSConfigResponse,
    summary="Get Organization KMS Configuration",
    description="Retrieve current KMS configuration (credentials redacted for security).",
)
@limiter.limit("100/hour")  # Rate limit: 100 reads per hour
async def get_organization_kms_config(
    request: Request,  # Required for rate limiting
    org_id: UUID,
    org: Organization = Depends(get_organization),  # Includes auth check
    kms_service: KMSConfigService = Depends(get_kms_config_service),
    user: AuthenticatedUser = Depends(get_authenticated_user),
) -> KMSConfigResponse:
    """Get organization's KMS configuration with credentials redacted."""
    user_id = user.user_id
    try:
        safe_config = await kms_service.get_kms_config_safe(org)

        if safe_config is None:
            audit_logger.info(
                "KMS config not found",
                extra={"action": "kms_config_not_found", "user_id": user_id,
                       "org_id": str(org_id)},
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="KMS not configured for this organization",
            )
        
        # Audit log successful retrieval
        audit_logger.info(
            "KMS config retrieved",
            extra={"action": "kms_config_read", "user_id": user_id,
                   "org_id": str(org_id),
                   "provider": safe_config["provider"]},
        )

        return KMSConfigResponse(
            provider=safe_config["provider"],
            region=safe_config.get("region"),
            algorithm=safe_config.get("algorithm", "ES256"),
            endpoint_url=safe_config.get("endpoint_url"),
            metadata=safe_config.get("metadata", {}),
        )

    except HTTPException:
        raise
    except Exception as e:
        audit_logger.error(
            "KMS config retrieval error",
            extra={"action": "kms_config_read_error", "user_id": user_id,
                   "org_id": str(org_id), "error": str(e)},
            exc_info=True,
        )
        logger.exception(f"Error retrieving KMS config for org {org_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error retrieving KMS configuration",
        )


@kms_router.delete(
    "/{org_id}/kms",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Organization KMS Configuration",
    description="Remove KMS configuration. WARNING: This will disable remote signing.",
)
@limiter.limit("10/hour")  # Rate limit: 10 deletions per hour
async def delete_organization_kms_config(
    request: Request,  # Required for rate limiting
    org_id: UUID,
    org: Organization = Depends(get_organization),  # Includes auth check
    kms_service: KMSConfigService = Depends(get_kms_config_service),
    remote_signing_service: RemoteSigningService = Depends(
        get_remote_signing_service
    ),
    user: AuthenticatedUser = Depends(get_authenticated_user),
) -> None:
    """Delete organization's KMS configuration."""
    user_id = user.user_id
    try:
        # Get provider name for audit log before deletion
        provider_name = org.kms_provider or "none"
        
        await kms_service.delete_kms_config(org)
        
        # Clear provider cache
        await remote_signing_service.clear_cache(org_id)
        
        # Audit log successful deletion
        audit_logger.warning(
            "KMS config deleted",
            extra={"action": "kms_config_deleted", "user_id": user_id,
                   "org_id": str(org_id), "org_name": org.name,
                   "provider": provider_name},
        )
        record_operation("delete", provider_name, "success")
        logger.info(f"Deleted KMS configuration for organization {org_id}")

    except Exception as e:
        audit_logger.error(
            "KMS deletion error",
            extra={"action": "kms_delete_error", "user_id": user_id,
                   "org_id": str(org_id), "error": str(e)},
            exc_info=True,
        )
        logger.exception(f"Error deleting KMS config for org {org_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error deleting KMS configuration",
        )


@kms_router.post(
    "/{org_id}/kms/test-connectivity",
    response_model=KMSConnectivityResponse,
    summary="Test KMS Connectivity",
    description="""
    Test connectivity to the configured KMS provider.
    
    Validates:
    - Network connectivity
    - Authentication credentials
    - Key access permissions
    
    **Rate Limit:** 20 connectivity tests per hour.
    """,
)
@limiter.limit("20/hour")  # Rate limit: 20 tests per hour
async def test_kms_connectivity(
    request: Request,  # Required for rate limiting
    org_id: UUID,
    org: Organization = Depends(get_organization),  # Includes auth check
    kms_service: KMSConfigService = Depends(get_kms_config_service),
    user: AuthenticatedUser = Depends(get_authenticated_user),
) -> KMSConnectivityResponse:
    """Test connectivity to organization's KMS."""
    user_id = user.user_id
    try:
        result = await kms_service.test_kms_connectivity(org)

        # Audit log test result
        audit_logger.info(
            "KMS connectivity test",
            extra={"action": "kms_connectivity_test", "user_id": user_id,
                   "org_id": str(org_id), "provider": org.kms_provider,
                   "result": "success" if result.get("connected") else "failed"},
        )

        return KMSConnectivityResponse(
            connected=result.get("connected", False),
            provider=result.get("provider"),
            error=result.get("error"),
            note=result.get("note"),
        )

    except KMSConfigError as e:
        audit_logger.warning(
            "KMS connectivity test failed",
            extra={"action": "kms_connectivity_failed", "user_id": user_id,
                   "org_id": str(org_id), "error": str(e)},
        )
        logger.error(f"KMS connectivity test failed for org {org_id}: {e}")
        return KMSConnectivityResponse(
            connected=False,
            error=str(e),
        )
    except Exception as e:
        audit_logger.error(
            "KMS connectivity test error",
            extra={"action": "kms_connectivity_error", "user_id": user_id,
                   "org_id": str(org_id), "error": str(e)},
            exc_info=True,
        )
        logger.exception(f"Error testing KMS connectivity for org {org_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error testing KMS connectivity",
        )


@kms_router.post(
    "/{org_id}/kms/test-signing",
    response_model=SigningTestResponse,
    summary="Test Remote Signing",
    description="""
    Test remote signing operation with configured KMS.
    
    Performs an actual signing operation to verify:
    - KMS connectivity
    - Key access permissions
    - Signing algorithm support
    
    **Note:** This uses the organization's configured KMS and will count toward KMS usage.
    **Rate Limit:** 50 signing tests per hour.
    """,
)
@limiter.limit("50/hour")  # Rate limit: 50 tests per hour
async def test_remote_signing(
    request: Request,  # Required for rate limiting
    org_id: UUID,
    test_request: SigningTestRequest,
    org: Organization = Depends(get_organization),  # Includes auth check
    remote_signing_service: RemoteSigningService = Depends(
        get_remote_signing_service
    ),
    user: AuthenticatedUser = Depends(get_authenticated_user),
) -> SigningTestResponse:
    """Test remote signing operation."""
    user_id = user.user_id
    try:
        # Sign test payload
        test_payload_bytes = test_request.test_payload.encode()

        signature = await remote_signing_service.sign(
            organization=org,
            key_id=test_request.key_id,
            payload=test_payload_bytes,
            algorithm=test_request.algorithm,
        )

        # Convert signature to hex for response
        signature_hex = signature.hex()

        # Audit log successful test
        audit_logger.info(
            "KMS signing test successful",
            extra={"action": "kms_sign_test_success", "user_id": user_id,
                   "org_id": str(org_id), "provider": org.kms_provider,
                   "key_id": test_request.key_id},
        )
        logger.info(
            f"Remote signing test successful for org {org_id} with key {test_request.key_id}"
        )

        return SigningTestResponse(
            success=True,
            signature=signature_hex,
        )

    except RemoteSigningError as e:
        audit_logger.warning(
            "KMS signing test failed",
            extra={"action": "kms_sign_test_failed", "user_id": user_id,
                   "org_id": str(org_id), "key_id": test_request.key_id,
                   "error": str(e)},
        )
        logger.error(f"Remote signing test failed for org {org_id}: {e}")
        return SigningTestResponse(
            success=False,
            error=str(e),
        )
    except Exception as e:
        audit_logger.error(
            "KMS signing test error",
            extra={"action": "kms_sign_test_error", "user_id": user_id,
                   "org_id": str(org_id), "key_id": test_request.key_id,
                   "error": str(e)},
            exc_info=True,
        )
        logger.exception(f"Unexpected error testing remote signing for org {org_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error testing remote signing",
        )
