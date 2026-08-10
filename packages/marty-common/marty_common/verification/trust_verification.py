"""Native-backed trust verification compatibility layer."""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from marty_common.crypto.certificate_validator import (
    CertificateChainValidator as NativeChainValidator,
)
from marty_common.crypto.sod_signer import verify_sod_signature
from marty_common.native_backends import NativeOperationError, load_native_backend


class TrustValidationLevel(Enum):
    BASIC = "basic"
    STANDARD = "standard"
    STRICT = "strict"


class TrustSource(Enum):
    PKD = "pkd"
    CONFIGURED = "configured"
    CSCA = "csca"
    NATIONAL_PKI = "national_pki"
    EMERGENCY = "emergency"


class TrustValidationError(Enum):
    PKD_UNAVAILABLE = "pkd_unavailable"
    CERTIFICATE_NOT_FOUND = "certificate_not_found"
    CERTIFICATE_EXPIRED = "certificate_expired"
    CERTIFICATE_REVOKED = "certificate_revoked"
    CHAIN_VALIDATION_FAILED = "chain_validation_failed"
    TRUST_ANCHOR_NOT_FOUND = "trust_anchor_not_found"
    INVALID_SIGNATURE = "invalid_signature"
    POLICY_VIOLATION = "policy_violation"


@dataclass
class TrustResult:
    check_name: str
    passed: bool
    details: str
    trust_source: TrustSource
    confidence: float = 1.0
    error_code: TrustValidationError | None = None
    certificate_chain: list[str] | None = None
    trust_anchor: str | None = None


@dataclass
class CertificateInfo:
    certificate_pem: str
    subject: str
    issuer: str
    serial_number: str
    not_before: datetime
    not_after: datetime
    fingerprint: str
    is_ca: bool = False
    key_usage: list[str] = field(default_factory=list)


def _native():
    return load_native_backend(
        "marty_verification",
        (
            "certificate_der_to_pem",
            "certificate_pem_to_der",
            "get_certificate_info",
            "load_certificate_der",
        ),
    )


def _certificate_der(value: Any) -> bytes:
    native = _native()
    if isinstance(value, CertificateInfo):
        value = value.certificate_pem
    if isinstance(value, str):
        return bytes(native.certificate_pem_to_der(value))
    if isinstance(value, bytes):
        if value.lstrip().startswith(b"-----BEGIN"):
            return bytes(native.certificate_pem_to_der(value.decode("ascii")))
        return bytes(native.load_certificate_der(value))
    if isinstance(value, dict):
        for key in ("certificate", "certificate_pem", "pem", "der"):
            if value.get(key) is not None:
                return _certificate_der(value[key])
    for attribute in ("certificate", "certificate_pem", "pem", "der"):
        candidate = getattr(value, attribute, None)
        if candidate is not None:
            return _certificate_der(candidate)
    raise NativeOperationError("Trust validation requires a DER or PEM certificate")


def _parse_time(value: Any) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)


def _certificate_info(value: Any) -> CertificateInfo:
    native = _native()
    der = _certificate_der(value)
    info = native.get_certificate_info(der)
    return CertificateInfo(
        certificate_pem=str(native.certificate_der_to_pem(der)),
        subject=str(info["subject"]),
        issuer=str(info["issuer"]),
        serial_number=str(info["serial_number"]),
        not_before=_parse_time(info["not_before"]),
        not_after=_parse_time(info["not_after"]),
        fingerprint=str(info["fingerprint_sha256"]),
        is_ca=bool(info.get("is_ca")),
        key_usage=list(info.get("key_usage", [])),
    )


async def _invoke(client: Any, names: tuple[str, ...], *args: Any) -> Any:
    if client is None:
        return None
    for name in names:
        method = getattr(client, name, None)
        if callable(method):
            result = method(*args)
            return await result if inspect.isawaitable(result) else result
    raise NativeOperationError(f"Configured trust client exposes none of the required methods: {', '.join(names)}")


class PKDResolver:
    """Resolve certificate bytes from configured PKD/CSCA service adapters."""

    def __init__(self, pkd_service_client=None, csca_service_client=None) -> None:
        self.pkd_client = pkd_service_client
        self.csca_client = csca_service_client
        self._certificate_cache: dict[str, CertificateInfo] = {}
        self._trust_anchor_cache: dict[str, CertificateInfo] = {}

    async def resolve_certificate(self, certificate_id: str) -> CertificateInfo | None:
        if certificate_id in self._certificate_cache:
            return self._certificate_cache[certificate_id]
        for client in (self.pkd_client, self.csca_client):
            record = await _invoke(
                client,
                ("get_certificate", "resolve_certificate", "GetCertificate"),
                certificate_id,
            )
            if record is not None:
                parsed = _certificate_info(record)
                self._certificate_cache[certificate_id] = parsed
                return parsed
        return None

    async def _resolve_from_pkd(self, certificate_id: str) -> CertificateInfo | None:
        record = await _invoke(
            self.pkd_client,
            ("get_certificate", "resolve_certificate", "GetCertificate"),
            certificate_id,
        )
        return _certificate_info(record) if record is not None else None

    async def _resolve_from_csca(self, certificate_id: str) -> CertificateInfo | None:
        record = await _invoke(
            self.csca_client,
            ("get_certificate", "resolve_certificate", "GetCertificate"),
            certificate_id,
        )
        return _certificate_info(record) if record is not None else None

    async def get_trust_anchors(self, country_code: str | None = None) -> list[CertificateInfo]:
        client = self.pkd_client or self.csca_client
        records = await _invoke(
            client,
            ("list_trust_anchors", "get_trust_anchors", "ListTrustAnchors"),
            country_code,
        )
        if records is None:
            return []
        records = getattr(records, "certificates", records)
        anchors = [_certificate_info(record) for record in records]
        for anchor in anchors:
            self._trust_anchor_cache[anchor.fingerprint] = anchor
        return anchors


