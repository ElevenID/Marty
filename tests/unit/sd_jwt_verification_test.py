"""Retained public-key verification stays usable after Python issuer retirement."""

import json

import pytest
from jwcrypto import jwk

from marty_common.native_backends import NativeOperationError, load_native_backend
from marty_common.vc.sd_jwt_verifier import SdJwtVerifier


def test_native_sdjwt_verification_accepts_valid_and_rejects_wrong_public_key():
    # Ephemeral test-fixture keys never enter the production issuance path.
    key = jwk.JWK.generate(kty="EC", crv="P-256")
    other = jwk.JWK.generate(kty="EC", crv="P-256")
    native = load_native_backend("_marty_rs", ("oid4vci_sign_credential",))
    compact, _ = native.oid4vci_sign_credential(
        "https://issuer.example",
        key.export_private(),
        "did:example:holder",
        "PreTravelCredential",
        json.dumps({"documentNumber": "fixture-123"}),
        300,
        "vc+sd-jwt",
        ["documentNumber"],
    )
    parts = compact.split("~")
    token, disclosures = parts[0], [value for value in parts[1:] if value]
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
