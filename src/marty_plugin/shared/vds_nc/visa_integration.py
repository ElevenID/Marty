"""
Visa VDS-NC Integration Module.

This module extends the visa models to support VDS-NC profiles for e-visa and MRV documents,
providing seamless integration with the VDS-NC verification protocol.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from marty_plugin.shared.models.visa import PersonalData, VDSNCData, VisaDocumentData
from marty_plugin.shared.vds_nc import (
    BarcodeFormat,
    DocumentType,
    SignatureAlgorithm,
    VDSNCDocument,
    VDSNCProcessor,
    VDSNCVerificationResult,
)


def convert_personal_data_to_vds_nc(personal_data: PersonalData) -> dict[str, Any]:
    """Convert PersonalData to VDS-NC canonical format."""
    return {
        "surname": personal_data.surname,
        "givenNames": personal_data.given_names,
        "nationality": personal_data.nationality,
        "dateOfBirth": personal_data.date_of_birth.strftime("%Y%m%d"),
        "gender": personal_data.gender.value,
    }


def _add_e_visa_fields(vds_data: dict[str, Any], document_data: VisaDocumentData) -> None:
    """Add E-VISA specific fields to VDS data."""
    vds_data.update(
        {
            "docType": "EVISA",
            "issuingCountry": document_data.issuing_state,
            "documentNumber": document_data.document_number,
            "visaCategory": document_data.visa_category.value,
            "dateOfIssue": document_data.date_of_issue.strftime("%Y%m%d"),
            "dateOfExpiry": document_data.date_of_expiry.strftime("%Y%m%d"),
        }
    )

    # Optional fields
    if document_data.valid_from:
        vds_data["validFrom"] = document_data.valid_from.strftime("%Y%m%d")
    if document_data.valid_until:
        vds_data["validUntil"] = document_data.valid_until.strftime("%Y%m%d")
    if document_data.number_of_entries:
        vds_data["numberOfEntries"] = document_data.number_of_entries
    if document_data.place_of_issue:
        vds_data["placeOfIssue"] = document_data.place_of_issue


def _add_mrv_fields(vds_data: dict[str, Any], document_data: VisaDocumentData) -> None:
    """Add MRV specific fields to VDS data."""
    vds_data.update(
        {
            "docType": "V",
            "issuingCountry": document_data.issuing_state,
            "documentNumber": document_data.document_number,
            "visaCategory": document_data.visa_category.value,
            "dateOfIssue": document_data.date_of_issue.strftime("%Y%m%d"),
            "dateOfExpiry": document_data.date_of_expiry.strftime("%Y%m%d"),
        }
    )

    # Optional fields for MRV
    if document_data.valid_from:
        vds_data["validFrom"] = document_data.valid_from.strftime("%Y%m%d")
    if document_data.valid_until:
        vds_data["validUntil"] = document_data.valid_until.strftime("%Y%m%d")
    if document_data.number_of_entries:
        vds_data["numberOfEntries"] = document_data.number_of_entries
    if document_data.duration_of_stay:
        vds_data["durationOfStay"] = document_data.duration_of_stay
    if document_data.place_of_issue:
        vds_data["placeOfIssue"] = document_data.place_of_issue


def convert_visa_data_to_vds_nc(
    document_data: VisaDocumentData,
    personal_data: PersonalData,
    doc_type: DocumentType = DocumentType.E_VISA,
) -> dict[str, Any]:
    """Convert visa data to VDS-NC canonical format."""
    vds_data = convert_personal_data_to_vds_nc(personal_data)

    # Add document-specific fields based on type
    if doc_type == DocumentType.E_VISA:
        _add_e_visa_fields(vds_data, document_data)
    elif doc_type == DocumentType.MRV:
        _add_mrv_fields(vds_data, document_data)

    return vds_data


class VisaVDSNCProcessor:
    """VDS-NC processor specifically for visa documents."""

    def __init__(
        self,
        private_key_pem: str | None = None,
        public_keys: dict[str, str] | None = None,
        signer_id: str = "VISASGN",
        certificate_reference: str = "VISACERT001",
    ) -> None:
        """Initialize visa VDS-NC processor."""
        self.processor = VDSNCProcessor(
            private_key_pem=private_key_pem,
            public_keys=public_keys,
            signer_id=signer_id,
            certificate_reference=certificate_reference,
        )

    def create_visa_vds_nc(
        self,
        document_data: VisaDocumentData,
        personal_data: PersonalData,
        doc_type: DocumentType = DocumentType.E_VISA,
        signature_algorithm: SignatureAlgorithm = SignatureAlgorithm.ES256,
        preferred_barcode_format: BarcodeFormat | None = None,
    ) -> VDSNCDocument:
        """
        Create VDS-NC document for visa.

        Args:
            document_data: Visa document data
            personal_data: Personal data
            doc_type: Document type (E_VISA or MRV)
            signature_algorithm: Signature algorithm
            preferred_barcode_format: Preferred barcode format

        Returns:
            VDS-NC document with visa data
        """
        # Convert visa data to VDS-NC format
        vds_data = convert_visa_data_to_vds_nc(document_data, personal_data, doc_type)

        return self.processor.create_vds_nc_document(
            doc_type=doc_type,
            issuing_country=document_data.issuing_state,
            document_data=vds_data,
            signature_algorithm=signature_algorithm,
            preferred_barcode_format=preferred_barcode_format,
        )

    def verify_visa_vds_nc(
        self,
        barcode_data: str,
        printed_visa_data: dict[str, Any] | None = None,
        verify_signature: bool = True,
    ) -> VDSNCVerificationResult:
        """
        Verify visa VDS-NC document.

        Args:
            barcode_data: VDS-NC barcode data
            printed_visa_data: Printed visa data for comparison
            verify_signature: Whether to verify digital signature

        Returns:
            Verification result
        """
        return self.processor.verify_vds_nc_document(
            barcode_data=barcode_data,
            printed_values=printed_visa_data,
            verify_signature=verify_signature,
        )

    def extract_visa_data_from_vds_nc(self, document: VDSNCDocument) -> dict[str, Any]:
        """
        Extract visa data from VDS-NC document in a visa-friendly format.

        Args:
            document: VDS-NC document

        Returns:
            Visa data dictionary
        """
        message_data = document.payload.message

        # Convert back to visa format
        visa_data = {
            "document_number": message_data.get("documentNumber"),
            "document_type": message_data.get("docType"),
            "issuing_state": message_data.get("issuingCountry"),
            "surname": message_data.get("surname"),
            "given_names": message_data.get("givenNames"),
            "nationality": message_data.get("nationality"),
            "gender": message_data.get("gender"),
            "visa_category": message_data.get("visaCategory"),
        }

        # Convert date strings back to date objects
        if message_data.get("dateOfBirth"):
            visa_data["date_of_birth"] = date.fromisoformat(
                f"{message_data['dateOfBirth'][:4]}-{message_data['dateOfBirth'][4:6]}-{message_data['dateOfBirth'][6:8]}"
            )

        if message_data.get("dateOfIssue"):
            visa_data["date_of_issue"] = date.fromisoformat(
                f"{message_data['dateOfIssue'][:4]}-{message_data['dateOfIssue'][4:6]}-{message_data['dateOfIssue'][6:8]}"
            )

        if message_data.get("dateOfExpiry"):
            visa_data["date_of_expiry"] = date.fromisoformat(
                f"{message_data['dateOfExpiry'][:4]}-{message_data['dateOfExpiry'][4:6]}-{message_data['dateOfExpiry'][6:8]}"
            )

        # Optional fields
        for field in ["validFrom", "validUntil"]:
            if message_data.get(field):
                date_str = message_data[field]
                visa_data[field.lower()] = date.fromisoformat(
                    f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                )

        for field in ["numberOfEntries", "durationOfStay", "placeOfIssue", "purposeOfTravel"]:
            if message_data.get(field):
                visa_data[field.lower()] = message_data[field]

        return visa_data


class EnhancedVDSNCData(BaseModel):
    """Enhanced VDS-NC data model for visa integration."""

    # Core VDS-NC document
    vds_nc_document: VDSNCDocument = Field(..., description="VDS-NC document")

    # Verification status
    last_verification: VDSNCVerificationResult | None = Field(
        None, description="Last verification result"
    )

    # Visa-specific metadata
    visa_type: DocumentType = Field(default=DocumentType.E_VISA, description="Visa document type")

    # Legacy compatibility fields (derived from VDS-NC data)
    @property
    def header(self) -> dict[str, Any]:
        """Legacy header format for compatibility."""
        return {
            "version": self.vds_nc_document.payload.header.version.value,
            "doc_type": self.vds_nc_document.payload.header.doc_type.value,
            "issuing_country": self.vds_nc_document.payload.header.issuing_country,
            "signer_id": self.vds_nc_document.payload.header.signer_id,
            "certificate_reference": self.vds_nc_document.payload.header.certificate_reference,
        }

    @property
    def message(self) -> dict[str, Any]:
        """VDS-NC message payload."""
        return self.vds_nc_document.payload.message

    @property
    def signature(self) -> str:
        """Base64-encoded signature."""
        return self.vds_nc_document.signature

    @property
    def barcode_data(self) -> str:
        """Encoded barcode data."""
        return self.vds_nc_document.barcode_data

    @property
    def barcode_format(self) -> str:
        """Barcode format."""
        return self.vds_nc_document.barcode_format.value

    @property
    def signature_algorithm(self) -> str:
        """Signature algorithm."""
        return self.vds_nc_document.payload.signature_info.algorithm.value

    def verify_with_public_key(self, public_key_pem: str) -> bool:
        """Verify signature with public key."""
        return self.vds_nc_document.verify_signature(public_key_pem)

    def validate_field_consistency(self, printed_values: dict[str, Any]) -> list[str]:
        """Validate field consistency with printed values."""
        return self.vds_nc_document.validate_field_consistency(printed_values)

    def validate_expiry_and_dates(self) -> list[str]:
        """Validate expiry dates and temporal constraints."""
        return self.vds_nc_document.validate_expiry_and_dates()


def upgrade_legacy_vds_nc_data(_legacy_data: VDSNCData) -> EnhancedVDSNCData | None:
    """
    Upgrade legacy VDSNCData to enhanced format.

    Args:
        _legacy_data: Legacy VDS-NC data (currently unused)

    Returns:
        Enhanced VDS-NC data or None if conversion fails
    """
    try:
        # This would require parsing the legacy barcode_data and reconstructing
        # the VDSNCDocument. For now, return None to indicate upgrade needed.
        return None
    except (ValueError, TypeError):
        return None
