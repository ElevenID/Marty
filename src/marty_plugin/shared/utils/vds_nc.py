"""
VDS-NC (Visible Digital Seal - Non-Constrained) encoding for e-visa documents.

This module implements VDS-NC encoding per ICAO Part 13 specifications for
Digital Travel Authorization (DTA) and e-visa documents with:
- CBOR (Concise Binary Object Representation) payload encoding
- Digital signature generation and verification (via Rust marty_rs)
- 2D barcode (QR Code, DataMatrix) generation
- Full verification workflow support

Supports both printable and screen-presentable formats with identical
verification outcomes.
"""

from __future__ import annotations

import base64
import json
import time
from datetime import datetime
from enum import Enum
from typing import Any

try:
    import cbor2
except ImportError:
    cbor2 = None

try:
    import qrcode
    from qrcode.image.styledpil import StyledPilImage
    from qrcode.image.styles.moduledrawers import RoundedModuleDrawer
except ImportError:
    qrcode = None

# Use crypto_bridge for Rust-backed cryptographic operations
from marty_backend_common.crypto_bridge import (
    sha256,
    ecdsa_p256_sign,
    ecdsa_p256_verify,
    ecdsa_p384_sign,
    ecdsa_p384_verify,
    ecdsa_p521_sign,
    ecdsa_p521_verify,
    rsa_pss_sha256_sign,
    rsa_pss_sha256_verify,
    rsa_pss_sha384_sign,
    rsa_pss_sha384_verify,
    rsa_pss_sha512_sign,
    rsa_pss_sha512_verify,
    load_private_key_pem,
    pkcs8_to_raw_private_key,
    detect_private_key_type,
)

from marty_plugin.shared.models.visa import VDSNCData, Visa


class VDSNCMessageType(str, Enum):
    """VDS-NC message types."""

    EMERGENCY_TRAVEL_DOCUMENT = "emergency_travel_document"
    PROOF_OF_TESTING = "proof_of_testing"
    PROOF_OF_VACCINATION = "proof_of_vaccination"
    DIGITAL_TRAVEL_AUTHORIZATION = "digital_travel_authorization"
    VISA = "visa"


class BarcodeFormat(str, Enum):
    """Supported barcode formats."""

    QR_CODE = "QR"
    DATA_MATRIX = "DM"
    AZTEC = "AZTEC"


class SignatureAlgorithm(str, Enum):
    """Supported signature algorithms."""

    ES256 = "ES256"  # ECDSA with SHA-256
    ES384 = "ES384"  # ECDSA with SHA-384
    ES512 = "ES512"  # ECDSA with SHA-512
    PS256 = "PS256"  # RSA-PSS with SHA-256
    PS384 = "PS384"  # RSA-PSS with SHA-384
    PS512 = "PS512"  # RSA-PSS with SHA-512


