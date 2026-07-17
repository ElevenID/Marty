"""High-level cryptographic verification helpers for ICAO eMRTDs.

This module stitches together the lower-level cryptographic building blocks that
already exist in ``marty_common`` (MRZ parsing, SOD parsing, active
authentication, certificate validation, etc.) and exposes a cohesive API that
services can use to perform production-grade verification of passports.

It covers the following responsibilities:

* Full MRZ parsing and check-digit validation (TD3 passports).
* Security Object (SOD) parsing, hash comparison and metadata extraction.
* Document Signer (DSC) certificate chain validation against provisioned CSCA
  trust anchors.
* Active Authentication (AA) helpers driven by DG15 public key material.

The goal is to give higher-level services (Inspection System, personalization
pipelines, test harnesses) a single entry point for validating cryptographic
artifacts without re-implementing the orchestration logic every time.
"""

from __future__ import annotations

import base64
import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes

# Import crypto_bridge for certificate compatibility
from marty_common.crypto_bridge import Certificate as CertificateBridge

from marty_common.crypto.certificate_validator import (
    CertificateChainValidator,
    ChainValidationResult,
)
from marty_common.crypto.data_group_hasher import DataGroupHashComputer
from marty_common.crypto.sod_parser import HashAlgorithmError, SODParsingError, SODProcessor
from marty_common.models.asn1_structures import SOD
from marty_common.security.active_authentication import (
    ActiveAuthenticationChallenge,
    ActiveAuthenticationProtocol,
    ActiveAuthenticationResponse,
)
from marty_common.security.dg15_parser import ChipAuthenticationInfo, DG15Parser
from marty_common.security.passport_chip_session import (
    PassportChipSession,
    PassportChipTransport,
)
from marty_common.utils.mrz_utils import MRZException, MRZParser

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class MRZValidationResult:
    """Outcome of MRZ validation."""

    is_valid: bool
    mrz_string: str
    parsed: Any | None
    errors: list[str]


@dataclass
class SODValidationResult:
    """Outcome of SOD parsing and data-group integrity verification."""

    is_valid: bool
    hash_algorithm: str | None
    expected_hashes: dict[int, str]
    computed_hashes: dict[int, str]
    errors: list[str]


@dataclass
class CertificateValidationSummary:
    """Wrapper for DSC -> CSCA chain validation."""

    result: ChainValidationResult
    sod_certificate_subject: str | None


@dataclass
class ActiveAuthenticationResult:
    """Outcome of Active Authentication verification."""

    is_valid: bool
    challenge: ActiveAuthenticationChallenge
    chip_info: ChipAuthenticationInfo | None
    recovered_message: bytes | None
    error: str | None = None


class PassportCryptoValidationError(Exception):
    """Raised when cryptographic verification cannot be completed."""


# ---------------------------------------------------------------------------
# PassportCryptoValidator implementation
# ---------------------------------------------------------------------------