class CertificateChainValidator:
    """Map native chain validation into the historical trust-result shape."""

    def __init__(self, pkd_resolver: PKDResolver) -> None:
        self.pkd_resolver = pkd_resolver

    async def validate_chain(
        self,
        leaf_certificate: str | bytes,
        intermediate_certificates: list[str | bytes] | None = None,
        trust_anchors: list[CertificateInfo] | None = None,
        crls: list[str | bytes] | None = None,
    ) -> list[TrustResult]:
        anchors = trust_anchors or []
        if not anchors:
            return [
                TrustResult(
                    "trust_chain_validation",
                    False,
                    "No CSCA trust anchors configured",
                    TrustSource.PKD,
                    error_code=TrustValidationError.TRUST_ANCHOR_NOT_FOUND,
                )
            ]
        validator = NativeChainValidator([_certificate_der(anchor) for anchor in anchors])
        for crl in crls or []:
            validator.add_crl(crl)
        result = validator.validate_certificate_chain(
            _certificate_der(leaf_certificate),
            [_certificate_der(value) for value in intermediate_certificates or []],
        )
        path = [item.fingerprint_sha256 for item in result.validation_path]
        anchor = _certificate_info(result.trust_anchor).fingerprint if result.trust_anchor is not None else None
        details = (
            "Native certificate chain is valid"
            if result.is_valid
            else "; ".join(error.error_message for error in result.errors)
        )
        return [
            TrustResult(
                "trust_chain_validation",
                result.is_valid,
                details or "Native certificate chain validation failed",
                TrustSource.PKD,
                certificate_chain=path,
                trust_anchor=anchor,
                error_code=(None if result.is_valid else TrustValidationError.CHAIN_VALIDATION_FAILED),
            )
        ]

    def _parse_certificate(self, certificate_data: str | bytes) -> CertificateInfo:
        return _certificate_info(certificate_data)


class TrustValidator:
    """Orchestrate PKD resolution and native trust checks without simulation."""

    def __init__(self, pkd_service_client=None, csca_service_client=None) -> None:
        self.pkd_resolver = PKDResolver(pkd_service_client, csca_service_client)
        self.chain_validator = CertificateChainValidator(self.pkd_resolver)

    async def validate_trust(
        self,
        document_data: dict[str, Any],
        doc_class: Any,
        validation_level: TrustValidationLevel = TrustValidationLevel.STANDARD,
    ) -> list[TrustResult]:
        del doc_class
        issuing_authority = str(document_data.get("issuing_authority", ""))
        country = issuing_authority[:3] or None
        anchors = await self.pkd_resolver.get_trust_anchors(country)
        results = [
            TrustResult(
                "pkd_trust_anchor_resolution",
                bool(anchors),
                (f"Resolved {len(anchors)} native trust anchors" if anchors else "No trust anchors resolved"),
                TrustSource.PKD,
                error_code=(None if anchors else TrustValidationError.TRUST_ANCHOR_NOT_FOUND),
            )
        ]

        chip = document_data.get("chip_data") or {}
        vds = document_data.get("vds_nc_data") or {}
        leaf = chip.get("dsc_certificate") or vds.get("certificate")
        intermediates = document_data.get("intermediate_certificates") or []
        crls = document_data.get("crls") or []
        if leaf:
            results.extend(
                await self.chain_validator.validate_chain(
                    leaf,
                    intermediates,
                    anchors,
                    crls if validation_level is TrustValidationLevel.STRICT else None,
                )
            )
        else:
            results.append(
                TrustResult(
                    "certificate_availability",
                    False,
                    "No DSC or VDS-NC signer certificate supplied",
                    TrustSource.CONFIGURED,
                    error_code=TrustValidationError.CERTIFICATE_NOT_FOUND,
                )
            )

        sod = chip.get("sod") or chip.get("security_object")
        if sod:
            sod_valid = bool(anchors) and verify_sod_signature(sod, [_certificate_der(anchor) for anchor in anchors])
            results.append(
                TrustResult(
                    "sod_trust_validation",
                    sod_valid,
                    ("Native SOD signature is trusted" if sod_valid else "Native SOD signature verification failed"),
                    TrustSource.PKD,
                    error_code=(None if sod_valid else TrustValidationError.INVALID_SIGNATURE),
                )
            )

        if validation_level is TrustValidationLevel.STRICT and not crls:
            results.append(
                TrustResult(
                    "certificate_revocation_check",
                    False,
                    "Strict validation requires native CRL evidence",
                    TrustSource.PKD,
                    error_code=TrustValidationError.POLICY_VIOLATION,
                )
            )
        return results


__all__ = [
    "CertificateChainValidator",
    "CertificateInfo",
    "PKDResolver",
    "TrustResult",
    "TrustSource",
    "TrustValidationError",
    "TrustValidationLevel",
    "TrustValidator",
]