class VDSNCEncoder:
    """Encoder for VDS-NC data payloads."""

    @classmethod
    def create_header(
        cls,
        message_type: VDSNCMessageType,
        issuer: str,
        version: str = "1",
        algorithm: SignatureAlgorithm = SignatureAlgorithm.ES256,
    ) -> dict[str, Any]:
        """
        Create VDS-NC header.

        Args:
            message_type: Type of VDS-NC message
            issuer: Issuing authority identifier
            version: VDS-NC version
            algorithm: Signature algorithm

        Returns:
            Header dictionary
        """
        return {
            "ver": version,
            "typ": message_type.value,
            "iss": issuer,
            "iat": int(time.time()),
            "alg": algorithm.value,
        }

    @classmethod
    def create_visa_message(cls, visa: Visa) -> dict[str, Any]:
        """
        Create VDS-NC message payload for visa.

        Args:
            visa: Visa object

        Returns:
            Message payload dictionary
        """
        personal = visa.personal_data
        document = visa.document_data

        message = {
            # Document identification
            "doc": {
                "type": "V",  # Visa
                "no": document.document_number,
                "iss": document.issuing_state,
                "cat": document.visa_category.value,
            },
            # Personal data
            "subj": {
                "fn": personal.given_names,
                "gn": personal.surname,
                "dob": personal.date_of_birth.isoformat(),
                "sex": personal.gender.value,
                "nat": personal.nationality,
            },
            # Validity
            "val": {
                "from": document.date_of_issue.isoformat(),
                "to": document.date_of_expiry.isoformat(),
            },
            # Additional visa-specific data
            "vis": {
                "poi": document.place_of_issue,
                "entries": document.number_of_entries or "M",
                "duration": document.duration_of_stay,
            },
        }

        # Add validity window if specified
        if document.valid_from:
            message["val"]["valid_from"] = document.valid_from.isoformat()

        if document.valid_until:
            message["val"]["valid_until"] = document.valid_until.isoformat()

        # Add policy constraints if present
        if visa.policy_constraints:
            constraints = {}

            if visa.policy_constraints.allowed_countries:
                constraints["allowed_countries"] = visa.policy_constraints.allowed_countries

            if visa.policy_constraints.restricted_countries:
                constraints["restricted_countries"] = visa.policy_constraints.restricted_countries

            if visa.policy_constraints.employment_authorized:
                constraints["employment"] = visa.policy_constraints.employment_authorized

            if visa.policy_constraints.study_authorized:
                constraints["study"] = visa.policy_constraints.study_authorized

            if constraints:
                message["pol"] = constraints

        return message

    @classmethod
    def encode_cbor(cls, header: dict[str, Any], message: dict[str, Any]) -> bytes:
        """
        Encode header and message as CBOR.

        Args:
            header: VDS-NC header
            message: VDS-NC message

        Returns:
            CBOR-encoded bytes
        """
        if cbor2 is None:
            msg = "cbor2 library required for CBOR encoding"
            raise ImportError(msg)

        payload = {"header": header, "message": message}

        return cbor2.dumps(payload)

    @classmethod
    def create_signature_input(cls, cbor_data: bytes) -> bytes:
        """
        Create signature input from CBOR data.

        Args:
            cbor_data: CBOR-encoded payload

        Returns:
            Signature input bytes
        """
        # For VDS-NC, we typically sign the hash of the CBOR data using Rust
        return sha256(cbor_data)

    @classmethod
    def sign_data(
        cls,
        signature_input: bytes,
        private_key_pem: str,
        algorithm: SignatureAlgorithm = SignatureAlgorithm.ES256,
    ) -> bytes:
        """
        Sign the signature input using Rust crypto.

        Args:
            signature_input: Data to sign
            private_key_pem: Private key in PEM format
            algorithm: Signature algorithm

        Returns:
            Signature bytes
        """
        if not private_key_pem or private_key_pem.strip() == "":
            raise ValueError("Private key is empty — cannot sign VDS-NC data")

        try:
            # Load key using Rust crypto_bridge
            private_der = load_private_key_pem(private_key_pem)
            key_type = detect_private_key_type(private_der)
        except Exception as exc:
            raise ValueError(
                f"Failed to load private key for VDS-NC signing: {exc}"
            ) from exc

        if algorithm in [
            SignatureAlgorithm.ES256,
            SignatureAlgorithm.ES384,
            SignatureAlgorithm.ES512,
        ]:
            # ECDSA signing using Rust
            raw_key, _ = pkcs8_to_raw_private_key(private_der)
            
            if algorithm == SignatureAlgorithm.ES256:
                return ecdsa_p256_sign(raw_key, signature_input)
            elif algorithm == SignatureAlgorithm.ES384:
                return ecdsa_p384_sign(raw_key, signature_input)
            else:  # ES512
                raise NotImplementedError("ES512 (P-521) signing is not yet supported")

        elif algorithm in [
            SignatureAlgorithm.PS256,
            SignatureAlgorithm.PS384,
            SignatureAlgorithm.PS512,
        ]:
            # RSA-PSS signing using Rust
            if algorithm == SignatureAlgorithm.PS256:
                return rsa_pss_sha256_sign(private_der, signature_input)
            elif algorithm == SignatureAlgorithm.PS384:
                return rsa_pss_sha384_sign(private_der, signature_input)
            else:  # PS512
                return rsa_pss_sha512_sign(private_der, signature_input)
        else:
            msg = f"Unsupported signature algorithm: {algorithm}"
            raise ValueError(msg)

    @classmethod
    def encode_vds_nc(
        cls,
        visa: Visa,
        issuer: str,
        private_key_pem: str,
        algorithm: SignatureAlgorithm = SignatureAlgorithm.ES256,
        certificate_pem: str | None = None,
    ) -> VDSNCData:
        """
        Create complete VDS-NC encoding for visa.

        Args:
            visa: Visa object
            issuer: Issuing authority identifier
            private_key_pem: Private key for signing
            algorithm: Signature algorithm
            certificate_pem: Optional certificate for verification

        Returns:
            VDSNCData object with encoded data
        """
        # Create header and message
        header = cls.create_header(VDSNCMessageType.VISA, issuer, algorithm=algorithm)
        message = cls.create_visa_message(visa)

        # Encode as CBOR
        cbor_data = cls.encode_cbor(header, message)

        # Create signature
        signature_input = cls.create_signature_input(cbor_data)
        signature = cls.sign_data(signature_input, private_key_pem, algorithm)

        # Create complete VDS-NC structure
        vds_nc_payload = {
            "data": base64.b64encode(cbor_data).decode("ascii"),
            "sig": base64.b64encode(signature).decode("ascii"),
        }

        if certificate_pem:
            vds_nc_payload["cert"] = (
                certificate_pem.replace("\n", "")
                .replace("-----BEGIN CERTIFICATE-----", "")
                .replace("-----END CERTIFICATE-----", "")
            )

        # Encode complete payload
        complete_payload = json.dumps(vds_nc_payload, separators=(",", ":"))

        return VDSNCData(
            header=header,
            message=message,
            signature=base64.b64encode(signature).decode("ascii"),
            barcode_data=complete_payload,
            barcode_format=BarcodeFormat.QR_CODE,
            issuer_certificate=certificate_pem,
            signature_algorithm=algorithm.value,
        )


