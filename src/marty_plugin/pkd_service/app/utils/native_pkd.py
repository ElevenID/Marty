"""Thin PKD model adapters for the canonical Rust verification backend."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
from uuid import uuid4

from app.models.pkd_models import Certificate, CertificateStatus, RevokedCertificate

from marty_plugin.native_backends import NativeOperationError, require_backend

_REASON_CODES = {
    "KeyCompromise": 1,
    "CaCompromise": 2,
    "AffiliationChanged": 3,
    "Superseded": 4,
    "CessationOfOperation": 5,
    "CertificateHold": 6,
    "RemoveFromCrl": 8,
    "PrivilegeWithdrawn": 9,
    "AaCompromise": 10,
}


def normalize_der(data: bytes) -> bytes:
    """Remove a PEM envelope without interpreting the ASN.1 payload in Python."""

    value = bytes(data)
    if not value.lstrip().startswith(b"-----BEGIN"):
        return value
    payload = b"".join(
        line.strip()
        for line in value.splitlines()
        if line and not line.startswith(b"-----")
    )
    try:
        return base64.b64decode(payload, validate=True)
    except (ValueError, TypeError) as exc:
        raise NativeOperationError(f"Invalid PEM payload: {exc}") from exc


def decode_master_list(master_list_data: bytes) -> list[Certificate]:
    """Map Rust-parsed ICAO Master List certificates to service DTOs."""

    native = require_backend("marty_verification")
    try:
        decoded = native.parse_master_list(normalize_der(master_list_data))
        return [_certificate_from_native(item) for item in decoded["certificates"]]
    except Exception as exc:
        raise NativeOperationError(
            f"Native Master List decoding failed: {exc}"
        ) from exc


def decode_certificate(certificate_data: bytes) -> Certificate:
    """Parse one PEM or DER certificate in Rust and map its public metadata."""

    native = require_backend("marty_verification")
    value = bytes(certificate_data)
    try:
        if value.lstrip().startswith(b"-----BEGIN CERTIFICATE-----"):
            der_bytes = bytes(native.certificate_pem_to_der(value.decode("ascii")))
        else:
            der_bytes = bytes(native.load_certificate_der(value))
        info = native.get_certificate_info(der_bytes)
        return Certificate(
            subject=info["subject"],
            issuer=info["issuer"],
            valid_from=_parse_native_datetime(info["not_before"]),
            valid_to=_parse_native_datetime(info["not_after"]),
            serial_number=info["serial_number"],
            certificate_data=der_bytes,
            country_code=_country_from_subject(info["subject"]) or "XXX",
        )
    except Exception as exc:
        raise NativeOperationError(
            f"Native certificate decoding failed: {exc}"
        ) from exc


def decode_signed_certificate_list(
    list_data: bytes,
    signer_certificate_der: bytes,
    *,
    label: str,
) -> list[Certificate]:
    """Verify and parse a signed CSCA or DSC list entirely through Rust."""

    native = require_backend("marty_verification")
    der_data = normalize_der(list_data)
    try:
        if not native.verify_master_list_signature(der_data, signer_certificate_der):
            raise NativeOperationError(f"{label} signature verification failed")
        decoded = native.parse_master_list(der_data)
        return [_certificate_from_native(item) for item in decoded["certificates"]]
    except NativeOperationError:
        raise
    except Exception as exc:
        raise NativeOperationError(f"Native {label} processing failed: {exc}") from exc


def decode_crl(
    crl_data: bytes,
) -> tuple[str, datetime, datetime, list[RevokedCertificate]]:
    """Map a Rust-parsed CRL to stable service DTOs."""

    native = require_backend("marty_verification")
    try:
        crl = native.parse_crl(normalize_der(crl_data))
        this_update = _parse_native_datetime(crl.this_update)
        next_update = _parse_native_datetime(crl.next_update)
        revoked = [
            RevokedCertificate(
                serial_number=item.serial_number,
                revocation_date=_parse_native_datetime(item.revocation_date),
                reason_code=_REASON_CODES.get(item.reason or ""),
            )
            for item in crl.revoked_certificates()
        ]
        return crl.issuer, this_update, next_update, revoked
    except Exception as exc:
        raise NativeOperationError(f"Native CRL decoding failed: {exc}") from exc


def validate_crl(crl_data: bytes, issuer_certificate_der: bytes) -> bytes:
    """Authenticate CRL evidence in Rust and return its normalized DER bytes."""

    native = require_backend("marty_verification")
    der_data = normalize_der(crl_data)
    try:
        native.validate_crl(der_data, issuer_certificate_der)
    except Exception as exc:
        raise NativeOperationError(f"Native CRL validation failed: {exc}") from exc
    return der_data


def unsigned_artifact_unavailable(label: str) -> NativeOperationError:
    """Return the stable fail-closed error for unsupported unsigned output."""

    return NativeOperationError(
        f"Unsigned {label} generation is disabled; use the native signed issuance path"
    )


def _certificate_from_native(item: dict) -> Certificate:
    return Certificate(
        id=uuid4(),
        subject=item["subject"],
        issuer=item["issuer"],
        valid_from=_parse_native_datetime(item["not_before"]),
        valid_to=_parse_native_datetime(item["not_after"]),
        serial_number=item["serial_number"],
        certificate_data=bytes(item["der_bytes"]),
        status=CertificateStatus.ACTIVE,
        country_code=item.get("country") or "XXX",
    )


def _parse_native_datetime(value: str | None) -> datetime:
    if not value:
        raise NativeOperationError("Native PKD result omitted a required timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise NativeOperationError(f"Invalid native timestamp: {value}") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _country_from_subject(subject: str) -> str | None:
    for component in subject.replace("/", ",").split(","):
        key, separator, value = component.strip().partition("=")
        if separator and key.upper() == "C":
            candidate = value.strip().upper()
            if len(candidate) == 2 and candidate.isalpha():
                return candidate
    return None


__all__ = [
    "decode_crl",
    "decode_certificate",
    "decode_master_list",
    "decode_signed_certificate_list",
    "normalize_der",
    "unsigned_artifact_unavailable",
    "validate_crl",
]
