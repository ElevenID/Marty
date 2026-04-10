"""Digital Travel Credential cryptographic verification helpers."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import cbor2
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa

# Import crypto_bridge for certificate compatibility
from marty_plugin.common.crypto_bridge import Certificate as CertificateBridge

from marty_plugin.common.crypto.certificate_validator import (
    CertificateChainValidator,
    ChainValidationResult,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class DTCIntegrityResult:
    """Outcome of verifying DG hash material embedded in the credential."""

    is_valid: bool
    mismatches: list[str]
    expected: Mapping[str, str]
    computed: Mapping[str, str]


@dataclass(slots=True)
class DTCSignatureResult:
    """Outcome of verifying the PRES signature."""

    is_valid: bool
    certificate_subject: str
    chain_result: ChainValidationResult | None
    error: str | None = None


class DTCVerifier:
    """Verifier for ICAO Digital Travel Credential cryptographic properties."""

    def __init__(self, trust_anchors: Iterable[x509.Certificate | CertificateBridge] | None = None) -> None:
        self._chain_validator = CertificateChainValidator()
        if trust_anchors:
            # Convert CertificateBridge to x509.Certificate if needed
            converted_anchors = [
                cert.to_cryptography() if isinstance(cert, CertificateBridge) else cert
                for cert in trust_anchors
            ]
            self._chain_validator.load_csca_certificates(converted_anchors)
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    # ------------------------------------------------------------------
    # Data group hash verification
    # ------------------------------------------------------------------
    @staticmethod
    def compute_data_group_hashes(
        data_groups: Sequence[Mapping[str, Any]], algorithm: str = "sha256"
    ) -> dict[str, str]:
        hash_algorithm = algorithm.lower()
        if hash_algorithm not in {"sha256", "sha384", "sha512", "sha224", "sha1"}:
            msg = f"Unsupported hash algorithm for DTC data groups: {algorithm}"
            raise ValueError(msg)
        if hash_algorithm == "sha1":
            import warnings
            warnings.warn(
                "SHA-1 is cryptographically broken. Use sha256 or stronger.",
                DeprecationWarning,
                stacklevel=2,
            )

        hash_cls = {
            "sha1": hashes.SHA1,
            "sha224": hashes.SHA224,
            "sha256": hashes.SHA256,
            "sha384": hashes.SHA384,
            "sha512": hashes.SHA512,
        }[hash_algorithm]

        results: dict[str, str] = {}
        for item in data_groups:
            dg_number = str(item.get("dg_number") or item.get("number") or item.get("id"))
            raw = item.get("data") or item.get("content") or b""
            if isinstance(raw, str):
                try:
                    payload = bytes.fromhex(raw)
                except ValueError:
                    payload = raw.encode("utf-8")
            else:
                payload = bytes(raw)
            digest = hashes.Hash(hash_cls())
            digest.update(payload)
            results[dg_number] = digest.finalize().hex()
        return results

    def verify_data_group_hashes(
        self,
        credential_payload: Mapping[str, Any],
        data_groups: Sequence[Mapping[str, Any]],
        algorithm: str = "sha256",
    ) -> DTCIntegrityResult:
        expected_hashes: Mapping[str, str] = credential_payload.get("dataGroupHashes", {})  # type: ignore[assignment]
        computed_hashes = self.compute_data_group_hashes(data_groups, algorithm)

        mismatches: list[str] = []
        for dg_number, expected_hash in expected_hashes.items():
            actual = computed_hashes.get(str(dg_number))
            if actual is None:
                mismatches.append(f"Missing DG{dg_number} in computed hash set")
            elif actual.lower() != expected_hash.lower():
                mismatches.append(f"Hash mismatch for DG{dg_number}")

        mismatches.extend(
            f"Unexpected DG{dg_number} in credential payload"
            for dg_number in computed_hashes
            if str(dg_number) not in expected_hashes
        )

        return DTCIntegrityResult(
            is_valid=len(mismatches) == 0,
            mismatches=mismatches,
            expected=expected_hashes,
            computed=computed_hashes,
        )

    # ------------------------------------------------------------------
    # Signature verification
    # ------------------------------------------------------------------
    def verify_signature(
        self,
        payload: Mapping[str, Any],
        signature: bytes,
        signer_certificate: x509.Certificate | CertificateBridge,
        signature_algorithm: hashes.HashAlgorithm | None = None,
    ) -> DTCSignatureResult:
        signature_algorithm = signature_algorithm or hashes.SHA256()
        # Convert CertificateBridge to x509.Certificate if needed
        if isinstance(signer_certificate, CertificateBridge):
            signer_certificate = signer_certificate.to_cryptography()
        public_key = signer_certificate.public_key()
        cbor_payload = cbor2.dumps(payload)

        try:
            if isinstance(public_key, rsa.RSAPublicKey):
                public_key.verify(signature, cbor_payload, padding.PKCS1v15(), signature_algorithm)
            elif isinstance(public_key, ec.EllipticCurvePublicKey):
                public_key.verify(signature, cbor_payload, ec.ECDSA(signature_algorithm))
            else:
                msg = f"Unsupported public key type for DTC signature: {type(public_key)}"
                raise TypeError(msg)
        except (InvalidSignature, TypeError, ValueError) as exc:
            return DTCSignatureResult(
                is_valid=False,
                certificate_subject=signer_certificate.subject.rfc4514_string(),
                chain_result=None,
                error=str(exc),
            )

        return DTCSignatureResult(
            is_valid=True,
            certificate_subject=signer_certificate.subject.rfc4514_string(),
            chain_result=None,
        )

    def validate_certificate_chain(
        self,
        signer_certificate: x509.Certificate | CertificateBridge,
        intermediates: Sequence[x509.Certificate | CertificateBridge] | None = None,
    ) -> ChainValidationResult:
        # Convert CertificateBridge to x509.Certificate if needed
        if isinstance(signer_certificate, CertificateBridge):
            signer_certificate = signer_certificate.to_cryptography()
        converted_intermediates = [
            cert.to_cryptography() if isinstance(cert, CertificateBridge) else cert
            for cert in (intermediates or [])
        ]
        return self._chain_validator.validate_certificate_chain(
            signer_certificate, converted_intermediates
        )


__all__ = [
    "DTCIntegrityResult",
    "DTCSignatureResult",
    "DTCVerifier",
]
