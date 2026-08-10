"""Helpers for issuing SD-JWT based verifiable credentials."""

from __future__ import annotations

import base64
import json
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from marty_common import crypto_bridge
from marty_common.crypto_bridge import Certificate, sha256
from marty_common.infrastructure import KeyVaultClient
from marty_common.native_backends import NativeOperationError, load_native_backend


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
        # Use Rust sha256 for hashing
        digest_bytes = sha256(disclosure_json.encode("utf-8"))
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
        now = datetime.now(UTC)
        expires_at = issuance.expires_at or now + self._config.default_expiry
        audience = issuance.audience or self._config.audience
        if audience or issuance.nonce or issuance.additional_payload:
            raise NativeOperationError(
                "The native SD-JWT issuer does not support audience, nonce, or arbitrary top-level payload injection"
            )
        if self._certificate_chain_provider():
            raise NativeOperationError("The native SD-JWT issuer does not support an x5c header")

        private_key_pem = await self._key_vault.load_private_key(self._config.signing_key_id)
        private_key_der = crypto_bridge.load_private_key_pem(private_key_pem.decode("ascii"))
        private_jwk = self._private_jwk(private_key_der)
        claims = dict(issuance.base_claims)
        claims.update(issuance.selective_disclosures)
        ttl_seconds = max(1, int((expires_at - now).total_seconds()))

        native = load_native_backend(
            "_marty_rs",
            ("oid4vci_sign_credential",),
        )
        compact, credential_id = native.oid4vci_sign_credential(
            self._config.issuer,
            json.dumps(private_jwk),
            issuance.subject_id,
            issuance.credential_type,
            json.dumps(claims),
            ttl_seconds,
            "vc+sd-jwt",
            list(issuance.selective_disclosures),
        )
        token, disclosures = self._split_compact_sd_jwt(compact)
        payload = self._decode_jwt_payload(token)
        disclosure_objects = [self._decode_disclosure(encoded) for encoded in disclosures]

        return SdJwtIssuanceResult(
            credential_id=credential_id,
            token=token,
            disclosures=disclosures,
            issuer=self._config.issuer,
            subject_id=issuance.subject_id,
            credential_type=issuance.credential_type,
            audience=audience,
            expires_at=expires_at,
            issued_at=now,
            payload=payload,
            disclosure_objects=disclosure_objects,
        )

    def _private_jwk(self, private_key_der: bytes) -> dict[str, str]:
        key_type = crypto_bridge.detect_private_key_type(private_key_der)
        private_raw, _ = crypto_bridge.pkcs8_to_raw_private_key(private_key_der)
        public_der = crypto_bridge.extract_public_key(private_key_der)
        public_raw, _ = crypto_bridge.spki_to_raw_public_key(public_der)
        kid = self._config.kid or self._config.signing_key_id

        if key_type == "EC_P256" and len(public_raw) == 65:
            return {
                "kty": "EC",
                "crv": "P-256",
                "x": _b64url_encode(public_raw[1:33]),
                "y": _b64url_encode(public_raw[33:65]),
                "d": _b64url_encode(private_raw),
                "alg": "ES256",
                "kid": kid,
            }
        if key_type == "Ed25519" and len(public_raw) == 32:
            return {
                "kty": "OKP",
                "crv": "Ed25519",
                "x": _b64url_encode(public_raw),
                "d": _b64url_encode(private_raw),
                "alg": "EdDSA",
                "kid": kid,
            }
        raise NativeOperationError(f"Native SD-JWT issuance does not support key type {key_type!r}")

    @staticmethod
    def _split_compact_sd_jwt(compact: str) -> tuple[str, list[str]]:
        parts = compact.split("~")
        token = parts[0]
        disclosures = [value for value in parts[1:] if value]
        if token.count(".") != 2:
            raise NativeOperationError("Native SD-JWT issuer returned an invalid token")
        return token, disclosures

    @staticmethod
    def _decode_jwt_payload(token: str) -> dict[str, Any]:
        try:
            encoded = token.split(".", 2)[1]
            return json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        except (ValueError, json.JSONDecodeError) as exc:
            raise NativeOperationError("Native SD-JWT issuer returned an invalid payload") from exc

    @staticmethod
    def _decode_disclosure(encoded: str) -> SdJwtDisclosure:
        try:
            raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
            salt, name, value = json.loads(raw)
        except (ValueError, json.JSONDecodeError, TypeError) as exc:
            raise NativeOperationError("Native SD-JWT issuer returned an invalid disclosure") from exc
        return SdJwtDisclosure(
            salt=str(salt),
            name=str(name),
            value=value,
            encoded=encoded,
            digest=_b64url_encode(sha256(encoded.encode("ascii"))),
        )


__all__ = [
    "SdJwtConfig",
    "SdJwtDisclosure",
    "SdJwtIssuanceInput",
    "SdJwtIssuanceResult",
    "SdJwtIssuer",
]
