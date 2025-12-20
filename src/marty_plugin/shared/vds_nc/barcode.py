"""
VDS-NC Barcode Format Selection and Generation.

This module implements intelligent barcode format selection based on payload size
and error correction requirements for optimal print/scan survival per Doc 9303 Part 13.
"""

from __future__ import annotations

from .types import BarcodeFormat, DocumentType, ErrorCorrectionLevel


class VDSNCBarcodeSelector:
    """
    Intelligent barcode format selection based on payload size and requirements.

    Follows Doc 9303 Part 13 guidance for optimal print/scan survival.
    """

    # Size thresholds for different barcode formats (approximate characters)
    SIZE_THRESHOLDS = {
        BarcodeFormat.QR_CODE: {
            ErrorCorrectionLevel.LOW: 2953,
            ErrorCorrectionLevel.MEDIUM: 2331,
            ErrorCorrectionLevel.QUARTILE: 1663,
            ErrorCorrectionLevel.HIGH: 1273,
        },
        BarcodeFormat.AZTEC: {
            ErrorCorrectionLevel.LOW: 3832,
            ErrorCorrectionLevel.MEDIUM: 3067,
            ErrorCorrectionLevel.QUARTILE: 2293,
            ErrorCorrectionLevel.HIGH: 1914,
        },
        BarcodeFormat.DATA_MATRIX: {
            ErrorCorrectionLevel.LOW: 2335,  # Simplified - Data Matrix uses Reed-Solomon
            ErrorCorrectionLevel.MEDIUM: 2335,
            ErrorCorrectionLevel.QUARTILE: 2335,
            ErrorCorrectionLevel.HIGH: 2335,
        },
    }

    @staticmethod
    def select_optimal_format(
        payload_size: int,
        error_correction: ErrorCorrectionLevel = ErrorCorrectionLevel.MEDIUM,
        preferred_format: BarcodeFormat | None = None,
    ) -> BarcodeFormat:
        """
        Select optimal barcode format based on payload size and requirements.

        Args:
            payload_size: Size of payload in characters
            error_correction: Required error correction level
            preferred_format: Preferred format if size allows

        Returns:
            Optimal barcode format
        """
        # Check if preferred format can handle the payload
        if preferred_format and preferred_format in VDSNCBarcodeSelector.SIZE_THRESHOLDS:
            threshold = VDSNCBarcodeSelector.SIZE_THRESHOLDS[preferred_format].get(
                error_correction, 0
            )
            if payload_size <= threshold:
                return preferred_format

        # Find best format that can handle the payload
        best_format = BarcodeFormat.QR_CODE  # Default fallback

        for format_type, thresholds in VDSNCBarcodeSelector.SIZE_THRESHOLDS.items():
            threshold = thresholds.get(error_correction, 0)
            if payload_size <= threshold:
                # Prefer QR Code for most applications due to widespread support
                if format_type == BarcodeFormat.QR_CODE:
                    return format_type
                best_format = format_type

        return best_format

    @staticmethod
    def get_recommended_error_correction(doc_type: DocumentType) -> ErrorCorrectionLevel:
        """
        Get recommended error correction level for document type.

        Args:
            doc_type: Document type

        Returns:
            Recommended error correction level
        """
        # High-security documents need higher error correction
        if doc_type in [DocumentType.CMC, DocumentType.E_VISA]:
            return ErrorCorrectionLevel.HIGH
        if doc_type == DocumentType.MRV:
            return ErrorCorrectionLevel.QUARTILE
        return ErrorCorrectionLevel.MEDIUM
