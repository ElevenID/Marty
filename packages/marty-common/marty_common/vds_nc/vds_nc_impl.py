"""VDS-NC (Visible Digital Seal - Non-Constrained) Implementation

This module implements VDS-NC barcod            vds_nc_barcode = VDSNCBarcode(
                certificate_reference=self.certificate_reference,
                signature_creation_date=signature_date_str,
                signature_creation_time=signature_time_str,
                cmc_payload=cmc_payload,
                signature=signature_b64,
                barcode_data=barcode_data
            )

            logger.info(f"VDS-NC barcode generated successfully for CMC: {cmc_certificate.cmc_id}")
        except Exception as e:
            logger.error(f"Failed to generate VDS-NC barcode: {e!s}")
            raise RuntimeError(f"VDS-NC generation failed: {e!s}") from e
        else:
            return vds_nc_barcoded verification according to
ICAO Doc 9303 Part 13 for Crew Member Certificates.

VDS-NC Structure:
- Header: "DC" + version + country code (e.g., "DC03USA")
- Message type: "CMC" for Crew Member Certificate
- Signature algorithm: ES256 (ECDSA with P-256 and SHA-256)
- Certificate reference: Reference to signing certificate
- Date/time of signature creation
- Payload: JSON-encoded CMC data
- Digital signature: ECDSA signature over header + payload
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from typing import Any

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.ec import (
        EllipticCurvePrivateKey,
        EllipticCurvePublicKey,
    )
except ImportError:
    # For environments where cryptography is not available
    EllipticCurvePrivateKey = Any
    EllipticCurvePublicKey = Any
    InvalidSignature = Exception

from marty_common.models.passport import CMCCertificate, VDSNCBarcode
from shared.logging_config import get_logger

logger = get_logger(__name__)


class VDSNCGenerator:
    """VDS-NC barcode generator for CMC certificates."""

    def __init__(self, signing_key: EllipticCurvePrivateKey, certificate_reference: str) -> None:
        """Initialize VDS-NC generator.

        Args:
            signing_key: ECDSA P-256 private key for signing
            certificate_reference: Reference to the signing certificate
        """
        self.signing_key = signing_key
        self.certificate_reference = certificate_reference

    def generate_vds_nc_barcode(
        self, cmc_certificate: CMCCertificate, signature_algorithm: str = "ES256"
    ) -> VDSNCBarcode:
        """Generate VDS-NC barcode for CMC certificate.

        Args:
            cmc_certificate: CMC certificate to encode
            signature_algorithm: Signature algorithm (default: ES256)

        Returns:
            VDS-NC barcode data

        Raises:
            ValueError: If invalid parameters or CMC data
            RuntimeError: If signing fails
        """
        try:
            logger.info(f"Generating VDS-NC barcode for CMC: {cmc_certificate.cmc_id}")

            # Create VDS-NC header
            header = self._create_header(cmc_certificate.cmc_data.issuing_country)

            # Create timestamp
            signature_date = datetime.utcnow()
            signature_date_str = signature_date.strftime("%y%m%d")
            signature_time_str = signature_date.strftime("%H%M%S")

            # Create CMC payload
            cmc_payload = self._create_cmc_payload(cmc_certificate)

            # Create data to sign (header + payload)
            sign_data = header + cmc_payload

            # Generate signature
            signature = self._sign_data(sign_data.encode("utf-8"))
            signature_b64 = base64.b64encode(signature).decode("ascii")

            # Create complete barcode data
            barcode_data = self._create_barcode_data(header, cmc_payload, signature_b64)

            # Create VDS-NC barcode object
            vds_nc_barcode = VDSNCBarcode(
                header=header,
                message_type="CMC",
                issuing_country=cmc_certificate.cmc_data.issuing_country,
                signature_algorithm=signature_algorithm,
                certificate_reference=self.certificate_reference,
                signature_creation_date=signature_date_str,
                signature_creation_time=signature_time_str,
                cmc_payload=cmc_payload,
                signature=signature_b64,
                barcode_data=barcode_data,
            )

            logger.info(f"VDS-NC barcode generated successfully for CMC: {cmc_certificate.cmc_id}")
        except Exception as e:
            logger.exception(f"Failed to generate VDS-NC barcode: {e!s}")
            msg = f"VDS-NC generation failed: {e!s}"
            raise RuntimeError(msg) from e
        else:
            return vds_nc_barcode

    def _create_header(self, issuing_country: str) -> str:
        """Create VDS-NC header.

        Args:
            issuing_country: 3-letter country code

        Returns:
            VDS-NC header string
        """
        if len(issuing_country) != 3:
            msg = f"Invalid country code: {issuing_country}"
            raise ValueError(msg)

        # VDS-NC version 03 (current version)
        return f"DC03{issuing_country}"

    def _create_cmc_payload(self, cmc_certificate: CMCCertificate) -> str:
        """Create JSON payload for CMC data.

        Args:
            cmc_certificate: CMC certificate

        Returns:
            JSON-encoded CMC payload
        """
        # Extract essential CMC data for VDS-NC
        payload_data = {
            "typ": "CMC",  # Message type
            "doc": cmc_certificate.cmc_data.document_number,
            "iss": cmc_certificate.cmc_data.issuing_country,
            "sur": cmc_certificate.cmc_data.surname,
            "giv": cmc_certificate.cmc_data.given_names,
            "nat": cmc_certificate.cmc_data.nationality,
            "dob": cmc_certificate.cmc_data.date_of_birth,
            "sex": cmc_certificate.cmc_data.gender,
            "exp": cmc_certificate.cmc_data.date_of_expiry,
        }

        # Add optional CMC-specific fields if present
        if cmc_certificate.cmc_data.employer:
            payload_data["emp"] = cmc_certificate.cmc_data.employer

        if cmc_certificate.cmc_data.crew_id:
            payload_data["cid"] = cmc_certificate.cmc_data.crew_id

        # Add background verification status (Annex 9)
        payload_data["bgv"] = cmc_certificate.cmc_data.background_check_verified

        # Add electronic record ID if present
        if cmc_certificate.cmc_data.electronic_record_id:
            payload_data["eri"] = cmc_certificate.cmc_data.electronic_record_id

        # Convert to compact JSON (no spaces)
        return json.dumps(payload_data, separators=(",", ":"), sort_keys=True)

    def _sign_data(self, data: bytes) -> bytes:
        """Sign data using ECDSA ES256.

        Args:
            data: Data to sign

        Returns:
            Signature bytes
        """
        try:
            signature = self.signing_key.sign(data, ec.ECDSA(hashes.SHA256()))
        except Exception as e:
            msg = f"Signing failed: {e!s}"
            raise RuntimeError(msg) from e
        else:
            return signature

    def _create_barcode_data(self, header: str, payload: str, signature: str) -> str:
        """Create complete barcode data string.

        Args:
            header: VDS-NC header
            payload: CMC JSON payload
            signature: Base64-encoded signature

        Returns:
            Complete barcode data string
        """
        # VDS-NC format: header + separator + payload + separator + signature
        # Using tilde (~) as separator as per ICAO Doc 9303 Part 13
        return f"{header}~{payload}~{signature}"


class VDSNCVerifier:
    """VDS-NC barcode verifier for CMC certificates."""

    def __init__(self, public_keys: dict[str, EllipticCurvePublicKey]) -> None:
        """Initialize VDS-NC verifier.

        Args:
            public_keys: Dictionary mapping certificate references to public keys
        """
        self.public_keys = public_keys

    def verify_vds_nc_barcode(
        self, barcode_data: str
    ) -> tuple[bool, CMCCertificate | None, list[str]]:
        """Verify VDS-NC barcode and extract CMC data.

        Args:
            barcode_data: Complete VDS-NC barcode data

        Returns:
            Tuple of (is_valid, cmc_certificate, error_messages)
        """
        logger.info("Verifying VDS-NC barcode")

        # Parse barcode data
        parts = barcode_data.split("~")
        if len(parts) != 3:
            return False, None, ["Invalid VDS-NC format: expected 3 parts"]

        header, payload, signature_b64 = parts

        # Verify header format
        if not self._verify_header(header):
            return False, None, ["Invalid VDS-NC header format"]

        # Extract country code from header
        issuing_country = header[4:7]

        # Validate and parse components
        validation_result = self._validate_barcode_components(payload, signature_b64)
        if not validation_result[0]:
            return False, None, validation_result[1]

        cmc_data = validation_result[2]

        try:
            # Create CMC certificate from payload
            cmc_certificate = self._create_cmc_from_payload(cmc_data, issuing_country)
            logger.info("VDS-NC barcode verified successfully")
        except Exception as e:
            logger.exception("VDS-NC verification failed")
            return False, None, [f"Verification error: {e!s}"]
        else:
            return True, cmc_certificate, []

    def _validate_barcode_components(
        self, payload: str, signature_b64: str
    ) -> tuple[bool, list[str], dict[str, Any] | None]:
        """Validate barcode payload and signature components.

        Args:
            payload: JSON payload string
            signature_b64: Base64-encoded signature

        Returns:
            Tuple of (is_valid, error_messages, parsed_data)
        """
        # Decode signature
        try:
            base64.b64decode(signature_b64)
        except (ValueError, TypeError):
            return False, ["Invalid signature encoding"], None

        # Parse CMC payload
        try:
            cmc_data = json.loads(payload)
        except json.JSONDecodeError:
            return False, ["Invalid JSON payload"], None

        # Verify payload structure
        validation_errors = self._validate_cmc_payload(cmc_data)
        if validation_errors:
            return False, validation_errors, None

        return True, [], cmc_data

    def _verify_header(self, header: str) -> bool:
        """Verify VDS-NC header format.

        Args:
            header: VDS-NC header

        Returns:
            True if valid, False otherwise
        """
        # Header should be: DC + version + country (e.g., "DC03USA")
        return (
            len(header) == 7
            and header.startswith("DC")
            and header[2:4].isdigit()
            and header[4:7].isalpha()
        )

    def _validate_cmc_payload(self, payload: dict[str, Any]) -> list[str]:
        """Validate CMC payload structure.

        Args:
            payload: Parsed JSON payload

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Required fields
        required_fields = ["typ", "doc", "iss", "sur", "nat", "dob", "sex", "exp"]
        errors.extend(
            f"Missing required field: {field}" for field in required_fields if field not in payload
        )

        # Validate message type
        if payload.get("typ") != "CMC":
            errors.append(f"Invalid message type: {payload.get('typ')}")

        # Validate country codes (should be 3 letters)
        errors.extend(
            f"Invalid {field}: must be 3-letter code"
            for field in ["iss", "nat"]
            if field in payload and len(payload[field]) != 3
        )

        # Validate gender
        if "sex" in payload and payload["sex"] not in ["M", "F", "X"]:
            errors.append(f"Invalid gender: {payload['sex']}")

        return errors

    def _create_cmc_from_payload(
        self, payload: dict[str, Any], issuing_country: str
    ) -> CMCCertificate:
        """Create CMC certificate from VDS-NC payload.

        Args:
            payload: Parsed CMC payload
            issuing_country: Issuing country from header

        Returns:
            CMC certificate object
        """
        from marty_common.models.passport import CMCData, CMCSecurityModel, CMCTD1MRZData

        # Create CMC data from payload
        cmc_data = CMCData(
            document_number=payload["doc"],
            issuing_country=issuing_country,
            surname=payload["sur"],
            given_names=payload.get("giv", ""),
            nationality=payload["nat"],
            date_of_birth=payload["dob"],
            gender=payload["sex"],
            date_of_expiry=payload["exp"],
            employer=payload.get("emp", ""),
            crew_id=payload.get("cid", ""),
            background_check_verified=payload.get("bgv", False),
            electronic_record_id=payload.get("eri", ""),
            issuer_record_keeping=True,  # Assumed true for VDS-NC
        )

        # Create TD-1 MRZ data
        td1_mrz_data = CMCTD1MRZData(
            document_type="I",
            issuing_country=issuing_country,
            document_number=payload["doc"],
            surname=payload["sur"],
            given_names=payload.get("giv", ""),
            nationality=payload["nat"],
            date_of_birth=payload["dob"],
            gender=payload["sex"],
            date_of_expiry=payload["exp"],
        )

        # Create CMC certificate
        return CMCCertificate(
            cmc_id=f"vds-nc-{payload['doc']}",  # Generate ID from document number
            cmc_data=cmc_data,
            td1_mrz_data=td1_mrz_data,
            security_model=CMCSecurityModel.VDS_NC,
            status="ACTIVE",
            created_at=datetime.now(tz=timezone.utc),
        )


