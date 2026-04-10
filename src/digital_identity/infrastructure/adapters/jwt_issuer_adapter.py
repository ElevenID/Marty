"""
JWT Issuer Bridge Adapter

Bridges the CredentialIssuanceService interface with the RustCredentialIssuer
from marty-credentials. The service layer expects a flat keyword interface
(credential_id, issuer_did, subject_claims, ...) while the Rust adapter expects
wrapped value objects (KeyPair, CredentialSubject).

Limitations:
- credential_id: The Rust FFI auto-generates the credential ID; the caller's
  credential_id is returned but not embedded in the JWT. The issuance service
  tracks it independently via the database.
- credential_status: Not supported by the Rust FFI. The status entry is injected
  into subject claims as a workaround until the Rust layer adds a
  credentialStatus parameter.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from marty_credentials.adapters.rust.adapter import RustCredentialIssuer
from marty_credentials.ports.credential_ports import (
    CredentialSubject,
    KeyAlgorithm,
    KeyPair,
)

logger = logging.getLogger(__name__)

_ALG_MAP = {
    "ES256": KeyAlgorithm.ES256,
    "ES256K": KeyAlgorithm.ES256K,
    "EdDSA": KeyAlgorithm.EDDSA,
}


class JwtIssuerBridgeAdapter:
    """Adapts RustCredentialIssuer to the CredentialIssuanceService caller."""

    def __init__(self) -> None:
        self._issuer = RustCredentialIssuer()

    def create_credential(
        self,
        credential_id: str,
        issuer_did: str,
        subject_claims: dict[str, Any],
        credential_type: str,
        signing_key_jwk: str,
        credential_status: dict[str, Any] | None = None,
    ) -> str:
        """Create a JWT-VC and return the compact serialisation string.

        Args:
            credential_id: Caller-assigned credential URI (tracked externally).
            issuer_did: DID of the issuer.
            subject_claims: Dict with at least ``"id"`` for the subject.
            credential_type: e.g. ``"UniversityDegreeCredential"``.
            signing_key_jwk: JWK JSON string for signing.
            credential_status: Optional W3C BitstringStatusListEntry dict.

        Returns:
            JWT compact serialisation string.
        """
        # Resolve algorithm from JWK if present, default ES256
        algorithm = KeyAlgorithm.ES256
        try:
            jwk_obj = json.loads(signing_key_jwk)
            alg = jwk_obj.get("alg") or jwk_obj.get("crv", "")
            if alg in _ALG_MAP:
                algorithm = _ALG_MAP[alg]
            elif alg == "P-256":
                algorithm = KeyAlgorithm.ES256
            elif alg in ("secp256k1", "P-256K"):
                algorithm = KeyAlgorithm.ES256K
            elif alg == "Ed25519":
                algorithm = KeyAlgorithm.EDDSA
        except (json.JSONDecodeError, TypeError):
            pass

        key_pair = KeyPair(
            did=issuer_did,
            jwk_json=signing_key_jwk,
            algorithm=algorithm,
        )

        # Build claims dict — inject credentialStatus as a claim attribute
        # until the Rust FFI supports a first-class credentialStatus parameter.
        claims = {k: v for k, v in subject_claims.items() if k != "id"}
        if credential_status:
            claims["credentialStatus"] = credential_status

        subject = CredentialSubject(
            id=subject_claims.get("id"),
            claims=claims,
        )

        result = self._issuer.create_credential(
            issuer_key=key_pair,
            credential_type=credential_type,
            subject=subject,
        )

        logger.debug(
            "Created JWT-VC via bridge adapter (rust_id=%s, caller_id=%s)",
            result.id,
            credential_id,
        )

        return result.jwt
