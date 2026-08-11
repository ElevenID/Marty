"""Compatibility service for the canonical Rust VDS-NC implementation."""

from __future__ import annotations

import uuid
from typing import Any

from marty_common.native_backends import NativeOperationError

from .models import (
    VDSNCDocument,
    VDSNCHeader,
    VDSNCPayload,
    VDSNCSignatureInfo,
    VDSNCVerificationResult,
)
from .native import (
    barcode_policy,
    inspect_profile,
    sign_profile,
    validate_profile,
    verify_profile,
)
from .types import (
    BarcodeFormat,
    DocumentType,
    ErrorCorrectionLevel,
    SignatureAlgorithm,
    SignatureError,
    VDSNCVersion,
    VerificationError,
)


def _required_mapping(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise NativeOperationError(
            f"Native VDS-NC result is missing object field '{name}'"
        )
    return value


def _required_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise NativeOperationError(
            f"Native VDS-NC result is missing text field '{name}'"
        )
    return value


def _document_from_native(
    barcode_data: str,
    inspection: dict[str, Any],
    *,
    barcode_format: str | None = None,
    error_correction: str | None = None,
    document_id: str | None = None,
    preferred_format: BarcodeFormat | None = None,
) -> VDSNCDocument:
    payload = _required_mapping(inspection.get("payload"), "payload").copy()
    metadata = _required_mapping(inspection.get("metadata"), "metadata")
    profile_metadata = _required_mapping(payload.pop("_vds", None), "payload._vds")
    if metadata != profile_metadata:
        raise NativeOperationError("Native VDS-NC metadata views are inconsistent")

    document_type = DocumentType(
        _required_text(metadata.get("documentType"), "documentType")
    )
    selected_format, selected_correction = barcode_policy(
        document_type.value,
        len(barcode_data.encode("utf-8")),
        preferred_format.value if preferred_format else None,
    )
    selected_format = barcode_format or selected_format
    selected_correction = error_correction or selected_correction

    header = VDSNCHeader(
        version=VDSNCVersion(_required_text(metadata.get("version"), "version")),
        doc_type=document_type,
        issuing_country=_required_text(inspection.get("country"), "country"),
        signer_id=_required_text(metadata.get("issuerId"), "issuerId"),
        certificate_reference=str(metadata.get("certificateReference") or ""),
        native_header=_required_text(inspection.get("header"), "header"),
    )
    signature_info = VDSNCSignatureInfo(
        algorithm=SignatureAlgorithm(
            _required_text(metadata.get("algorithm"), "algorithm")
        ),
        key_id=_required_text(metadata.get("keyId"), "keyId"),
        certificate_chain=None,
    )
    return VDSNCDocument(
        payload=VDSNCPayload(
            header=header,
            message=payload,
            signature_info=signature_info,
            native_signing_input=_required_text(
                inspection.get("signing_input"), "signing_input"
            ),
        ),
        signature=_required_text(inspection.get("signature_b64"), "signature_b64"),
        barcode_format=BarcodeFormat(selected_format),
        error_correction=ErrorCorrectionLevel(selected_correction),
        barcode_data=barcode_data,
        document_id=document_id or str(uuid.uuid4()),
    )


class VDSNCProcessor:
    """Preserve the service API while delegating all VDS-NC decisions to Rust."""

    def __init__(
        self,
        private_key_pem: str | None = None,
        public_keys: dict[str, str] | None = None,
        signer_id: str = "TESTSGN",
        certificate_reference: str = "TESTCERT001",
    ) -> None:
        self.private_key_pem = private_key_pem
        self.public_keys = public_keys or {}
        self.signer_id = signer_id
        self.certificate_reference = certificate_reference

    def create_vds_nc_document(
        self,
        doc_type: DocumentType,
        issuing_country: str,
        document_data: dict[str, Any],
        signature_algorithm: SignatureAlgorithm = SignatureAlgorithm.ES256,
        preferred_barcode_format: BarcodeFormat | None = None,
    ) -> VDSNCDocument:
        if not self.private_key_pem:
            raise SignatureError("Private key required for document creation")
        try:
            signed = sign_profile(
                private_key_pem=self.private_key_pem,
                signer_id=self.signer_id,
                certificate_reference=self.certificate_reference,
                document_type=doc_type.value,
                issuing_country=issuing_country,
                document_data=document_data,
                algorithm=signature_algorithm.value,
            )
            barcode_data = _required_text(signed.get("barcode_data"), "barcode_data")
            inspection = inspect_profile(barcode_data)
            return _document_from_native(
                barcode_data,
                inspection,
                document_id=str(signed.get("credential_id") or "") or None,
                preferred_format=preferred_barcode_format,
            )
        except NativeOperationError as exc:
            raise SignatureError(str(exc)) from exc

    def verify_vds_nc_document(
        self,
        barcode_data: str,
        printed_values: dict[str, Any] | None = None,
        verify_signature: bool = True,
    ) -> VDSNCVerificationResult:
        result = VDSNCVerificationResult(is_valid=False, document=None)
        try:
            inspection = inspect_profile(barcode_data)
            result.document = _document_from_native(barcode_data, inspection)
            signer_id = result.document.payload.header.signer_id
            public_key_pem = self.public_keys.get(signer_id)

            if verify_signature and public_key_pem:
                native = verify_profile(
                    barcode_data,
                    public_key_pem,
                    printed_values=printed_values,
                )
                result.signature_valid = bool(native["signature_valid"])
                result.is_valid = bool(native["is_valid"])
            else:
                native = validate_profile(barcode_data, printed_values=printed_values)
                result.signature_valid = False
                if verify_signature:
                    native["errors"].append(
                        f"Public key not found for signer: {signer_id}"
                    )
                else:
                    native["errors"].append(
                        "Digital signature verification was not requested"
                    )

            result.canonicalization_ok = bool(native["canonicalization_ok"])
            result.field_consistency_valid = bool(native["field_consistency_valid"])
            result.temporal_validity_ok = bool(native["temporal_validity_ok"])
            result.errors.extend(str(error) for error in native.get("errors", []))
            result.warnings.extend(
                str(warning) for warning in native.get("warnings", [])
            )
            result.verification_details["native_backend"] = "_marty_rs"
            result.verification_details["algorithm"] = native.get("algorithm")
        except NativeOperationError as exc:
            result.errors.append(str(exc))
        return result

    def _decode_barcode_data(self, barcode_data: str) -> VDSNCDocument:
        """Parse one barcode with the canonical native parser."""

        try:
            return _document_from_native(barcode_data, inspect_profile(barcode_data))
        except NativeOperationError as exc:
            raise VerificationError(str(exc)) from exc
