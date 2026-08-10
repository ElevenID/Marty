"""Native SD-JWT verification compatibility adapter."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from marty_common.native_backends import NativeOperationError, load_native_backend


@dataclass(slots=True)
class SdJwtVerificationResult:
    """Outcome of SD-JWT verification."""

    valid: bool
    payload: dict[str, Any]
    disclosures: dict[str, Any]
    errors: list[str]
    warnings: list[str]
    certificate_subject: str | None = None


class SdJwtVerifier:
    """Delegate SD-JWT verification to the canonical Rust RFC 9449 engine."""

    def __init__(
        self,
        trust_anchors: Iterable[Any] | None = None,
        wallet_trust_anchors: Iterable[Any] | None = None,
        *,
        issuer_jwk: Mapping[str, Any] | str | None = None,
        expected_audience: str | None = None,
        expected_nonce: str | None = None,
    ) -> None:
        if trust_anchors or wallet_trust_anchors:
            raise NativeOperationError("The legacy x5c SD-JWT verifier is retired; configure the issuer public JWK")
        self.issuer_jwk = issuer_jwk
        self.expected_audience = expected_audience
        self.expected_nonce = expected_nonce

    def verify(
        self,
        token: str,
        disclosures: Sequence[str],
        *,
        wallet_attestation: str | None = None,
    ) -> SdJwtVerificationResult:
        if wallet_attestation is not None:
            raise NativeOperationError("Wallet attestation verification requires the native wallet-attestation service")
        if self.issuer_jwk is None:
            raise NativeOperationError("Native SD-JWT verification requires an issuer public JWK")

        compact = token
        if disclosures:
            compact = "~".join((token.rstrip("~"), *disclosures, ""))
        issuer_jwk_json = (
            self.issuer_jwk
            if isinstance(self.issuer_jwk, str)
            else json.dumps(self.issuer_jwk, separators=(",", ":"), sort_keys=True)
        )
        native = load_native_backend("_marty_rs", ("verify_sd_jwt",))
        try:
            payload = json.loads(
                native.verify_sd_jwt(
                    compact,
                    issuer_jwk_json,
                    self.expected_audience,
                    self.expected_nonce,
                )
            )
        except (RuntimeError, TypeError, ValueError) as exc:
            return SdJwtVerificationResult(
                valid=False,
                payload={},
                disclosures={},
                errors=[f"Native SD-JWT verification failed: {exc}"],
                warnings=[],
            )
        return SdJwtVerificationResult(
            valid=True,
            payload=payload,
            disclosures={},
            errors=[],
            warnings=[],
        )


__all__ = ["SdJwtVerificationResult", "SdJwtVerifier"]
