"""
Authentication and authorization dependencies for subscription endpoints.

Supports two modes:
- JWT Bearer token validation (default, production)
- Trusted proxy headers (when AUTH_TRUST_PROXY_HEADERS=true, behind API gateway)

JWT claims expected:
- sub: user ID
- org_ids: list of organization UUIDs the user has access to
- org_id: single organization UUID (backward compat)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

import jwt as pyjwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .audit import configure_audit_logging

logger = logging.getLogger(__name__)
audit_logger = configure_audit_logging()

_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class AuthenticatedUser:
    """Authenticated user extracted from JWT or proxy headers."""

    user_id: str
    org_ids: list[str] | None = field(default=None)
    """Organization IDs the user is authorized for. None = unrestricted."""


def _trust_proxy_headers() -> bool:
    return os.getenv("AUTH_TRUST_PROXY_HEADERS", "false").lower() == "true"


def _jwt_secret() -> str | None:
    return os.getenv("KMS_JWT_SECRET") or os.getenv("JWT_SECRET")


def _jwt_algorithm() -> str:
    return os.getenv("KMS_JWT_ALGORITHM", "HS256")


async def get_authenticated_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    x_user_id: str | None = Header(None, alias="X-User-ID"),
    x_org_ids: str | None = Header(None, alias="X-Org-IDs"),
) -> AuthenticatedUser:
    """Authenticate user via JWT Bearer token or trusted proxy headers.

    Priority:
    1. JWT Bearer token — always accepted when present.
    2. Proxy headers (X-User-ID, X-Org-IDs) — only when
       AUTH_TRUST_PROXY_HEADERS=true.

    Raises:
        HTTPException 401: No valid credentials provided.
        HTTPException 503: JWT secret not configured (token present but
                           server cannot validate).
    """
    # ── Mode 1: JWT Bearer token ──
    if credentials:
        secret = _jwt_secret()
        if not secret:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service not configured (JWT_SECRET missing)",
            )
        try:
            claims = pyjwt.decode(
                credentials.credentials,
                secret,
                algorithms=[_jwt_algorithm()],
            )
        except pyjwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except pyjwt.InvalidTokenError as exc:
            audit_logger.warning(
                "JWT validation failed",
                extra={"action": "jwt_validation_failed", "error": str(exc)},
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user_id = claims.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing 'sub' claim",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Extract org access from claims
        org_ids: list[str] | None = claims.get("org_ids")
        single_org = claims.get("org_id")
        if org_ids is None and single_org:
            org_ids = [single_org]

        return AuthenticatedUser(user_id=str(user_id), org_ids=org_ids)

    # ── Mode 2: Trusted proxy headers (behind API gateway) ──
    if _trust_proxy_headers() and x_user_id:
        org_ids = None
        if x_org_ids:
            org_ids = [oid.strip() for oid in x_org_ids.split(",") if oid.strip()]
        return AuthenticatedUser(user_id=x_user_id, org_ids=org_ids)

    # ── No credentials ──
    audit_logger.warning(
        "Authentication failed: no credentials provided",
        extra={"action": "auth_no_credentials"},
    )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )
