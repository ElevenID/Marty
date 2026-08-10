"""
ASN.1 utilities for PKD service
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
from uuid import uuid4

from app.models.pkd_models import Certificate, CertificateStatus, RevokedCertificate

from marty_plugin.native_backends import NativeOperationError, require_backend


class ASN1Encoder:
    """
    Provides ASN.1 encoding functionality for PKD data structures according to ICAO Doc 9303 standards
    """

    @staticmethod
    def encode_master_list(certificates: list[Certificate]) -> bytes:
        """
        Encode a list of certificates as an ICAO CSCA Master List.

        The Master List is a CMS SignedData structure according to RFC 5652,
        containing a list of CSCA certificates.
        """
        raise NativeOperationError(
            "Unsigned Master List generation is disabled; use the native signed issuance path"
        )

    @staticmethod
    def encode_dsc_list(certificates: list[Certificate]) -> bytes:
        """
        Encode a list of certificates as an ICAO DSC List.

        The DSC List is structured similarly to the Master List.
        """
        # For the DSC list, we use the same structure as the Master List
        return ASN1Encoder.encode_master_list(certificates)

    @staticmethod
    def encode_crl(
        issuer: str,
        this_update: datetime,
        next_update: datetime,
        revoked_certs: list[RevokedCertificate],
    ) -> bytes:
        """
        Encode a Certificate Revocation List (CRL) according to RFC 5280.
        """
        raise NativeOperationError(
            "Unsigned CRL generation is disabled; use the native signed issuance path"
        )


class ASN1Decoder:
    """
    Provides ASN.1 decoding functionality for PKD data structures according to ICAO Doc 9303 standards
    """

    @staticmethod
    def decode_master_list(master_list_data: bytes) -> list[Certificate]:
        """
        Decode an ICAO CSCA Master List from ASN.1 DER encoding to a list of certificates.
        """
        native = require_backend("marty_verification")
        der_bytes = ASN1Decoder._pem_to_der(master_list_data)
        try:
            decoded = native.parse_master_list(der_bytes)
            return [
                Certificate(
                    id=uuid4(),
                    subject=item["subject"],
                    issuer=item["issuer"],
                    valid_from=ASN1Decoder._parse_native_datetime(item["not_before"]),
                    valid_to=ASN1Decoder._parse_native_datetime(item["not_after"]),
                    serial_number=item["serial_number"],
                    certificate_data=bytes(item["der_bytes"]),
                    status=CertificateStatus.ACTIVE,
                    country_code=item.get("country") or "XXX",
                )
                for item in decoded["certificates"]
            ]
        except Exception as exc:
            raise NativeOperationError(
                f"Native Master List decoding failed: {exc}"
            ) from exc

    @staticmethod
    def decode_dsc_list(dsc_list_data: bytes) -> list[Certificate]:
        """
        Decode an ICAO DSC List from ASN.1 DER encoding to a list of certificates.
        """
        # DSC list has the same structure as Master List
        return ASN1Decoder.decode_master_list(dsc_list_data)

    @staticmethod
    def decode_crl(
        crl_data: bytes,
    ) -> tuple[str, datetime, datetime, list[RevokedCertificate]]:
        """
        Decode a Certificate Revocation List (CRL) according to RFC 5280.
        """
        native = require_backend("marty_verification")
        der_bytes = ASN1Decoder._pem_to_der(crl_data)
        reason_codes = {
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
        try:
            crl = native.parse_crl(der_bytes)
            this_update = ASN1Decoder._parse_native_datetime(crl.this_update)
            next_update = ASN1Decoder._parse_native_datetime(crl.next_update)
            revoked = [
                RevokedCertificate(
                    serial_number=item.serial_number,
                    revocation_date=ASN1Decoder._parse_native_datetime(
                        item.revocation_date
                    ),
                    reason_code=reason_codes.get(item.reason or ""),
                )
                for item in crl.revoked_certificates()
            ]
            return crl.issuer, this_update, next_update, revoked
        except Exception as exc:
            raise NativeOperationError(f"Native CRL decoding failed: {exc}") from exc

    @staticmethod
    def _pem_to_der(data: bytes) -> bytes:
        if not data.startswith(b"-----BEGIN"):
            return data
        payload = b"".join(
            line.strip()
            for line in data.splitlines()
            if line and not line.startswith(b"-----")
        )
        try:
            return base64.b64decode(payload, validate=True)
        except Exception as exc:
            raise NativeOperationError(f"Invalid PEM payload: {exc}") from exc

    @staticmethod
    def _parse_native_datetime(value: str | None) -> datetime:
        if not value:
            raise NativeOperationError(
                "Native ASN.1 result omitted a required timestamp"
            )
        normalized = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise NativeOperationError(f"Invalid native timestamp: {value}") from exc
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
