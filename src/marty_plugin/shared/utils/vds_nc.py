"""Compatibility views and rendering for the Rust-owned VDS-NC profile.

Protocol encoding, parsing, canonicalization, signing, verification, field
comparison, temporal policy, and barcode selection live in ``marty-core``.
This module only maps legacy visa DTOs and renders QR images.
"""

from __future__ import annotations

import io
import time
from enum import Enum
from typing import Any, NoReturn

try:
    import qrcode
    from qrcode.image.styledpil import StyledPilImage
    from qrcode.image.styles.moduledrawers import RoundedModuleDrawer
except ImportError:
    qrcode = None

from marty_common.native_backends import NativeOperationError

from marty_plugin.shared.models.visa import VDSNCData, Visa
from marty_plugin.shared.vds_nc.native import (
    inspect_profile,
    validate_profile,
    verify_profile,
)
from marty_plugin.shared.vds_nc.processor import VDSNCProcessor
from marty_plugin.shared.vds_nc.types import (
    BarcodeFormat,
    DocumentType,
    SignatureAlgorithm,
)
from marty_plugin.shared.vds_nc.visa_integration import convert_visa_data_to_vds_nc


class VDSNCMessageType(str, Enum):
    """Legacy DTO labels retained for callers."""

    EMERGENCY_TRAVEL_DOCUMENT = "emergency_travel_document"
    PROOF_OF_TESTING = "proof_of_testing"
    PROOF_OF_VACCINATION = "proof_of_vaccination"
    DIGITAL_TRAVEL_AUTHORIZATION = "digital_travel_authorization"
    VISA = "visa"


def _retired_low_level(operation: str) -> NoReturn:
    raise NativeOperationError(
        f"Low-level Python VDS-NC {operation} is removed; use the canonical native "
        "profile operation"
    )


def _iso_date(value: object) -> object:
    if isinstance(value, str) and len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    return value


def _legacy_view(barcode_data: str) -> dict[str, Any]:
    inspected = inspect_profile(barcode_data)
    payload = dict(inspected["payload"])
    metadata = dict(payload.pop("_vds"))
    hidden = {"_barcode_data": barcode_data}
    validity: dict[str, Any] = {
        "from": _iso_date(payload.get("dateOfIssue")),
        "to": _iso_date(payload.get("dateOfExpiry")),
    }
    if payload.get("validFrom"):
        validity["valid_from"] = _iso_date(payload["validFrom"])
    if payload.get("validUntil"):
        validity["valid_until"] = _iso_date(payload["validUntil"])
    message: dict[str, Any] = {
        "doc": {
            "type": "V",
            "no": payload.get("documentNumber"),
            "iss": payload.get("issuingCountry"),
            "cat": payload.get("visaCategory"),
        },
        "subj": {
            "fn": payload.get("givenNames"),
            "gn": payload.get("surname"),
            "dob": _iso_date(payload.get("dateOfBirth")),
            "sex": payload.get("gender"),
            "nat": payload.get("nationality"),
        },
        "val": validity,
        "vis": {
            "poi": payload.get("placeOfIssue"),
            "entries": payload.get("numberOfEntries"),
            "duration": payload.get("durationOfStay"),
        },
        "pol": payload.get("policyConstraints"),
        "_canonical": payload,
        **hidden,
    }
    return {
        "header": {
            "ver": metadata["version"],
            "typ": "visa",
            "iss": metadata["issuerId"],
            "iat": payload.get("issuedAt"),
            "alg": metadata["algorithm"],
            **hidden,
        },
        "message": message,
        "_canonical": payload,
        **hidden,
    }


