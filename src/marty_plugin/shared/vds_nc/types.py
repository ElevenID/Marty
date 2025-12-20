"""
VDS-NC Core Types and Enumerations for ICAO Doc 9303 Part 13 Implementation.

This module defines the fundamental types and enumerations used throughout
the VDS-NC (Visible Digital Seal - Non-Constrained) implementation.
"""

from __future__ import annotations

from enum import Enum


class VDSNCVersion(str, Enum):
    """VDS-NC specification versions."""

    V1_0 = "1.0"
    V1_1 = "1.1"


class DocumentType(str, Enum):
    """Document types supported by VDS-NC."""

    CMC = "CMC"  # Crew Member Certificate
    MRV = "MRV"  # Machine Readable Visa
    E_VISA = "EVISA"  # Electronic Visa
    DTA = "DTA"  # Digital Travel Authorization
    TEMP_DOC = "TEMP"  # Temporary Travel Document


class SignatureAlgorithm(str, Enum):
    """Supported signature algorithms for VDS-NC."""

    ES256 = "ES256"  # ECDSA using P-256 and SHA-256
    ES384 = "ES384"  # ECDSA using P-384 and SHA-384
    ES512 = "ES512"  # ECDSA using P-521 and SHA-512
    PS256 = "PS256"  # RSASSA-PSS using SHA-256 and MGF1 with SHA-256


class BarcodeFormat(str, Enum):
    """Barcode formats for VDS-NC encoding."""

    QR_CODE = "QR"  # QR Code
    AZTEC = "AZTEC"  # Aztec Code
    DATA_MATRIX = "DM"  # Data Matrix
    PDF417 = "PDF417"  # PDF417


class ErrorCorrectionLevel(str, Enum):
    """Error correction levels for barcode generation."""

    LOW = "L"  # ~7% recovery
    MEDIUM = "M"  # ~15% recovery
    QUARTILE = "Q"  # ~25% recovery
    HIGH = "H"  # ~30% recovery


class VDSNCError(Exception):
    """Base exception for VDS-NC related errors."""


class CanonicalizeError(VDSNCError):
    """Exception raised during canonicalization."""


class SignatureError(VDSNCError):
    """Exception raised during signature operations."""


class VerificationError(VDSNCError):
    """Exception raised during verification."""
