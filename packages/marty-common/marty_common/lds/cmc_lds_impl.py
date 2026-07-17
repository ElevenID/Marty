"""LDS (Logical Data Structure) Implementation for CMC Certificates

This module implements minimal LDS support for chip-based CMC certificates according to
ICAO Doc 9303 Parts 10-12. It provides DG1 (MRZ data) and DG2 (face image) data groups
with SOD (Security Object Document) signing.

CMC LDS Structure:
- DG1: MRZ data (TD-1 format)
- DG2: Face image (JPEG/JP2)
- SOD: Security Object Document with hashes and signatures
"""

from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timezone

from marty_common.models.passport import CMCCertificate, DataGroup, DataGroupType
from marty_common.utils.mrz_utils import generate_td1_mrz
from shared.logging_config import get_logger

logger = get_logger(__name__)


class CMCLDSGenerator:
    """Generator for CMC Logical Data Structure (LDS) data groups."""

    def __init__(self) -> None:
        """Initialize LDS generator for CMC certificates."""
        logger.info("CMC LDS generator initialized")

    def generate_dg1(self, cmc_certificate: CMCCertificate) -> DataGroup:
        """Generate DG1 (MRZ data) for CMC certificate.

        Args:
            cmc_certificate: CMC certificate containing MRZ data

        Returns:
            DataGroup containing DG1 data

        Raises:
            ValueError: If MRZ data is invalid
        """
        try:
            logger.info(f"Generating DG1 for CMC: {cmc_certificate.cmc_id}")

            # Get TD-1 MRZ string
            td1_mrz = generate_td1_mrz(cmc_certificate.td1_mrz_data)

            # Encode MRZ data for DG1
            # In real implementation, this would be ASN.1 encoded
            # For now, we'll use simple UTF-8 encoding
            mrz_bytes = td1_mrz.encode("utf-8")

            # Create DG1 with proper ASN.1 TLV structure (simplified)
            dg1_data = self._create_dg1_tlv(mrz_bytes)

            # Calculate hash for SOD
            dg1_hash = hashlib.sha256(dg1_data).hexdigest()

            dg1 = DataGroup(
                type=DataGroupType.DG1,
                data=dg1_data,
                hash_algorithm="SHA-256",
                hash_value=dg1_hash,
                size=len(dg1_data),
            )

            logger.info(f"DG1 generated successfully: {len(dg1_data)} bytes")
        except Exception as e:
            error_msg = f"Failed to generate DG1: {e!s}"
            logger.exception(error_msg)
            raise ValueError(error_msg) from e
        else:
            return dg1

    def generate_dg2(self, cmc_certificate: CMCCertificate) -> DataGroup | None:
        """Generate DG2 (face image) for CMC certificate.

        Args:
            cmc_certificate: CMC certificate containing face image

        Returns:
            DataGroup containing DG2 data, or None if no face image

        Raises:
            ValueError: If face image data is invalid
        """
        try:
            if not cmc_certificate.face_image:
                logger.info("No face image provided for DG2")
                return None

            logger.info(f"Generating DG2 for CMC: {cmc_certificate.cmc_id}")

            # Get face image bytes
            if isinstance(cmc_certificate.face_image, str):
                face_image_bytes = base64.b64decode(cmc_certificate.face_image)
            else:
                face_image_bytes = cmc_certificate.face_image

            # Validate image format (basic check)
            if not self._is_valid_image(face_image_bytes):
                msg = "Invalid face image format"
                raise ValueError(msg)

            # Create DG2 with proper ASN.1 TLV structure (simplified)
            dg2_data = self._create_dg2_tlv(face_image_bytes)

            # Calculate hash for SOD
            dg2_hash = hashlib.sha256(dg2_data).hexdigest()

            dg2 = DataGroup(
                type=DataGroupType.DG2,
                data=dg2_data,
                hash_algorithm="SHA-256",
                hash_value=dg2_hash,
                size=len(dg2_data),
            )

            logger.info(f"DG2 generated successfully: {len(dg2_data)} bytes")
        except Exception as e:
            error_msg = f"Failed to generate DG2: {e!s}"
            logger.exception(error_msg)
            raise ValueError(error_msg) from e
        else:
            return dg2

    def generate_chip_content(
        self, cmc_certificate: CMCCertificate, sod_data: str | None = None
    ) -> bytes:
        """Generate complete chip content for CMC certificate.

        Args:
            cmc_certificate: CMC certificate
            sod_data: Security Object Document (base64 encoded)

        Returns:
            Complete chip content as bytes
        """
        try:
            logger.info(f"Generating chip content for CMC: {cmc_certificate.cmc_id}")

            # Generate DG1 and DG2
            dg1 = self.generate_dg1(cmc_certificate)
            dg2 = self.generate_dg2(cmc_certificate)

            # Create chip content structure
            chip_content = {
                "EF.COM": self._create_ef_com(dg1, dg2),
                "EF.DG1": dg1.data,
            }

            if dg2:
                chip_content["EF.DG2"] = dg2.data

            if sod_data:
                chip_content["EF.SOD"] = base64.b64decode(sod_data)

            # Serialize chip content (simplified - real implementation would use CBEFF)
            serialized_content = self._serialize_chip_content(chip_content)

            logger.info(f"Chip content generated: {len(serialized_content)} bytes")
        except Exception as e:
            error_msg = f"Failed to generate chip content: {e!s}"
            logger.exception(error_msg)
            raise RuntimeError(error_msg) from e
        else:
            return serialized_content

    def _create_dg1_tlv(self, mrz_bytes: bytes) -> bytes:
        """Create DG1 TLV (Tag-Length-Value) structure.

        Args:
            mrz_bytes: MRZ data as bytes

        Returns:
            DG1 data with TLV structure
        """
        # DG1 tag is 0x61
        tag = b"\x61"

        # Length encoding (simplified - real implementation would handle long form)
        length = len(mrz_bytes)
        if length < 128:
            length_bytes = bytes([length])
        elif length < 256:
            length_bytes = b"\x81" + bytes([length])
        else:
            length_bytes = b"\x82" + length.to_bytes(2, "big")

        return tag + length_bytes + mrz_bytes

    def _create_dg2_tlv(self, image_bytes: bytes) -> bytes:
        """Create DG2 TLV structure for face image.

        Args:
            image_bytes: Face image data

        Returns:
            DG2 data with TLV structure
        """
        # DG2 tag is 0x75 (for biometric data)
        tag = b"\x75"

        # Create biometric header (simplified)
        biometric_header = self._create_biometric_header(len(image_bytes))

        # Combine header and image data
        payload = biometric_header + image_bytes

        # Length encoding
        length = len(payload)
        if length < 128:
            length_bytes = bytes([length])
        elif length < 256:
            length_bytes = b"\x81" + bytes([length])
        else:
            length_bytes = b"\x82" + length.to_bytes(2, "big")

        return tag + length_bytes + payload

    def _create_biometric_header(self, image_size: int) -> bytes:
        """Create biometric header for DG2.

        Args:
            image_size: Size of the face image

        Returns:
            Biometric header bytes
        """
        # Simplified biometric header according to ICAO standards
        header = bytearray()

        # Biometric type (face = 0x02)
        header.append(0x02)

        # Biometric subtype (basic frontal image = 0x01)
        header.append(0x01)

        # Creation date/time (current time in compact format)
        now = datetime.now(tz=timezone.utc)
        creation_date = now.strftime("%Y%m%d%H%M%S")
        header.extend(creation_date.encode("ascii"))

        # Validity period (1 year in days)
        validity_days = 365
        header.extend(validity_days.to_bytes(2, "big"))

        # Creator info (simplified)
        creator = "CMC_LDS_GEN"
        header.extend(len(creator).to_bytes(1, "big"))
        header.extend(creator.encode("ascii"))

        # Format type (JPEG = 0x00)
        header.append(0x00)

        # Image data length
        header.extend(image_size.to_bytes(4, "big"))

        return bytes(header)

    def _create_ef_com(self, dg1: DataGroup, dg2: DataGroup | None) -> bytes:
        """Create EF.COM (Common) file containing LDS version and tag list.

        Args:
            dg1: DG1 data group
            dg2: DG2 data group (optional)

        Returns:
            EF.COM file content
        """
        # EF.COM structure (simplified)
        ef_com = bytearray()

        # LDS version (1.7)
        ef_com.extend(b"\x5f\x01\x04\x30\x31\x30\x37")  # Version "0107"

        # Unicode version (4.0.0)
        ef_com.extend(b"\x5f\x36\x06\x34\x2e\x30\x2e\x30")  # "4.0.0"

        # Tag list indicating which DGs are present
        tag_list = [0x61]  # DG1 always present
        if dg2:
            tag_list.append(0x75)  # DG2 if face image present

        # Encode tag list
        ef_com.extend(b"\x5c")  # Tag list tag
        ef_com.append(len(tag_list))
        ef_com.extend(bytes(tag_list))

        return bytes(ef_com)

    def _is_valid_image(self, image_bytes: bytes) -> bool:
        """Validate image format (JPEG or JPEG2000).

        Args:
            image_bytes: Image data

        Returns:
            True if valid image format
        """
        if len(image_bytes) < 4:
            return False

        # Check for JPEG magic number
        if image_bytes[:2] == b"\xff\xd8":
            return True

        # Check for JPEG2000 magic number
        return image_bytes[:4] == b"\x00\x00\x00\x0c"

    def _serialize_chip_content(self, chip_content: dict[str, bytes]) -> bytes:
        """Serialize chip content to binary format.

        Args:
            chip_content: Dictionary of file system content

        Returns:
            Serialized chip content
        """
        # Simplified serialization - real implementation would use ISO 7816-4 file system
        serialized = bytearray()

        for file_id, content in chip_content.items():
            # File header
            file_id_bytes = file_id.encode("ascii")
            serialized.extend(len(file_id_bytes).to_bytes(2, "big"))
            serialized.extend(file_id_bytes)

            # Content length and data
            serialized.extend(len(content).to_bytes(4, "big"))
            serialized.extend(content)

        return bytes(serialized)