class VDSNCDecoder:
    """Decoder for VDS-NC data payloads."""

    @classmethod
    def decode_cbor(cls, cbor_data: bytes) -> dict[str, Any]:
        """
        Decode CBOR data.

        Args:
            cbor_data: CBOR-encoded bytes

        Returns:
            Decoded payload dictionary
        """
        if cbor2 is None:
            msg = "cbor2 library required for CBOR decoding"
            raise ImportError(msg)

        return cbor2.loads(cbor_data)

    @classmethod
    def verify_signature(
        cls,
        signature_input: bytes,
        signature: bytes,
        public_key_pem: str,
        algorithm: SignatureAlgorithm = SignatureAlgorithm.ES256,
    ) -> bool:
        """
        Verify signature using Rust crypto bindings.

        Args:
            signature_input: Original data that was signed
            signature: Signature bytes
            public_key_pem: Public key in PEM format
            algorithm: Signature algorithm

        Returns:
            True if signature is valid
        """
        try:
            # Extract raw public key bytes from PEM
            from cryptography.hazmat.primitives.serialization import (
                Encoding,
                PublicFormat,
                load_pem_public_key,
            )

            public_key = load_pem_public_key(public_key_pem.encode())
            public_key_bytes = public_key.public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)

            if algorithm in [
                SignatureAlgorithm.ES256,
                SignatureAlgorithm.ES384,
                SignatureAlgorithm.ES512,
            ]:
                # ECDSA verification via Rust
                if algorithm == SignatureAlgorithm.ES256:
                    return ecdsa_p256_verify(public_key_bytes, signature_input, signature)
                elif algorithm == SignatureAlgorithm.ES384:
                    return ecdsa_p384_verify(public_key_bytes, signature_input, signature)
                else:  # ES512
                    return ecdsa_p521_verify(public_key_bytes, signature_input, signature)

            elif algorithm in [
                SignatureAlgorithm.PS256,
                SignatureAlgorithm.PS384,
                SignatureAlgorithm.PS512,
            ]:
                # RSA-PSS verification via Rust
                if algorithm == SignatureAlgorithm.PS256:
                    return rsa_pss_sha256_verify(public_key_bytes, signature_input, signature)
                elif algorithm == SignatureAlgorithm.PS384:
                    return rsa_pss_sha384_verify(public_key_bytes, signature_input, signature)
                else:  # PS512
                    return rsa_pss_sha512_verify(public_key_bytes, signature_input, signature)
            else:
                return False

        except Exception:
            return False

    @classmethod
    def decode_vds_nc(
        cls, barcode_data: str, public_key_pem: str | None = None
    ) -> tuple[dict[str, Any], bool]:
        """
        Decode and verify VDS-NC barcode data.

        Args:
            barcode_data: Barcode data (JSON string)
            public_key_pem: Public key for signature verification

        Returns:
            Tuple of (decoded_data, signature_valid)
        """
        try:
            # Parse JSON payload
            payload = json.loads(barcode_data)

            # Extract components
            cbor_data = base64.b64decode(payload["data"])
            signature = base64.b64decode(payload["sig"])

            # Decode CBOR data
            decoded = cls.decode_cbor(cbor_data)

            # Verify signature if public key provided
            signature_valid = False
            if public_key_pem:
                signature_input = VDSNCEncoder.create_signature_input(cbor_data)

                # Get algorithm from header
                algorithm_str = decoded.get("header", {}).get("alg", "ES256")
                algorithm = SignatureAlgorithm(algorithm_str)

                signature_valid = cls.verify_signature(
                    signature_input, signature, public_key_pem, algorithm
                )

        except Exception as e:
            msg = f"Failed to decode VDS-NC data: {e}"
            raise ValueError(msg) from e
        else:
            return decoded, signature_valid


