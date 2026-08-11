"""
VDS-NC Data Models for Headers, Payloads, and Documents.

This module defines the Pydantic models for VDS-NC structures following
ICAO Doc 9303 Part 13 specifications.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any

from marty_common.native_backends import NativeOperationError
from pydantic import BaseModel, Field, field_validator

from .types import (
    BarcodeFormat,
    DocumentType,
    ErrorCorrectionLevel,
    SignatureAlgorithm,
    VDSNCVersion,
)


class VDSNCHeader(BaseModel):
    """VDS-NC header structure per Doc 9303 Part 13."""

    version: VDSNCVersion = Field(
        default=VDSNCVersion.V1_0, description="VDS-NC version"
    )
    doc_type: DocumentType = Field(..., description="Document type")
    issuing_country: str = Field(
        ..., min_length=3, max_length=3, description="3-letter country code"
    )
    signer_id: str = Field(..., max_length=512, description="Signer identifier")
    certificate_reference: str = Field(
        ..., max_length=16, description="Certificate reference"
    )
    native_header: str | None = Field(default=None, exclude=True, repr=False)

    @field_validator("issuing_country")
    @classmethod
    def validate_country_code(cls, v: str) -> str:
        """Validate country code format."""
        if not v.isalpha() or len(v) != 3:
            msg = "Country code must be 3 alphabetic characters"
            raise ValueError(msg)
        return v.upper()

    def to_canonical_string(self) -> str:
        """Return the header parsed or created by the native profile."""
        if self.native_header is None:
            raise NativeOperationError(
                "Canonical VDS-NC headers must be created or parsed by the Rust backend"
            )
        return self.native_header


class VDSNCSignatureInfo(BaseModel):
    """VDS-NC signature metadata."""

    algorithm: SignatureAlgorithm = Field(..., description="Signature algorithm")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Signature creation time",
    )
    key_id: str | None = Field(None, description="Key identifier")
    certificate_chain: list[str] | None = Field(None, description="Certificate chain")

    def get_creation_date_str(self) -> str:
        """Get creation date in YYMMDD format."""
        return self.created_at.strftime("%y%m%d")

    def get_creation_time_str(self) -> str:
        """Get creation time in HHMMSS format."""
        return self.created_at.strftime("%H%M%S")


class VDSNCPayload(BaseModel):
    """VDS-NC message payload structure."""

    header: VDSNCHeader = Field(..., description="VDS-NC header")
    message: dict[str, Any] = Field(..., description="Canonical document data")
    signature_info: VDSNCSignatureInfo = Field(..., description="Signature metadata")
    native_signing_input: str | None = Field(default=None, exclude=True, repr=False)

    def get_canonical_message(self) -> str:
        """Get canonical representation of message data."""
        from .canonicalization import VDSNCCanonicalizer

        return VDSNCCanonicalizer.canonicalize(self.message, self.header.doc_type)

    def get_signature_data(self) -> bytes:
        """Return the exact signing input supplied by the Rust profile."""
        if self.native_signing_input is None:
            raise NativeOperationError(
                "VDS-NC signing input must be created or parsed by the Rust backend"
            )
        return self.native_signing_input.encode("utf-8")


class VDSNCDocument(BaseModel):
    """Complete VDS-NC document with signature and barcode."""

    # Core VDS-NC data
    payload: VDSNCPayload = Field(..., description="VDS-NC payload")
    signature: str = Field(..., description="Base64-encoded signature")

    # Barcode generation
    barcode_format: BarcodeFormat = Field(..., description="Selected barcode format")
    error_correction: ErrorCorrectionLevel = Field(
        ..., description="Error correction level"
    )
    barcode_data: str = Field(..., description="Encoded barcode data")

    # Metadata
    document_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), description="Unique document ID"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Creation timestamp",
    )

    def verify_signature(self, public_key_pem: str) -> bool:
        """
        Verify VDS-NC signature.

        Args:
            public_key_pem: PEM-encoded public key

        Returns:
            True if signature is valid
        """
        from .native import verify_profile

        return bool(
            verify_profile(self.barcode_data, public_key_pem)["signature_valid"]
        )

    def validate_field_consistency(self, printed_values: dict[str, Any]) -> list[str]:
        """
        Perform strict field-by-field comparison to printed values.

        Args:
            printed_values: Values from printed document

        Returns:
            List of consistency errors (empty if consistent)
        """
        from .native import validate_profile

        result = validate_profile(self.barcode_data, printed_values=printed_values)
        return [str(error) for error in result["field_errors"]]

    def validate_expiry_and_dates(self) -> list[str]:
        """
        Validate expiry dates and temporal constraints.

        Returns:
            List of temporal validation errors
        """
        from .native import validate_profile

        result = validate_profile(self.barcode_data, evaluation_date=date.today())
        return [str(error) for error in result["temporal_errors"]]


class VDSNCVerificationResult(BaseModel):
    """Complete VDS-NC verification result."""

    # Overall result
    is_valid: bool = Field(..., description="Overall verification result")
    document: VDSNCDocument | None = Field(None, description="Verified document")
    verification_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # Detailed results
    signature_valid: bool = Field(
        default=False, description="Signature verification result"
    )
    field_consistency_valid: bool = Field(
        default=False, description="Field consistency result"
    )
    temporal_validity_ok: bool = Field(
        default=False, description="Date/expiry validation result"
    )
    canonicalization_ok: bool = Field(
        default=False, description="Canonicalization validation"
    )

    # Error details
    errors: list[str] = Field(default_factory=list, description="Verification errors")
    warnings: list[str] = Field(
        default_factory=list, description="Verification warnings"
    )

    # Additional details
    verification_details: dict[str, Any] = Field(
        default_factory=dict, description="Additional verification data"
    )
