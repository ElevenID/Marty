"""Helpers for issuing SD-JWT based verifiable credentials."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import jwt

# Use Rust crypto_bridge for certificate operations
from marty_plugin.common.crypto_bridge import Certificate, Encoding
# Keep serialization for private key loading (PyJWT needs cryptography key objects)
from cryptography.hazmat.primitives import serialization

from marty_plugin.common.infrastructure import KeyVaultClient


def _b64url_encode(data: bytes) -> str:
    """Return base64url encoded data without padding."""
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


@dataclass(slots=True)
class SdJwtDisclosure:
    """Representation of a single selective disclosure claim."""

    salt: str
    name: str
    value: Any
    encoded: str
    digest: str

    @classmethod
    def build(cls, name: str, value: Any, *, salt_bytes: bytes | None = None) -> SdJwtDisclosure:
        salt_bytes = salt_bytes or secrets.token_bytes(16)
        salt = _b64url_encode(salt_bytes)
        disclosure_object = [salt, name, value]
        disclosure_json = json.dumps(disclosure_object, separators=(",", ":"), ensure_ascii=False)
        encoded = _b64url_encode(disclosure_json.encode("utf-8"))
        digest_bytes = hashlib.sha256(disclosure_json.encode("utf-8")).digest()
        digest = _b64url_encode(digest_bytes)
        return cls(salt=salt, name=name, value=value, encoded=encoded, digest=digest)


@dataclass(slots=True)
class SdJwtConfig:
    """Runtime configuration for SD-JWT issuance."""

    issuer: str
    signing_key_id: str
    signing_algorithm: str = "ES256"
    kid: str | None = None
    default_expiry: timedelta = timedelta(hours=12)
    audience: str | None = None


@dataclass(slots=True)
class SdJwtIssuanceInput:
    """Input payload required to mint an SD-JWT VC."""

    subject_id: str
    credential_type: str
    base_claims: dict[str, Any]
    selective_disclosures: dict[str, Any]
    audience: str | None = None
    nonce: str | None = None
    expires_at: datetime | None = None
    additional_payload: dict[str, Any] | None = None


@dataclass(slots=True)
class SdJwtIssuanceResult:
    """Issued SD-JWT artefacts."""

    credential_id: str
    token: str
    disclosures: list[str]
    issuer: str
    subject_id: str
    credential_type: str
    audience: str | None
    expires_at: datetime
    issued_at: datetime
    payload: dict[str, Any]
    disclosure_objects: list[SdJwtDisclosure]


class SdJwtIssuer:
    """Mint SD-JWT verifiable credentials using signing keys from the key vault."""

    def __init__(
        self,
        key_vault: KeyVaultClient,
        certificate_chain_provider: Callable[[], list[Certificate]],
        config: SdJwtConfig,
    ) -> None:
        self._key_vault = key_vault
        self._certificate_chain_provider = certificate_chain_provider
        self._config = config

    async def issue(self, issuance: SdJwtIssuanceInput) -> SdJwtIssuanceResult:
        now = datetime.now(timezone.utc)
        expires_at = issuance.expires_at or now + self._config.default_expiry
        credential_id = str(uuid4())
        audience = issuance.audience or self._config.audience

        disclosures = [
            SdJwtDisclosure.build(name, value)
            for name, value in issuance.selective_disclosures.items()
        ]

        credential_subject = dict(issuance.base_claims)
        if disclosures:
            credential_subject["_sd"] = [disclosure.digest for disclosure in disclosures]
        if "id" not in credential_subject:
            credential_subject["id"] = issuance.subject_id

        vc_payload: dict[str, Any] = {
            "type": ["VerifiableCredential", issuance.credential_type],
            "credentialSubject": credential_subject,
        }
        if issuance.additional_payload:
            vc_payload.update(issuance.additional_payload)

        payload: dict[str, Any] = {
            "iss": self._config.issuer,
            "jti": credential_id,
            "iat": int(now.timestamp()),
            "nbf": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
            "vc": vc_payload,
            "sub": issuance.subject_id,
        }
        if audience:
            payload["aud"] = audience
        if issuance.nonce:
            payload["nonce"] = issuance.nonce
        if disclosures:
            payload["_sd"] = [disclosure.digest for disclosure in disclosures]
            payload["_sd_hash_alg"] = "sha-256"

        private_key_pem = await self._key_vault.load_private_key(self._config.signing_key_id)
        private_key = serialization.load_pem_private_key(private_key_pem, password=None)
        headers = {
            "typ": "vc+sd-jwt",
            "alg": self._config.signing_algorithm,
        }
        if self._config.kid:
            headers["kid"] = self._config.kid
        x5c_chain = self._build_x5c_chain()
        if x5c_chain:
            headers["x5c"] = x5c_chain

        token = jwt.encode(
            payload,
            private_key,
            algorithm=self._config.signing_algorithm,
            headers=headers,
        )

        return SdJwtIssuanceResult(
            credential_id=credential_id,
            token=token,
            disclosures=[disclosure.encoded for disclosure in disclosures],
            issuer=self._config.issuer,
            subject_id=issuance.subject_id,
            credential_type=issuance.credential_type,
            audience=audience,
            expires_at=expires_at,
            issued_at=now,
            payload=payload,
            disclosure_objects=disclosures,
        )

    def _build_x5c_chain(self) -> list[str]:
        chain = self._certificate_chain_provider()
        x5c_entries: list[str] = []
        for certificate in chain:
            try:
                # Use crypto_bridge Certificate's to_der() method
                der_bytes = certificate.to_der() if hasattr(certificate, 'to_der') else certificate.public_bytes(Encoding.DER)
            except Exception:  # pragma: no cover - defensive guard
                continue
            x5c_entries.append(_b64url_encode(der_bytes))
        return x5c_entries


__all__ = [
    "SdJwtConfig",
    "SdJwtDisclosure",
    "SdJwtIssuanceInput",
    "SdJwtIssuanceResult",
    "SdJwtIssuer",
]