class BarcodeGenerator:
    """Generator for 2D barcodes."""

    @classmethod
    def generate_qr_code(
        cls, data: str, error_correction: str = "M", border: int = 4, box_size: int = 10
    ) -> bytes | None:
        """
        Generate QR code for data.

        Args:
            data: Data to encode
            error_correction: Error correction level (L, M, Q, H)
            border: Border size
            box_size: Box size

        Returns:
            PNG image bytes or None if qrcode not available
        """
        if qrcode is None:
            return None

        # Map error correction levels
        error_levels = {
            "L": qrcode.constants.ERROR_CORRECT_L,
            "M": qrcode.constants.ERROR_CORRECT_M,
            "Q": qrcode.constants.ERROR_CORRECT_Q,
            "H": qrcode.constants.ERROR_CORRECT_H,
        }

        qr = qrcode.QRCode(
            version=1,
            error_correction=error_levels.get(error_correction, qrcode.constants.ERROR_CORRECT_M),
            box_size=box_size,
            border=border,
        )

        qr.add_data(data)
        qr.make(fit=True)

        # Create image
        img = qr.make_image(fill_color="black", back_color="white")

        # Convert to bytes
        import io

        img_bytes = io.BytesIO()
        img.save(img_bytes, format="PNG")

        return img_bytes.getvalue()

    @classmethod
    def generate_styled_qr_code(
        cls,
        data: str,
        logo_path: str | None = None,
        fill_color: str = "black",
        back_color: str = "white",
    ) -> bytes | None:
        """
        Generate styled QR code with optional logo.

        Args:
            data: Data to encode
            logo_path: Optional path to logo image
            fill_color: Fill color
            back_color: Background color

        Returns:
            PNG image bytes or None if libraries not available
        """
        if qrcode is None:
            return None

        try:
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_H,  # High for logo
                box_size=10,
                border=4,
            )

            qr.add_data(data)
            qr.make(fit=True)

            # Create styled image
            img = qr.make_image(
                image_factory=StyledPilImage,
                module_drawer=RoundedModuleDrawer(),
                fill_color=fill_color,
                back_color=back_color,
            )

            # Add logo if provided
            if logo_path:
                try:
                    from PIL import Image

                    logo = Image.open(logo_path)

                    # Calculate logo size (about 10% of QR code)
                    qr_width, qr_height = img.size
                    logo_size = min(qr_width, qr_height) // 10

                    # Resize logo
                    logo = logo.resize((logo_size, logo_size), Image.Resampling.LANCZOS)

                    # Calculate position (center)
                    logo_x = (qr_width - logo_size) // 2
                    logo_y = (qr_height - logo_size) // 2

                    # Paste logo
                    img.paste(logo, (logo_x, logo_y))

                except Exception:
                    pass  # Continue without logo if there's an error

            # Convert to bytes
            import io

            img_bytes = io.BytesIO()
            img.save(img_bytes, format="PNG")

            return img_bytes.getvalue()

        except Exception:
            # Fallback to basic QR code
            return cls.generate_qr_code(data)