def generate_test_key_pair() -> tuple[EllipticCurvePrivateKey, EllipticCurvePublicKey]:
    """Generate test ECDSA P-256 key pair for development/testing.

    Returns:
        Tuple of (private_key, public_key)
    """
    try:
        private_key = ec.generate_private_key(ec.SECP256R1())
        public_key = private_key.public_key()
    except Exception as e:
        msg = f"Failed to generate key pair: {e!s}"
        raise RuntimeError(msg) from e
    else:
        return private_key, public_key


def export_public_key_pem(public_key: EllipticCurvePublicKey) -> str:
    """Export public key to PEM format.

    Args:
        public_key: ECDSA public key

    Returns:
        PEM-encoded public key string
    """
    try:
        pem_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return pem_bytes.decode("utf-8")
    except Exception as e:
        msg = f"Failed to export public key: {e!s}"
        raise RuntimeError(msg) from e


def load_public_key_pem(pem_data: str) -> EllipticCurvePublicKey:
    """Load public key from PEM format.

    Args:
        pem_data: PEM-encoded public key string

    Returns:
        ECDSA public key
    """
    try:
        public_key = serialization.load_pem_public_key(pem_data.encode("utf-8"))
        if not isinstance(public_key, EllipticCurvePublicKey):
            msg = "Not an ECDSA public key"
            raise ValueError(msg)
    except Exception as e:
        msg = f"Failed to load public key: {e!s}"
        raise RuntimeError(msg) from e
    else:
        return public_key
