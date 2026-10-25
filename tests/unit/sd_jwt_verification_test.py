"""Retained public-key verification stays usable after Python issuer retirement."""

import base64
import hashlib
import json
import time

import pytest
from jwcrypto import jwk, jws

from marty_common.native_backends import NativeOperationError
from marty_common.vc.sd_jwt_verifier import SdJwtVerifier


def test_native_sdjwt_verification_accepts_valid_and_rejects_wrong_public_key():
    # Ephemeral test-fixture keys never enter the production issuance path.
    key = jwk.JWK.generate(kty="EC", crv="P-256")
    other = jwk.JWK.generate(kty="EC", crv="P-256")
    # Build an isolated signed public test vector, not a production issuer.
    disclosure = (
        base64.urlsafe_b64encode(
            json.dumps(["test-only-salt", "documentNumber", "fixture-123"]).encode()
        )
        .decode()
        .rstrip("=")
    )
    digest = (
        base64.urlsafe_b64encode(hashlib.sha256(disclosure.encode()).digest())
        .decode()
        .rstrip("=")
    )
    now = int(time.time())
    payload = {
        "iss": "https://issuer.example",
        "sub": "did:example:holder",
        "vct": "PreTravelCredential",
        "iat": now,
        "exp": now + 300,
        "_sd_alg": "sha-256",
        "_sd": [digest],
    }
    signed = jws.JWS(json.dumps(payload).encode())
    signed.add_signature(
        key, protected=json.dumps({"alg": "ES256", "typ": "vc+sd-jwt"})
    )
    token, disclosures = signed.serialize(compact=True), [disclosure]
    result = SdJwtVerifier(issuer_jwk=key.export_public()).verify(token, disclosures)
    assert result.valid and not result.errors
    assert (
        not SdJwtVerifier(issuer_jwk=other.export_public())
        .verify(token, disclosures)
        .valid
    )
    assert (
        not SdJwtVerifier(issuer_jwk=key.export_public())
        .verify(token, ["invalid-disclosure"])
        .valid
    )


def test_public_verifier_requires_explicit_public_key_and_supported_trust_policy():
    with pytest.raises(NativeOperationError, match="public JWK"):
        SdJwtVerifier().verify("untrusted", [])
    with pytest.raises(NativeOperationError, match="legacy x5c"):
        SdJwtVerifier(trust_anchors=["unqualified-chain"])
    with pytest.raises(NativeOperationError, match="wallet-attestation"):
        SdJwtVerifier(issuer_jwk={}).verify(
            "untrusted", [], wallet_attestation="unqualified"
        )