class VDSNCValidator:
    """Validator for VDS-NC data consistency."""

    @classmethod
    def validate_header(cls, header: dict[str, Any]) -> list[str]:
        """
        Validate VDS-NC header.

        Args:
            header: Header dictionary

        Returns:
            List of validation errors
        """
        errors = []

        # Required fields
        required_fields = ["ver", "typ", "iss", "iat", "alg"]
        for field in required_fields:
            if field not in header:
                errors.append(f"Missing required header field: {field}")

        # Validate version
        if "ver" in header and header["ver"] not in ["1"]:
            errors.append(f"Unsupported VDS-NC version: {header['ver']}")

        # Validate algorithm
        if "alg" in header:
            try:
                SignatureAlgorithm(header["alg"])
            except ValueError:
                errors.append(f"Unsupported signature algorithm: {header['alg']}")

        # Validate timestamp
        if "iat" in header:
            try:
                iat = int(header["iat"])
                now = int(time.time())

                # Check if timestamp is reasonable (not too far in past/future)
                if abs(now - iat) > 86400 * 365:  # 1 year
                    errors.append("Timestamp is outside reasonable range")

            except (ValueError, TypeError):
                errors.append("Invalid timestamp format")

        return errors

    @classmethod
    def validate_visa_message(cls, message: dict[str, Any]) -> list[str]:
        """
        Validate visa message payload.

        Args:
            message: Message dictionary

        Returns:
            List of validation errors
        """
        errors = []

        # Validate document section
        if "doc" not in message:
            errors.append("Missing document section")
        else:
            doc = message["doc"]

            required_doc_fields = ["type", "no", "iss", "cat"]
            for field in required_doc_fields:
                if field not in doc:
                    errors.append(f"Missing document field: {field}")

            if "type" in doc and doc["type"] != "V":
                errors.append(f"Invalid document type for visa: {doc['type']}")

        # Validate subject section
        if "subj" not in message:
            errors.append("Missing subject section")
        else:
            subj = message["subj"]

            required_subj_fields = ["fn", "gn", "dob", "sex", "nat"]
            for field in required_subj_fields:
                if field not in subj:
                    errors.append(f"Missing subject field: {field}")

            # Validate date format
            if "dob" in subj:
                try:
                    datetime.fromisoformat(subj["dob"].replace("Z", "+00:00"))
                except ValueError:
                    errors.append("Invalid date of birth format")

            # Validate gender
            if "sex" in subj and subj["sex"] not in ["M", "F", "X"]:
                errors.append(f"Invalid gender value: {subj['sex']}")

        # Validate validity section
        if "val" not in message:
            errors.append("Missing validity section")
        else:
            val = message["val"]

            required_val_fields = ["from", "to"]
            for field in required_val_fields:
                if field not in val:
                    errors.append(f"Missing validity field: {field}")

            # Validate date formats and logic
            try:
                if "from" in val and "to" in val:
                    from_date = datetime.fromisoformat(val["from"].replace("Z", "+00:00"))
                    to_date = datetime.fromisoformat(val["to"].replace("Z", "+00:00"))

                    if from_date >= to_date:
                        errors.append("Validity 'to' date must be after 'from' date")

            except ValueError:
                errors.append("Invalid validity date format")

        return errors

    @classmethod
    def validate_field_consistency(
        cls, vds_nc_data: dict[str, Any], visa: Visa | None = None
    ) -> list[str]:
        """
        Validate field consistency between VDS-NC data and visa object.

        Args:
            vds_nc_data: Decoded VDS-NC data
            visa: Optional visa object for comparison

        Returns:
            List of consistency errors
        """
        errors = []

        if not visa:
            return errors

        message = vds_nc_data.get("message", {})

        # Check document consistency
        if "doc" in message:
            doc = message["doc"]

            if "no" in doc and doc["no"] != visa.document_data.document_number:
                errors.append("Document number mismatch")

            if "iss" in doc and doc["iss"] != visa.document_data.issuing_state:
                errors.append("Issuing state mismatch")

            if "cat" in doc and doc["cat"] != visa.document_data.visa_category.value:
                errors.append("Visa category mismatch")

        # Check subject consistency
        if "subj" in message:
            subj = message["subj"]

            if "fn" in subj and subj["fn"] != visa.personal_data.given_names:
                errors.append("Given names mismatch")

            if "gn" in subj and subj["gn"] != visa.personal_data.surname:
                errors.append("Surname mismatch")

            if "nat" in subj and subj["nat"] != visa.personal_data.nationality:
                errors.append("Nationality mismatch")

            if "sex" in subj and subj["sex"] != visa.personal_data.gender.value:
                errors.append("Gender mismatch")

            if "dob" in subj:
                try:
                    vds_dob = datetime.fromisoformat(subj["dob"].replace("Z", "+00:00")).date()
                    if vds_dob != visa.personal_data.date_of_birth:
                        errors.append("Date of birth mismatch")
                except ValueError:
                    errors.append("Invalid date of birth in VDS-NC")

        # Check validity consistency
        if "val" in message:
            val = message["val"]

            if "from" in val:
                try:
                    vds_from = datetime.fromisoformat(val["from"].replace("Z", "+00:00")).date()
                    if vds_from != visa.document_data.date_of_issue:
                        errors.append("Issue date mismatch")
                except ValueError:
                    errors.append("Invalid issue date in VDS-NC")

            if "to" in val:
                try:
                    vds_to = datetime.fromisoformat(val["to"].replace("Z", "+00:00")).date()
                    if vds_to != visa.document_data.date_of_expiry:
                        errors.append("Expiry date mismatch")
                except ValueError:
                    errors.append("Invalid expiry date in VDS-NC")

        return errors