class VDSNCEncoder:
    """Legacy visa API backed by the canonical Rust signer."""

    @classmethod
    def create_header(
        cls,
        message_type: VDSNCMessageType,
        issuer: str,
        version: str = "1.0",
        algorithm: SignatureAlgorithm = SignatureAlgorithm.ES256,
    ) -> dict[str, Any]:
        return {
            "ver": version,
            "typ": message_type.value,
            "iss": issuer,
            "iat": int(time.time()),
            "alg": algorithm.value,
        }

    @classmethod
    def create_visa_message(cls, visa: Visa) -> dict[str, Any]:
        message = _legacy_view_from_claims(
            convert_visa_data_to_vds_nc(
                visa.document_data,
                visa.personal_data,
                DocumentType.E_VISA,
            )
        )
        if visa.policy_constraints:
            message["pol"] = visa.policy_constraints.model_dump(exclude_none=True)
        return message

    @classmethod
    def encode_cbor(cls, header: dict[str, Any], message: dict[str, Any]) -> NoReturn:
        del header, message
        _retired_low_level("CBOR encoding")

    @classmethod
    def create_signature_input(cls, cbor_data: bytes) -> NoReturn:
        del cbor_data
        _retired_low_level("signature-input construction")

    @classmethod
    def sign_data(
        cls,
        signature_input: bytes,
        private_key_pem: str,
        algorithm: SignatureAlgorithm = SignatureAlgorithm.ES256,
    ) -> NoReturn:
        del signature_input, private_key_pem, algorithm
        _retired_low_level("detached signing")

    @classmethod
    def encode_vds_nc(
        cls,
        visa: Visa,
        issuer: str,
        private_key_pem: str,
        algorithm: SignatureAlgorithm = SignatureAlgorithm.ES256,
        certificate_pem: str | None = None,
    ) -> VDSNCData:
        claims = convert_visa_data_to_vds_nc(
            visa.document_data,
            visa.personal_data,
            DocumentType.E_VISA,
        )
        claims["issuedAt"] = int(time.time())
        if visa.policy_constraints:
            claims["policyConstraints"] = visa.policy_constraints.model_dump(
                exclude_none=True
            )
        processor = VDSNCProcessor(
            private_key_pem=private_key_pem,
            signer_id=issuer,
            certificate_reference="EMBEDDED_CERT" if certificate_pem else "VISAKEY",
        )
        document = processor.create_vds_nc_document(
            DocumentType.E_VISA,
            visa.document_data.issuing_state,
            claims,
            algorithm,
        )
        view = _legacy_view(document.barcode_data)
        return VDSNCData(
            header=view["header"],
            message=view["message"],
            signature=document.signature,
            barcode_data=document.barcode_data,
            barcode_format=document.barcode_format.value,
            issuer_certificate=certificate_pem,
            signature_algorithm=algorithm.value,
            certificate_chain=None,
        )


def _legacy_view_from_claims(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "doc": {
            "type": "V",
            "no": payload.get("documentNumber"),
            "iss": payload.get("issuingCountry"),
            "cat": payload.get("visaCategory"),
        },
        "subj": {
            "fn": payload.get("givenNames"),
            "gn": payload.get("surname"),
            "dob": _iso_date(payload.get("dateOfBirth")),
            "sex": payload.get("gender"),
            "nat": payload.get("nationality"),
        },
        "val": {
            "from": _iso_date(payload.get("dateOfIssue")),
            "to": _iso_date(payload.get("dateOfExpiry")),
        },
        "vis": {
            "poi": payload.get("placeOfIssue"),
            "entries": payload.get("numberOfEntries"),
            "duration": payload.get("durationOfStay"),
        },
    }


