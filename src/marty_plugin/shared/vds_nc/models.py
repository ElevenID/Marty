"""
VDS-NC Data Models for Headers, Payloads, and Documents.

This module defines the Pydantic models for VDS-NC structures following
ICAO Doc 9303 Part 13 specifications.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

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

    version: VDSNCVersion = Field(default=VDSNCVersion.V1_0, description="VDS-NC version")
    doc_type: DocumentType = Field(..., description="Document type")
    issuing_country: str = Field(
        ..., min_length=3, max_length=3, description="3-letter country code"
    )
    signer_id: str = Field(..., max_length=16, description="Signer identifier")
    certificate_reference: str = Field(..., max_length=16, description="Certificate reference")

    @field_validator("issuing_country")
    @classmethod
    def validate_country_code(cls, v: str) -> str:
        """Validate country code format."""
        if not v.isalpha() or len(v) != 3:
            msg = "Country code must be 3 alphabetic characters"
            raise ValueError(msg)
        return v.upper()

    def to_canonical_string(self) -> str:
        """Convert to canonical header string."""
        return f"DC{self.version.value}{self.doc_type.value}{self.issuing_country}{self.signer_id}"


class VDSNCSignatureInfo(BaseModel):
    """VDS-NC signature metadata."""

    algorithm: SignatureAlgorithm = Field(..., description="Signature algorithm")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Signature creation time"
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

    def get_canonical_message(self) -> str:
        """Get canonical representation of message data."""
        from .canonicalization import VDSNCCanonicalizer

        return VDSNCCanonicalizer.canonicalize(self.message, self.header.doc_type)

    def get_signature_data(self) -> bytes:
        """Get data that should be signed (header + canonical message)."""
        header_str = self.header.to_canonical_string()
        canonical_message = self.get_canonical_message()
        sign_data = header_str + canonical_message
        return sign_data.encode("utf-8")


class VDSNCDocument(BaseModel):
    """Complete VDS-NC document with signature and barcode."""

    # Core VDS-NC data
    payload: VDSNCPayload = Field(..., description="VDS-NC payload")
    signature: str = Field(..., description="Base64-encoded signature")

    # Barcode generation
    barcode_format: BarcodeFormat = Field(..., description="Selected barcode format")
    error_correction: ErrorCorrectionLevel = Field(..., description="Error correction level")
    barcode_data: str = Field(..., description="Encoded barcode data")

    # Metadata
    document_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), description="Unique document ID"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Creation timestamp"
    )

    def verify_signature(self, public_key_pem: str) -> bool:
        """
        Verify VDS-NC signature.

        Args:
            public_key_pem: PEM-encoded public key

        Returns:
            True if signature is valid
        """
        try:
            import base64

            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import ec

            # Load public key
            public_key = serialization.load_pem_public_key(public_key_pem.encode())

            # Get signature data
            signature_data = self.payload.get_signature_data()
            signature_bytes = base64.b64decode(self.signature)

            # Verify signature based on algorithm
            algorithm = self.payload.signature_info.algorithm
            if algorithm == SignatureAlgorithm.ES256:
                public_key.verify(signature_bytes, signature_data, ec.ECDSA(hashes.SHA256()))
            elif algorithm == SignatureAlgorithm.ES384:
                public_key.verify(signature_bytes, signature_data, ec.ECDSA(hashes.SHA384()))
            elif algorithm == SignatureAlgorithm.ES512:
                public_key.verify(signature_bytes, signature_data, ec.ECDSA(hashes.SHA512()))
            else:
                return False
        except Exception:
            return False
        else:
            return True

    def validate_field_consistency(self, printed_values: dict[str, Any]) -> list[str]:
        """
        Perform strict field-by-field comparison to printed values.

        Args:
            printed_values: Values from printed document

        Returns:
            List of consistency errors (empty if consistent)
        """
        errors = []
        message_data = self.payload.message

        for key, printed_value in printed_values.items():
            vds_value = message_data.get(key)

            if vds_value is None:
                errors.append(f"Field '{key}' missing in VDS-NC data")
                continue

            # Normalize values for comparison
            if isinstance(printed_value, str):
                printed_value = printed_value.strip().upper()
            if isinstance(vds_value, str):
                vds_value = vds_value.strip().upper()

            if printed_value != vds_value:
                errors.append(
                    f"Field '{key}' mismatch: printed='{printed_value}', VDS-NC='{vds_value}'"
                )

        return errors

    def validate_expiry_and_dates(self) -> list[str]:
        """
        Validate expiry dates and temporal constraints.

        Returns:
            List of temporal validation errors
        """
        errors = []
        now = datetime.now(timezone.utc).date()
        message_data = self.payload.message

        # Parse dates
        try:
            if "dateOfIssue" in message_data:
                issue_date = datetime.strptime(message_data["dateOfIssue"], "%Y%m%d").date()
                if now < issue_date:
                    errors.append("Document not yet valid (before issue date)")

            if "dateOfExpiry" in message_data:
                expiry_date = datetime.strptime(message_data["dateOfExpiry"], "%Y%m%d").date()
                if now > expiry_date:
                    errors.append("Document expired")

            if "validFrom" in message_data:
                valid_from = datetime.strptime(message_data["validFrom"], "%Y%m%d").date()
                if now < valid_from:
                    errors.append("Document not yet valid (before valid from date)")

            if "validUntil" in message_data:
                valid_until = datetime.strptime(message_data["validUntil"], "%Y%m%d").date()
                if now > valid_until:
                    errors.append("Document validity period ended")

        except ValueError as e:
            errors.append(f"Date parsing error: {e}")

        return errors


class VDSNCVerificationResult(BaseModel):
    """Complete VDS-NC verification result."""

    # Overall result
    is_valid: bool = Field(..., description="Overall verification result")
    document: VDSNCDocument | None = Field(None, description="Verified document")
    verification_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Detailed results
    signature_valid: bool = Field(default=False, description="Signature verification result")
    field_consistency_valid: bool = Field(default=False, description="Field consistency result")
    temporal_validity_ok: bool = Field(default=False, description="Date/expiry validation result")
    canonicalization_ok: bool = Field(default=False, description="Canonicalization validation")

    # Error details
    errors: list[str] = Field(default_factory=list, description="Verification errors")
    warnings: list[str] = Field(default_factory=list, description="Verification warnings")

    # Additional details
    verification_details: dict[str, Any] = Field(
        default_factory=dict, description="Additional verification data"
    )