class PassportCryptoValidator:
    """End-to-end cryptographic validator for ICAO-compliant passports."""

    def __init__(
        self,
        trust_anchors: Iterable[x509.Certificate | CertificateBridge] | None = None,
    ) -> None:
        self._sod_processor = SODProcessor()
        self._hash_computer = DataGroupHashComputer()
        self._cert_validator = CertificateChainValidator()
        self._active_auth = ActiveAuthenticationProtocol()
        self._dg15_parser = DG15Parser()
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        if trust_anchors:
            self.load_trust_anchors(trust_anchors)

    # ------------------------------------------------------------------
    # Trust anchor management
    # ------------------------------------------------------------------
    def load_trust_anchors(self, certificates: Iterable[x509.Certificate | CertificateBridge]) -> None:
        """Populate the validator with CSCA trust anchors."""
        cert_list = list(certificates)
        for cert in cert_list:
            # Convert CertificateBridge to x509.Certificate if needed
            if isinstance(cert, CertificateBridge):
                cert = cert.to_cryptography()
            self._cert_validator.add_trust_anchor(cert)
        self.logger.info("Loaded %d CSCA trust anchors", len(cert_list))

    # ------------------------------------------------------------------
    # MRZ validation helpers
    # ------------------------------------------------------------------
    def validate_mrz(self, mrz_lines: Sequence[str] | str) -> MRZValidationResult:
        """Validate TD3 MRZ lines and return parsed model."""
        if isinstance(mrz_lines, str):
            payload = mrz_lines.strip()
        else:
            payload = "\n".join(line.strip() for line in mrz_lines)

        try:
            parsed = MRZParser.parse_td3_mrz(payload)
            return MRZValidationResult(
                is_valid=True,
                mrz_string=payload,
                parsed=parsed,
                errors=[],
            )
        except MRZException as exc:
            self.logger.warning("MRZ validation failed: %s", exc)
            return MRZValidationResult(
                is_valid=False,
                mrz_string=payload,
                parsed=None,
                errors=[str(exc)],
            )

    # ------------------------------------------------------------------
    # SOD parsing & hash verification
    # ------------------------------------------------------------------
    def verify_sod(
        self,
        sod_blob: bytes | str,
        data_groups: dict[str, Any],
    ) -> SODValidationResult:
        """Verify SOD integrity against provided data groups."""
        try:
            prepared = self._hash_computer.prepare_data_groups_for_verification(data_groups)
            success, errors, details = self._hash_computer.verify_data_group_integrity_with_sod(
                sod_blob, prepared
            )
        except (SODParsingError, HashAlgorithmError) as exc:
            self.logger.exception("Failed to verify SOD: %s", exc)
            raise PassportCryptoValidationError(str(exc)) from exc

        hash_algo = details.get("hash_algorithm") if success else None
        expected = {int(k): v for k, v in details.get("expected_hashes", {}).items()}
        computed = {int(k): v for k, v in details.get("computed_hashes", {}).items()}

        return SODValidationResult(
            is_valid=success,
            hash_algorithm=hash_algo,
            expected_hashes=expected,
            computed_hashes=computed,
            errors=errors,
        )

    def parse_sod(self, sod_blob: bytes | str) -> SOD:
        """Parse SOD data and return ASN.1 model."""
        sod = self._sod_processor.parse_sod_data(sod_blob)
        if sod is None:
            msg = "No SOD content found"
            raise PassportCryptoValidationError(msg)
        return sod

    # ------------------------------------------------------------------
    # Certificate chain validation
    # ------------------------------------------------------------------
    def validate_sod_certificate(
        self,
        sod_blob: bytes | str,
        extra_trust_anchors: Sequence[x509.Certificate] | None = None,
    ) -> CertificateValidationSummary:
        """Validate the Document Signer certificate embedded inside the SOD."""
        sod = self.parse_sod(sod_blob)
        certificate_model = sod.get_certificate()
        if certificate_model is None:
            msg = "SOD does not contain a Document Signer certificate"
            raise PassportCryptoValidationError(msg)

        ds_cert = x509.load_der_x509_certificate(certificate_model.dump())

        intermediates: list[x509.Certificate] = []
        signed_data = sod.signed_data
        certificates = signed_data["certificates"]
        if certificates and len(certificates) > 1:
            for extra in certificates[1:]:
                try:
                    intermediates.append(x509.load_der_x509_certificate(extra.dump()))
                except Exception as exc:  # pragma: no cover - defensive logging
                    self.logger.warning("Failed to parse intermediate certificate: %s", exc)

        if extra_trust_anchors:
            self.load_trust_anchors(extra_trust_anchors)

        validation = self._cert_validator.validate_certificate_chain(ds_cert, intermediates)
        subject = ds_cert.subject.rfc4514_string()
        return CertificateValidationSummary(result=validation, sod_certificate_subject=subject)

    # ------------------------------------------------------------------
    # Active Authentication helpers
    # ------------------------------------------------------------------
    def generate_active_authentication_challenge(
        self,
        key_size_bits: int = 128,
        hash_algorithm: hashes.HashAlgorithm | None = None,
    ) -> ActiveAuthenticationChallenge:
        """Generate a random challenge suitable for Active Authentication."""
        if hash_algorithm is None:
            canonical_name = "SHA-256"
        else:
            alg_name = hash_algorithm.name.lower()
            canonical_name = alg_name.upper()
            if alg_name.startswith("sha") and len(alg_name) > 3:
                canonical_name = f"SHA-{alg_name[3:]}"
        return self._active_auth.generate_challenge(
            key_size=key_size_bits, hash_algorithm=canonical_name
        )

    def verify_active_authentication(
        self,
        dg15_data: bytes,
        challenge: ActiveAuthenticationChallenge,
        signature: bytes,
    ) -> ActiveAuthenticationResult:
        """Verify Active Authentication response using DG15 public key."""
        try:
            chip_info = self._dg15_parser.parse_dg15(dg15_data)
        except ValueError as exc:
            self.logger.warning("Failed to parse DG15 data: %s", exc)
            return ActiveAuthenticationResult(
                is_valid=False,
                challenge=challenge,
                chip_info=None,
                recovered_message=None,
                error=str(exc),
            )

        response = ActiveAuthenticationResponse(signature=signature)
        try:
            is_valid = self._active_auth.verify_active_authentication(
                response=response,
                challenge=challenge,
                public_key=chip_info.public_key,
            )
            recovered = response.recovered_message
        except Exception as exc:  # pragma: no cover - defensive safeguard
            self.logger.exception("Active Authentication verification error")
            return ActiveAuthenticationResult(
                is_valid=False,
                challenge=challenge,
                chip_info=chip_info,
                recovered_message=None,
                error=str(exc),
            )

        return ActiveAuthenticationResult(
            is_valid=is_valid,
            challenge=challenge,
            chip_info=chip_info,
            recovered_message=recovered,
            error=None if is_valid else "Challenge mismatch",
        )

    def perform_chip_active_authentication(
        self,
        transport: PassportChipTransport,
        *,
        passport_number: str,
        date_of_birth: str,
        date_of_expiry: str,
        dg15_data: bytes | None = None,
        pace_password: str | None = None,
        challenge: ActiveAuthenticationChallenge | None = None,
    ) -> ActiveAuthenticationResult:
        """Perform BAC/PACE and Active Authentication directly against a chip."""

        session = PassportChipSession(transport, aa_protocol=self._active_auth)
        try:
            session.select_passport_application()

            if pace_password:
                session.establish_pace(pace_password)
            else:
                session.establish_bac(passport_number, date_of_birth, date_of_expiry)

            dg15_blob = dg15_data or session.read_data_group(15)
            auth_challenge = challenge or self._active_auth.generate_challenge()
            outcome = session.perform_active_authentication(dg15_blob, auth_challenge)

            return ActiveAuthenticationResult(
                is_valid=outcome.is_valid,
                challenge=outcome.challenge,
                chip_info=outcome.chip_info,
                recovered_message=outcome.response.recovered_message,
                error=None if outcome.is_valid else "Challenge mismatch",
            )
        except Exception as exc:  # pragma: no cover - hardware/path specific errors
            self.logger.exception("Active authentication against chip failed: %s", exc)
            fallback_challenge = challenge or self._active_auth.generate_challenge()
            return ActiveAuthenticationResult(
                is_valid=False,
                challenge=fallback_challenge,
                chip_info=None,
                recovered_message=None,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Convenience utilities
    # ------------------------------------------------------------------
    @staticmethod
    def decode_maybe_base64(data: bytes | str) -> bytes:
        """Decode input that may be base64 encoded."""
        if isinstance(data, bytes):
            return data
        try:
            return base64.b64decode(data, validate=True)
        except Exception:
            return (
                bytes.fromhex(data)
                if all(c in "0123456789abcdefABCDEF" for c in data.strip())
                else data.encode("utf-8")
            )


__all__ = [
    "ActiveAuthenticationResult",
    "CertificateValidationSummary",
    "MRZValidationResult",
    "PassportCryptoValidationError",
    "PassportCryptoValidator",
    "SODValidationResult",
]
