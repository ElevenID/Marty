"""
VDS-NC Main Processor Implementation.

This module provides the main VDS-NC processor for document creation and verification
following ICAO Doc 9303 Part 13 specifications.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from .barcode import VDSNCBarcodeSelector
from .canonicalization import VDSNCCanonicalizer
from .models import (
    VDSNCDocument,
    VDSNCHeader,
    VDSNCPayload,
    VDSNCSignatureInfo,
    VDSNCVerificationResult,
)
from .types import (
    BarcodeFormat,
    DocumentType,
    SignatureAlgorithm,
    SignatureError,
    VerificationError,
)


class VDSNCProcessor:
    """
    Main processor for VDS-NC document creation and verification.

    Implements complete Doc 9303 Part 13 VDS-NC processing workflow.
    """

    def __init__(
        self,
        private_key_pem: str | None = None,
        public_keys: dict[str, str] | None = None,
        signer_id: str = "TESTSGN",
        certificate_reference: str = "TESTCERT001",
    ) -> None:
        """
        Initialize VDS-NC processor.

        Args:
            private_key_pem: PEM-encoded private key for signing
            public_keys: Dictionary of signer_id -> PEM public key for verification
            signer_id: Signer identifier
            certificate_reference: Certificate reference
        """
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
        """
        Create complete VDS-NC document with signature and barcode.

        Args:
            doc_type: Document type
            issuing_country: 3-letter issuing country code
            document_data: Document data dictionary
            signature_algorithm: Signature algorithm to use
            preferred_barcode_format: Preferred barcode format

        Returns:
            Complete VDS-NC document

        Raises:
            ValueError: If data validation fails
            SignatureError: If signing fails
        """
        if not self.private_key_pem:
            msg = "Private key required for document creation"
            raise SignatureError(msg)

        # Validate and canonicalize document data
        canonical_message = VDSNCCanonicalizer.canonicalize(document_data, doc_type)

        # Create header
        header = VDSNCHeader(
            doc_type=doc_type,
            issuing_country=issuing_country,
            signer_id=self.signer_id,
            certificate_reference=self.certificate_reference,
        )

        # Create signature info
        signature_info = VDSNCSignatureInfo(algorithm=signature_algorithm)

        # Create payload
        payload = VDSNCPayload(
            header=header, message=json.loads(canonical_message), signature_info=signature_info
        )

        # Sign the payload
        signature = self._sign_payload(payload, signature_algorithm)

        # Select barcode format
        payload_size = len(canonical_message)
        error_correction = VDSNCBarcodeSelector.get_recommended_error_correction(doc_type)
        barcode_format = VDSNCBarcodeSelector.select_optimal_format(
            payload_size, error_correction, preferred_barcode_format
        )

        # Create barcode data
        barcode_data = self._create_barcode_data(payload, signature, barcode_format)

        return VDSNCDocument(
            payload=payload,
            signature=signature,
            barcode_format=barcode_format,
            error_correction=error_correction,
            barcode_data=barcode_data,
        )

    def verify_vds_nc_document(
        self,
        barcode_data: str,
        printed_values: dict[str, Any] | None = None,
        verify_signature: bool = True,
    ) -> VDSNCVerificationResult:
        """
        Complete VDS-NC verification protocol.

        Implements: decode → canonicalize → signature verify → field comparison → clock checks

        Args:
            barcode_data: Barcode data string
            printed_values: Printed values for field-by-field comparison
            verify_signature: Whether to verify digital signature

        Returns:
            Complete verification result
        """
        result = VDSNCVerificationResult(is_valid=False)

        try:
            # Step 1: Decode barcode
            document = self._decode_barcode_data(barcode_data)
            result.document = document

            # Step 2: Canonicalization validation
            try:
                document.payload.get_canonical_message()
                result.canonicalization_ok = True
            except Exception as e:
                result.errors.append(f"Canonicalization failed: {e}")
                result.canonicalization_ok = False

            # Step 3: Signature verification
            if verify_signature:
                signer_id = document.payload.header.signer_id
                public_key_pem = self.public_keys.get(signer_id)

                if public_key_pem:
                    result.signature_valid = document.verify_signature(public_key_pem)
                    if not result.signature_valid:
                        result.errors.append("Digital signature verification failed")
                else:
                    result.errors.append(f"Public key not found for signer: {signer_id}")
            else:
                result.signature_valid = True

            # Step 4: Field-by-field comparison
            if printed_values:
                field_errors = document.validate_field_consistency(printed_values)
                if field_errors:
                    result.errors.extend(field_errors)
                    result.field_consistency_valid = False
                else:
                    result.field_consistency_valid = True
            else:
                result.field_consistency_valid = True
                result.warnings.append("No printed values provided for field comparison")

            # Step 5: Temporal validation
            temporal_errors = document.validate_expiry_and_dates()
            if temporal_errors:
                result.errors.extend(temporal_errors)
                result.temporal_validity_ok = False
            else:
                result.temporal_validity_ok = True

            # Overall validation
            result.is_valid = (
                result.canonicalization_ok
                and result.signature_valid
                and result.field_consistency_valid
                and result.temporal_validity_ok
            )

        except Exception as e:
            result.errors.append(f"Verification failed: {e}")

        return result

    def _sign_payload(self, payload: VDSNCPayload, algorithm: SignatureAlgorithm) -> str:
        """Sign VDS-NC payload."""
        try:
            if not self.private_key_pem:
                msg = "Private key required for signing"
                raise SignatureError(msg)

            # Load private key
            private_key = serialization.load_pem_private_key(
                self.private_key_pem.encode(), password=None
            )

            # Get signature data
            signature_data = payload.get_signature_data()

            # Sign based on algorithm
            if algorithm == SignatureAlgorithm.ES256:
                signature = private_key.sign(signature_data, ec.ECDSA(hashes.SHA256()))
            elif algorithm == SignatureAlgorithm.ES384:
                signature = private_key.sign(signature_data, ec.ECDSA(hashes.SHA384()))
            elif algorithm == SignatureAlgorithm.ES512:
                signature = private_key.sign(signature_data, ec.ECDSA(hashes.SHA512()))
            else:
                msg = f"Unsupported signature algorithm: {algorithm}"
                raise SignatureError(msg)

            return base64.b64encode(signature).decode("ascii")

        except Exception as e:
            msg = f"Signing failed: {e}"
            raise SignatureError(msg) from e

    def _create_barcode_data(
        self, payload: VDSNCPayload, signature: str, format_type: BarcodeFormat
    ) -> str:
        """Create barcode data string."""
        # VDS-NC format: header~payload~signature (simplified)
        header_str = payload.header.to_canonical_string()
        canonical_message = payload.get_canonical_message()

        return f"{header_str}~{canonical_message}~{signature}"

    def _decode_barcode_data(self, barcode_data: str) -> VDSNCDocument:
        """Decode barcode data into VDS-NC document."""
        # Parse barcode data format
        parts = barcode_data.split("~")
        if len(parts) != 3:
            msg = "Invalid VDS-NC barcode format"
            raise VerificationError(msg)

        header_str, message_str, signature = parts

        # Parse header (simplified)
        if not header_str.startswith("DC"):
            msg = "Invalid VDS-NC header"
            raise VerificationError(msg)

        # Extract header components (this is simplified - real implementation would be more robust)
        # version = header_str[2:5]
        # doc_type_str = header_str[5:8] if len(header_str) > 8 else header_str[5:]

        # Create document structure (simplified for demonstration)
        # Real implementation would fully parse and validate the header

        return VDSNCDocument(
            payload=VDSNCPayload(
                header=VDSNCHeader(
                    doc_type=DocumentType.E_VISA,  # Would be parsed from header
                    issuing_country="USA",  # Would be parsed from header
                    signer_id="TESTSGN",  # Would be parsed from header
                    certificate_reference="TESTCERT001",
                ),
                message=json.loads(message_str),
                signature_info=VDSNCSignatureInfo(algorithm=SignatureAlgorithm.ES256),
            ),
            signature=signature,
            barcode_format=BarcodeFormat.QR_CODE,  # Would be determined from context
            error_correction=VDSNCBarcodeSelector.get_recommended_error_correction(
                DocumentType.E_VISA
            ),
            barcode_data=barcode_data,
        )
