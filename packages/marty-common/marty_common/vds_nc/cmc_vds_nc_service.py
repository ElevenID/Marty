"""VDS-NC Integration with CMC Engine

This module provides integration between the VDS-NC implementation and the CMC Engine service.
"""

from __future__ import annotations

from marty_common.models.passport import CMCCertificate, VDSNCBarcode
from marty_common.vds_nc.vds_nc_impl import VDSNCGenerator, VDSNCVerifier, generate_test_key_pair
from shared.logging_config import get_logger

logger = get_logger(__name__)


class CMCVDSNCService:
    """Service for handling VDS-NC operations for CMC certificates."""

    def __init__(self) -> None:
        """Initialize the VDS-NC service with test keys."""
        # Generate test key pair for development
        # In production, this would load actual signing keys
        self.private_key, self.public_key = generate_test_key_pair()
        self.certificate_reference = "TEST-CMC-001"

        # Initialize generator and verifier
        self.generator = VDSNCGenerator(
            signing_key=self.private_key, certificate_reference=self.certificate_reference
        )
        self.verifier = VDSNCVerifier(public_keys={self.certificate_reference: self.public_key})

        logger.info("CMC VDS-NC service initialized with test keys")

    def generate_barcode(
        self, cmc_certificate: CMCCertificate, signature_algorithm: str = "ES256"
    ) -> VDSNCBarcode:
        """Generate VDS-NC barcode for CMC certificate.

        Args:
            cmc_certificate: CMC certificate to encode
            signature_algorithm: Signature algorithm (default: ES256)

        Returns:
            VDS-NC barcode data
        """
        return self.generator.generate_vds_nc_barcode(cmc_certificate, signature_algorithm)

    def verify_barcode(self, barcode_data: str) -> tuple[bool, CMCCertificate | None, list[str]]:
        """Verify VDS-NC barcode and extract CMC data.

        Args:
            barcode_data: Complete VDS-NC barcode data string

        Returns:
            Tuple of (is_valid, cmc_certificate, error_messages)
        """
        return self.verifier.verify_vds_nc_barcode(barcode_data)

    def get_certificate_reference(self) -> str:
        """Get the certificate reference used for signing.

        Returns:
            Certificate reference string
        """
        return self.certificate_reference


# Global service instance
_vds_nc_service: CMCVDSNCService | None = None


def get_vds_nc_service() -> CMCVDSNCService:
    """Get or create global VDS-NC service instance.

    Returns:
        CMC VDS-NC service instance
    """
    global _vds_nc_service
    if _vds_nc_service is None:
        _vds_nc_service = CMCVDSNCService()
    return _vds_nc_service