class CMCSODGenerator:
    """Generator for CMC Security Object Document (SOD)."""

    def __init__(self, document_signer_service=None) -> None:
        """Initialize SOD generator.

        Args:
            document_signer_service: Document signer service for signing SOD
        """
        self.document_signer = document_signer_service
        logger.info("CMC SOD generator initialized")

    def generate_sod(
        self,
        data_groups: dict[str, DataGroup],
        signer_certificate: str | None = None,
        hash_algorithm: str = "SHA-256",
    ) -> str:
        """Generate Security Object Document (SOD) for CMC.

        Args:
            data_groups: Dictionary of data groups
            signer_certificate: Document signer certificate (base64)
            hash_algorithm: Hash algorithm to use

        Returns:
            SOD as base64 encoded string

        Raises:
            RuntimeError: If SOD generation fails
        """
        try:
            logger.info("Generating SOD for CMC")

            # Create LDS Security Object
            lds_security_object = self._create_lds_security_object(data_groups, hash_algorithm)

            # Create CMS SignedData structure (simplified)
            sod_data = self._create_cms_signed_data(lds_security_object, signer_certificate)

            # Encode as base64
            sod_b64 = base64.b64encode(sod_data).decode("ascii")

            logger.info(f"SOD generated successfully: {len(sod_data)} bytes")
        except Exception as e:
            error_msg = f"Failed to generate SOD: {e!s}"
            logger.exception(error_msg)
            raise RuntimeError(error_msg) from e
        else:
            return sod_b64

    def _create_lds_security_object(
        self, data_groups: dict[str, DataGroup], hash_algorithm: str
    ) -> bytes:
        """Create LDS Security Object with data group hashes.

        Args:
            data_groups: Data groups to include in SOD
            hash_algorithm: Hash algorithm identifier

        Returns:
            LDS Security Object as bytes
        """
        # ASN.1 structure for LDS Security Object (simplified)
        lds_obj = bytearray()

        # Version (v1)
        lds_obj.extend(b"\x02\x01\x01")

        # Hash algorithm identifier
        hash_alg_oid = self._get_hash_algorithm_oid(hash_algorithm)
        lds_obj.extend(hash_alg_oid)

        # Data group hash values
        dg_hashes = bytearray()
        for dg_type, dg in data_groups.items():
            if dg.hash_value:
                # DG number
                dg_num = int(dg_type.replace("DG", ""))
                dg_hashes.extend(b"\x02\x01" + bytes([dg_num]))

                # Hash value
                hash_bytes = bytes.fromhex(dg.hash_value)
                dg_hashes.extend(b"\x04" + bytes([len(hash_bytes)]) + hash_bytes)

        # Wrap in SEQUENCE
        lds_obj.extend(b"\x30" + bytes([len(dg_hashes)]) + dg_hashes)

        return bytes(lds_obj)

    def _get_hash_algorithm_oid(self, algorithm: str) -> bytes:
        """Get ASN.1 encoded hash algorithm OID.

        Args:
            algorithm: Hash algorithm name

        Returns:
            ASN.1 encoded algorithm identifier
        """
        # Hash algorithm OIDs
        hash_oids = {
            "SHA-1": b"\x30\x09\x06\x05\x2b\x0e\x03\x02\x1a\x05\x00",
            "SHA-256": b"\x30\x0b\x06\x09\x60\x86\x48\x01\x65\x03\x04\x02\x01\x05\x00",
            "SHA-384": b"\x30\x0b\x06\x09\x60\x86\x48\x01\x65\x03\x04\x02\x02\x05\x00",
            "SHA-512": b"\x30\x0b\x06\x09\x60\x86\x48\x01\x65\x03\x04\x02\x03\x05\x00",
        }

        return hash_oids.get(algorithm, hash_oids["SHA-256"])

    def _create_cms_signed_data(
        self, lds_security_object: bytes, signer_certificate: str | None
    ) -> bytes:
        """Create CMS SignedData structure.

        Args:
            lds_security_object: LDS Security Object
            signer_certificate: Signer certificate (base64)

        Returns:
            CMS SignedData as bytes
        """
        # Mock CMS SignedData structure
        # In real implementation, this would create proper CMS structure
        cms_data = bytearray()

        # CMS ContentInfo OID (signedData)
        cms_data.extend(b"\x30\x82")  # SEQUENCE, long form length

        # Content type (signedData)
        cms_data.extend(b"\x06\x09\x2a\x86\x48\x86\xf7\x0d\x01\x07\x02")

        # Content (the LDS Security Object)
        cms_data.extend(b"\xa0\x82")  # CONTEXT [0], long form length
        cms_data.extend(len(lds_security_object).to_bytes(2, "big"))
        cms_data.extend(lds_security_object)

        # Add mock signature (in real implementation, this would be actual signature)
        mock_signature = b"\x00" * 256  # 256-byte mock signature
        cms_data.extend(b"\x04\x82\x01\x00")  # OCTET STRING, 256 bytes
        cms_data.extend(mock_signature)

        # Fix length fields
        total_length = len(cms_data) - 4  # Exclude initial SEQUENCE header
        cms_data[2:4] = total_length.to_bytes(2, "big")

        return bytes(cms_data)