class VDSNCDecoder:
    """Legacy decoded view backed by the canonical Rust parser/verifier."""

    @classmethod
    def decode_cbor(cls, cbor_data: bytes) -> NoReturn:
        del cbor_data
        _retired_low_level("CBOR decoding")

    @classmethod
    def verify_signature(
        cls,
        signature_input: bytes,
        signature: bytes,
        public_key_pem: str,
        algorithm: SignatureAlgorithm = SignatureAlgorithm.ES256,
    ) -> NoReturn:
        del signature_input, signature, public_key_pem, algorithm
        _retired_low_level("detached verification")

    @classmethod
    def decode_vds_nc(
        cls,
        barcode_data: str,
        public_key_pem: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        decoded = _legacy_view(barcode_data)
        if public_key_pem is None:
            return decoded, False
        verified = verify_profile(barcode_data, public_key_pem)
        return decoded, bool(verified["signature_valid"])


class BarcodeGenerator:
    """Render canonical barcode data; rendering remains an integration concern."""

    @classmethod
    def generate_qr_code(
        cls,
        data: str,
        error_correction: str = "M",
        border: int = 4,
        box_size: int = 10,
    ) -> bytes | None:
        if qrcode is None:
            return None
        error_levels = {
            "L": qrcode.constants.ERROR_CORRECT_L,
            "M": qrcode.constants.ERROR_CORRECT_M,
            "Q": qrcode.constants.ERROR_CORRECT_Q,
            "H": qrcode.constants.ERROR_CORRECT_H,
        }
        qr = qrcode.QRCode(
            error_correction=error_levels.get(
                error_correction, qrcode.constants.ERROR_CORRECT_M
            ),
            box_size=box_size,
            border=border,
        )
        qr.add_data(data)
        qr.make(fit=True)
        image = qr.make_image(fill_color="black", back_color="white")
        output = io.BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()

    @classmethod
    def generate_styled_qr_code(
        cls,
        data: str,
        logo_path: str | None = None,
        fill_color: str = "black",
        back_color: str = "white",
    ) -> bytes | None:
        if qrcode is None:
            return None
        qr = qrcode.QRCode(
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)
        image = qr.make_image(
            image_factory=StyledPilImage,
            module_drawer=RoundedModuleDrawer(),
            fill_color=fill_color,
            back_color=back_color,
        )
        if logo_path:
            from PIL import Image

            logo = Image.open(logo_path)
            qr_width, qr_height = image.size
            logo_size = min(qr_width, qr_height) // 10
            resized_logo = logo.resize((logo_size, logo_size), Image.Resampling.LANCZOS)
            image.paste(
                resized_logo,
                ((qr_width - logo_size) // 2, (qr_height - logo_size) // 2),
            )
        output = io.BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()


class VDSNCValidator:
    """Compatibility validation views whose decisions come from Rust."""

    @classmethod
    def validate_header(cls, header: dict[str, Any]) -> list[str]:
        barcode_data = header.get("_barcode_data")
        if not isinstance(barcode_data, str):
            return [
                "VDS_NC.NATIVE_CONTEXT_REQUIRED: header was not produced by native parsing"
            ]
        validate_profile(barcode_data)
        return []

    @classmethod
    def validate_visa_message(cls, message: dict[str, Any]) -> list[str]:
        barcode_data = message.get("_barcode_data")
        if not isinstance(barcode_data, str):
            return [
                "VDS_NC.NATIVE_CONTEXT_REQUIRED: message was not produced by native parsing"
            ]
        result = validate_profile(barcode_data)
        return [str(error) for error in result["temporal_errors"]]

    @classmethod
    def validate_field_consistency(
        cls,
        vds_nc_data: dict[str, Any],
        visa: Visa | None = None,
    ) -> list[str]:
        if visa is None:
            return []
        barcode_data = vds_nc_data.get("_barcode_data")
        if not isinstance(barcode_data, str):
            return [
                "VDS_NC.NATIVE_CONTEXT_REQUIRED: data was not produced by native parsing"
            ]
        printed = convert_visa_data_to_vds_nc(
            visa.document_data,
            visa.personal_data,
            DocumentType.E_VISA,
        )
        result = validate_profile(barcode_data, printed_values=printed)
        return [str(error) for error in result["field_errors"]]


__all__ = [
    "BarcodeFormat",
    "BarcodeGenerator",
    "SignatureAlgorithm",
    "VDSNCDecoder",
    "VDSNCEncoder",
    "VDSNCMessageType",
    "VDSNCValidator",
]
