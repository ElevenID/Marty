"""
VDS-NC (Visible Digital Seal - Non-Constrained) Implementation.

This package implements ICAO Doc 9303 Part 13 VDS-NC standards for non-chip documents
including CMC, MRV/e-visa, and future travel documents.

Key Features:
- Canonical dataset generation with deterministic key ordering
- VDS-NC signature creation and verification
- Intelligent barcode format selection
- Complete verification protocol with field-by-field validation
- Clock/expiry checks and canonicalization drift detection
"""

from .barcode import VDSNCBarcodeSelector
from .canonicalization import VDSNCCanonicalizer
from .models import (
    VDSNCDocument,
    VDSNCHeader,
    VDSNCPayload,
    VDSNCSignatureInfo,
    VDSNCVerificationResult,
)
from .processor import VDSNCProcessor
from .types import (
    BarcodeFormat,
    CanonicalizeError,
    DocumentType,
    ErrorCorrectionLevel,
    SignatureAlgorithm,
    SignatureError,
    VDSNCError,
    VDSNCVersion,
    VerificationError,
)
from .visa_integration import (
    EnhancedVDSNCData,
    VisaVDSNCProcessor,
    convert_personal_data_to_vds_nc,
    convert_visa_data_to_vds_nc,
    upgrade_legacy_vds_nc_data,
)

__all__ = [
    "BarcodeFormat",
    "CanonicalizeError",
    "DocumentType",
    "EnhancedVDSNCData",
    "ErrorCorrectionLevel",
    "SignatureAlgorithm",
    "SignatureError",
    "VDSNCBarcodeSelector",
    "VDSNCCanonicalizer",
    "VDSNCDocument",
    "VDSNCError",
    "VDSNCHeader",
    "VDSNCPayload",
    "VDSNCProcessor",
    "VDSNCSignatureInfo",
    "VDSNCVerificationResult",
    "VDSNCVersion",
    "VerificationError",
    # Visa integration
    "VisaVDSNCProcessor",
    "convert_personal_data_to_vds_nc",
    "convert_visa_data_to_vds_nc",
    "upgrade_legacy_vds_nc_data",
]