class CMCLDSManager:
    """High-level manager for CMC LDS operations."""

    def __init__(self, document_signer_service=None) -> None:
        """Initialize LDS manager.

        Args:
            document_signer_service: Document signer service
        """
        self.lds_generator = CMCLDSGenerator()
        self.sod_generator = CMCSODGenerator(document_signer_service)
        logger.info("CMC LDS manager initialized")

    def create_chip_lds_data(
        self, cmc_certificate: CMCCertificate, signer_certificate: str | None = None
    ) -> tuple[dict[str, DataGroup], str, bytes]:
        """Create complete LDS data for chip-based CMC.

        Args:
            cmc_certificate: CMC certificate
            signer_certificate: Document signer certificate

        Returns:
            Tuple of (data_groups, sod_b64, chip_content)
        """
        try:
            logger.info(f"Creating chip LDS data for CMC: {cmc_certificate.cmc_id}")

            # Generate data groups
            data_groups = {}

            # Always create DG1 (MRZ)
            dg1 = self.lds_generator.generate_dg1(cmc_certificate)
            data_groups["DG1"] = dg1

            # Create DG2 (face image) if available
            dg2 = self.lds_generator.generate_dg2(cmc_certificate)
            if dg2:
                data_groups["DG2"] = dg2

            # Generate SOD
            sod_b64 = self.sod_generator.generate_sod(data_groups, signer_certificate)

            # Generate complete chip content
            chip_content = self.lds_generator.generate_chip_content(cmc_certificate, sod_b64)

            logger.info("Chip LDS data created successfully")
        except Exception as e:
            error_msg = f"Failed to create chip LDS data: {e!s}"
            logger.exception(error_msg)
            raise RuntimeError(error_msg) from e
        else:
            return data_groups, sod_b64, chip_content

    def update_cmc_with_lds_data(
        self, cmc_certificate: CMCCertificate, signer_certificate: str | None = None
    ) -> CMCCertificate:
        """Update CMC certificate with LDS data.

        Args:
            cmc_certificate: CMC certificate to update
            signer_certificate: Document signer certificate

        Returns:
            Updated CMC certificate with LDS data
        """
        try:
            # Only process chip-based security model
            if not cmc_certificate.uses_chip_security:
                msg = "LDS data only applicable for chip-based security model"
                raise ValueError(msg)

            # Create LDS data
            data_groups, sod_b64, chip_content = self.create_chip_lds_data(
                cmc_certificate, signer_certificate
            )

            # Update certificate with LDS data
            for dg in data_groups.values():
                cmc_certificate.add_data_group(dg)

            # Set security object and chip content
            cmc_certificate.security_object = sod_b64
            cmc_certificate.chip_content = chip_content
            cmc_certificate.updated_at = datetime.now(tz=timezone.utc)

            logger.info(f"CMC updated with LDS data: {cmc_certificate.cmc_id}")
        except Exception as e:
            error_msg = f"Failed to update CMC with LDS data: {e!s}"
            logger.exception(error_msg)
            raise RuntimeError(error_msg) from e
        else:
            return cmc_certificate


# Global LDS manager instance
_lds_manager: CMCLDSManager | None = None


def get_lds_manager() -> CMCLDSManager:
    """Get or create global LDS manager instance.

    Returns:
        CMC LDS manager instance
    """
    global _lds_manager
    if _lds_manager is None:
        _lds_manager = CMCLDSManager()
    return _lds_manager
