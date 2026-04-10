"""Signing Key Management API Router (K25).

REST endpoints for registering, listing, rotating, and revoking
signing keys used by credential templates.  Bridges the UI's
``signingKeysApi.js`` with the ``CredentialKeyManager`` / OpenBao backend.

Endpoints (prefix ``/v1/signing-keys``):

  GET    /                  – List signing keys
  POST   /                  – Register / generate a new signing key
  GET    /{key_id}          – Get key details
  PATCH  /{key_id}          – Update key metadata
  POST   /{key_id}/rotate   – Rotate key
  DELETE /{key_id}          – Delete key
  GET    /config            – Get KMS backend configuration
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/signing-keys", tags=["Signing Keys"])

# ---------------------------------------------------------------------------
# API-key authentication (matches PKD service pattern)
# ---------------------------------------------------------------------------

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def _verify_api_key(api_key: str = Depends(_api_key_header)) -> str:
    """Verify X-API-Key header.  Returns the validated key string."""
    import hmac as _hmac
    if not api_key:
        raise HTTPException(401, "X-API-Key header is missing")
    expected = os.getenv("SIGNING_KEYS_API_KEY", "")
    if not expected:
        raise HTTPException(503, "SIGNING_KEYS_API_KEY not configured on server")
    if not _hmac.compare_digest(api_key, expected):
        raise HTTPException(401, "Invalid API Key")
    return api_key


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class KeyType(str, Enum):
    LOCAL = "local"
    HSM = "hsm"
    VAULT = "vault"


class KeyStatus(str, Enum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    REVOKED = "revoked"


class CreateSigningKeyRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    algorithm: str = Field("ES256", description="ES256, ES384, RS256, EdDSA, …")
    key_type: KeyType = KeyType.VAULT
    public_key: str | None = Field(None, description="PEM public key (for external BYOK)")
    vault_config: dict[str, Any] | None = None
    hsm_config: dict[str, Any] | None = None


class UpdateSigningKeyRequest(BaseModel):
    name: str | None = None
    status: KeyStatus | None = None


class RotateKeyRequest(BaseModel):
    immediate: bool = False


class SigningKeyResponse(BaseModel):
    id: str
    name: str
    algorithm: str
    key_type: str
    status: str
    public_key_pem: str | None = None
    created_at: str
    rotated_at: str | None = None


# ---------------------------------------------------------------------------
# Dependency – resolve CredentialKeyManager (or None)
# ---------------------------------------------------------------------------


async def _get_kms():
    """Lazy import to avoid hard dep at module load time."""
    from marty_backend_common.crypto.kms_factory import create_credential_key_manager

    return await create_credential_key_manager()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=list[SigningKeyResponse])
async def list_signing_keys(
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    _key: str = Depends(_verify_api_key),
):
    """List signing keys visible to the current organization."""
    logger.info("list_signing_keys called (status=%s, limit=%d, offset=%d)", status, limit, offset)
    ckm = await _get_kms()
    if ckm is None:
        return []

    from marty_backend_common.crypto.role_separation import CryptoRole

    keys = await ckm.list_credential_keys(role=CryptoRole.DSC)
    out = []
    for k in keys:
        key_status = "active"
        if k.is_expired:
            key_status = "expired"
        if status and key_status != status:
            continue
        out.append(
            SigningKeyResponse(
                id=k.key_id,
                name=k.key_id,
                algorithm="ES256",
                key_type="vault",
                status=key_status,
                public_key_pem=k.public_key_pem.decode() if k.public_key_pem else None,
                created_at=k.created_at.isoformat(),
            )
        )
    return out[offset : offset + limit]


@router.post("", response_model=SigningKeyResponse, status_code=201)
async def create_signing_key(
    body: CreateSigningKeyRequest,
    _key: str = Depends(_verify_api_key),
):
    """Register or generate a new signing key."""
    logger.info("create_signing_key: name=%s algorithm=%s type=%s", body.name, body.algorithm, body.key_type.value)
    ckm = await _get_kms()
    if ckm is None:
        raise HTTPException(503, "KMS backend not configured")

    info = await ckm.generate_issuer_key(
        issuer_id="default",
        key_id=body.name,
        algorithm=body.algorithm,
    )

    return SigningKeyResponse(
        id=info.key_id,
        name=body.name,
        algorithm=body.algorithm,
        key_type=body.key_type.value,
        status="active",
        public_key_pem=info.public_key_pem.decode() if info.public_key_pem else None,
        created_at=info.created_at.isoformat(),
    )


@router.get("/{key_id}", response_model=SigningKeyResponse)
async def get_signing_key(
    key_id: str,
    _key: str = Depends(_verify_api_key),
):
    """Get signing key details."""
    logger.info("get_signing_key: key_id=%s", key_id)
    ckm = await _get_kms()
    if ckm is None:
        raise HTTPException(503, "KMS backend not configured")

    info = await ckm.get_issuer_key(issuer_id="default", key_id=key_id)
    if info is None:
        raise HTTPException(404, f"Key {key_id} not found")

    return SigningKeyResponse(
        id=info.key_id,
        name=info.key_id,
        algorithm="ES256",
        key_type="vault",
        status="expired" if info.is_expired else "active",
        public_key_pem=info.public_key_pem.decode() if info.public_key_pem else None,
        created_at=info.created_at.isoformat(),
    )


@router.patch("/{key_id}", response_model=SigningKeyResponse)
async def update_signing_key(
    key_id: str,
    body: UpdateSigningKeyRequest,
    _key: str = Depends(_verify_api_key),
):
    """Update signing key metadata or status."""
    logger.info("update_signing_key: key_id=%s name=%s status=%s", key_id, body.name, body.status)
    ckm = await _get_kms()
    if ckm is None:
        raise HTTPException(503, "KMS backend not configured")

    info = await ckm.get_issuer_key(issuer_id="default", key_id=key_id)
    if info is None:
        raise HTTPException(404, f"Key {key_id} not found")

    if body.status == KeyStatus.REVOKED:
        logger.warning("REVOKE signing key: key_id=%s — deleting from KMS", key_id)
        await ckm.delete_credential_key(info.key_id)

    return SigningKeyResponse(
        id=info.key_id,
        name=body.name or info.key_id,
        algorithm="ES256",
        key_type="vault",
        status=body.status.value if body.status else "active",
        public_key_pem=info.public_key_pem.decode() if info.public_key_pem else None,
        created_at=info.created_at.isoformat(),
    )


@router.post("/{key_id}/rotate", response_model=SigningKeyResponse)
async def rotate_signing_key(
    key_id: str,
    body: RotateKeyRequest,
    _key: str = Depends(_verify_api_key),
):
    """Rotate a signing key (creates new version, optionally deprecates old)."""
    logger.info("rotate_signing_key: key_id=%s immediate=%s", key_id, body.immediate)
    ckm = await _get_kms()
    if ckm is None:
        raise HTTPException(503, "KMS backend not configured")

    info = await ckm.rotate_issuer_key(issuer_id="default", key_id=key_id)

    return SigningKeyResponse(
        id=info.key_id,
        name=info.key_id,
        algorithm="ES256",
        key_type="vault",
        status="active",
        public_key_pem=info.public_key_pem.decode() if info.public_key_pem else None,
        created_at=info.created_at.isoformat(),
        rotated_at=datetime.now(timezone.utc).isoformat(),
    )


@router.delete("/{key_id}", status_code=204)
async def delete_signing_key(
    key_id: str,
    _key: str = Depends(_verify_api_key),
):
    """Delete a signing key."""
    logger.warning("DELETE signing key: key_id=%s", key_id)
    ckm = await _get_kms()
    if ckm is None:
        raise HTTPException(503, "KMS backend not configured")

    deleted = await ckm.delete_credential_key(
        f"cred:issuer:default:{key_id}"
    )
    if not deleted:
        raise HTTPException(404, f"Key {key_id} not found")


@router.get("/config", response_model=dict)
async def get_key_management_config(
    _key: str = Depends(_verify_api_key),
):
    """Get KMS backend configuration (non-sensitive)."""
    import os

    logger.info("get_key_management_config called")

    addr = os.getenv("OPENBAO_ADDR") or os.getenv("BAO_ADDR")
    return {
        "vault_enabled": addr is not None,
        "vault_address": addr or "",
        "hsm_enabled": False,
    }
