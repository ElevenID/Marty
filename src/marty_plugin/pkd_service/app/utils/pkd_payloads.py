"""Utilities for parsing ICAO PKD payloads."""

from __future__ import annotations

import gzip
import io
import logging
import zipfile
from collections.abc import Iterator
from datetime import datetime

import asn1crypto.crl
import asn1crypto.pem
import asn1crypto.x509
from app.models.pkd_models import Certificate, RevokedCertificate
from app.utils.asn1_utils import ASN1Encoder
from marty_backend_common.crypto_bridge import (
    certificate_pem_to_der,
    get_certificate_info,
)

logger = logging.getLogger(__name__)


PAYLOAD_ROOT_LABEL = "payload"


def unwrap_pkd_payload(blob: bytes, label: str = PAYLOAD_ROOT_LABEL) -> list[tuple[str, bytes]]:
    """Recursively unwrap PKD payload containers into raw binary blobs."""

    results: list[tuple[str, bytes]] = []
    stack: list[tuple[str, bytes]] = [(label, blob)]
    seen: set[tuple[str, int]] = set()

    while stack:
        name, data = stack.pop()
        key = (name, len(data))
        if key in seen:
            continue
        seen.add(key)

        bio = io.BytesIO(data)

        if zipfile.is_zipfile(bio):
            try:
                with zipfile.ZipFile(bio) as archive:
                    for info in archive.infolist():
                        if info.is_dir():
                            continue
                        nested = archive.read(info)
                        stack.append((info.filename, nested))
                    continue
            except zipfile.BadZipFile as exc:  # pragma: no cover - logged for tracing
                logger.warning("Failed to unpack zip entry %s: %s", name, exc)

        if data.startswith(b"\x1f\x8b"):
            try:
                decompressed = gzip.decompress(data)
                stack.append((name, decompressed))
                continue
            except OSError as exc:  # pragma: no cover - logged for tracing
                logger.warning("Failed to decompress gzip payload %s: %s", name, exc)

        results.append((name, data))

    return results


def parse_certificate_payload(
    blob: bytes, *, source_hint: str = PAYLOAD_ROOT_LABEL
) -> list[Certificate]:
    """Decode the certificates embedded in a PKD payload."""

    certificates: dict[tuple[str, str], Certificate] = {}

    for _name, data in unwrap_pkd_payload(blob, source_hint):
        decoded = _decode_masterlist_like(data)
        if not decoded:
            decoded = _decode_raw_certificates(data)

        for cert in decoded:
            key = (cert.serial_number, cert.subject)
            certificates[key] = cert

    return list(certificates.values())


def parse_crl_payload(blob: bytes, *, source_hint: str = PAYLOAD_ROOT_LABEL) -> list[dict]:
    """Decode the CRLs embedded in a PKD payload."""

    crls: list[dict] = []
    for _name, data in unwrap_pkd_payload(blob, source_hint):
        crl_entry = _decode_single_crl(data)
        if crl_entry:
            crls.append(crl_entry)

    return crls


def _decode_masterlist_like(data: bytes) -> list[Certificate]:
    """Try interpreting data as an ICAO master list (CMS SignedData)."""

    # Late import avoids circular dependency with ASN1Decoder
    from app.utils.asn1_utils import ASN1Decoder

    try:
        certificates = ASN1Decoder.decode_master_list(data)
    except Exception as exc:  # pragma: no cover - defensive guard
        logger.debug("Master list decode failed: %s", exc)
        return []
    else:
        return certificates or []


def _decode_raw_certificates(data: bytes) -> list[Certificate]:
    """Decode loose PEM/DER encoded certificates."""

    certs: list[Certificate] = []

    try:
        text = data.decode("ascii")
    except UnicodeDecodeError:
        text = ""

    if "-----BEGIN CERTIFICATE-----" in text:
        for pem_block in _iterate_pem_blocks(text):
            try:
                der_bytes = certificate_pem_to_der(pem_block)
                certs.append(_convert_der_to_model(der_bytes))
            except Exception as exc:  # pragma: no cover - malformed block logged for diagnosis
                logger.debug("Failed to parse PEM certificate: %s", exc)
        return certs

    try:
        certs.append(_convert_der_to_model(data))
    except Exception:
        pass

    return certs


def _iterate_pem_blocks(text: str) -> Iterator[str]:
    """Yield PEM blocks from concatenated certificate text."""

    begin_marker = "-----BEGIN CERTIFICATE-----"
    end_marker = "-----END CERTIFICATE-----"
    start = 0

    while True:
        begin = text.find(begin_marker, start)
        if begin == -1:
            break
        end = text.find(end_marker, begin)
        if end == -1:
            break
        end += len(end_marker)
        yield text[begin:end]
        start = end


def _convert_der_to_model(der_bytes: bytes) -> Certificate:
    """Convert DER-encoded certificate into the PKD Certificate model."""

    # Get certificate info from Rust bindings
    cert_info = get_certificate_info(der_bytes)

    # Use asn1crypto for country code extraction
    asn1_cert = asn1crypto.x509.Certificate.load(der_bytes)
    country_code = ASN1Encoder.extract_country_code(asn1_cert.subject) or "XXX"

    # Parse ISO 8601 dates
    valid_from = datetime.fromisoformat(cert_info["not_before"].replace("Z", "+00:00"))
    valid_to = datetime.fromisoformat(cert_info["not_after"].replace("Z", "+00:00"))

    return Certificate(
        subject=cert_info["subject"],
        issuer=cert_info["issuer"],
        valid_from=valid_from,
        valid_to=valid_to,
        serial_number=cert_info["serial_number"],
        certificate_data=der_bytes,
        country_code=country_code,
    )


def _decode_single_crl(data: bytes) -> dict | None:
    """Decode a single CRL, returning a dictionary suitable for storage."""

    try:
        der_bytes = _ensure_der(data)
        crl = asn1crypto.crl.CertificateList.load(der_bytes)
        tbs_cert_list = crl["tbs_cert_list"]

        issuer = tbs_cert_list["issuer"].human_friendly
        this_update = tbs_cert_list["this_update"].native
        next_update_field = tbs_cert_list.get("next_update")
        next_update = next_update_field.native if next_update_field is not None else this_update

        revoked_entries: list[RevokedCertificate] = []
        for revoked in tbs_cert_list.get("revoked_certificates", []):
            serial = format(revoked["user_certificate"].native, "X")
            revocation_date = revoked["revocation_date"].native

            reason_code = None
            for extension in revoked.get("crl_entry_extensions", []):
                if extension["extn_id"].native == "crl_reason":
                    reason_code = extension["extn_value"].parsed.native
                    break

            revoked_entries.append(
                RevokedCertificate(
                    serial_number=serial,
                    revocation_date=revocation_date,
                    reason_code=reason_code,
                )
            )

        return {
            "issuer": issuer,
            "this_update": this_update,
            "next_update": next_update,
            "crl_data": der_bytes,
            "revoked_certificates": [
                {
                    "serial_number": entry.serial_number,
                    "revocation_date": entry.revocation_date,
                    "reason_code": entry.reason_code,
                }
                for entry in revoked_entries
            ],
        }

    except Exception as exc:  # pragma: no cover - handled by caller/logged for context
        logger.debug("Failed to decode CRL payload: %s", exc)
        return None


def _ensure_der(data: bytes) -> bytes:
    """Ensure payload is DER encoded, unwrapping PEM if needed."""

    if data.startswith(b"-----BEGIN"):
        _, _, der_bytes = asn1crypto.pem.unarmor(data)
        return der_bytes
    return data
