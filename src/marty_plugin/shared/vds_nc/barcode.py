"""Compatibility adapter for Rust-owned VDS-NC barcode policy."""

from __future__ import annotations

from marty_common.native_backends import NativeBackendError

from .native import barcode_policy, select_barcode_format
from .types import BarcodeFormat, DocumentType, ErrorCorrectionLevel, VDSNCError


class VDSNCBarcodeSelector:
    """Preserve the selector API while delegating all decisions to Rust."""

    @staticmethod
    def select_optimal_format(
        payload_size: int,
        error_correction: ErrorCorrectionLevel = ErrorCorrectionLevel.MEDIUM,
        preferred_format: BarcodeFormat | None = None,
        *,
        document_type: DocumentType | None = None,
    ) -> BarcodeFormat:
        del document_type
        try:
            selected = select_barcode_format(
                payload_size,
                error_correction.value,
                (
                    preferred_format.value
                    if preferred_format and preferred_format is not BarcodeFormat.PDF417
                    else None
                ),
            )
            return BarcodeFormat(selected)
        except (NativeBackendError, ValueError) as exc:
            raise VDSNCError(str(exc)) from exc

    @staticmethod
    def get_recommended_error_correction(
        doc_type: DocumentType,
    ) -> ErrorCorrectionLevel:
        try:
            _, correction = barcode_policy(doc_type.value, 0)
            return ErrorCorrectionLevel(correction)
        except (NativeBackendError, ValueError) as exc:
            raise VDSNCError(str(exc)) from exc
