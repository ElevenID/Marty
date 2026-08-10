"""Fail-closed orchestration boundary for CMC VDS-NC operations."""

from __future__ import annotations

from typing import Any

from marty_common.models.passport import CMCCertificate, VDSNCBarcode
from marty_common.native_backends import NativeOperationError


class CMCVDSNCService:
    """Delegate VDS-NC operations to an explicitly configured native provider."""

    def __init__(
        self,
        generator: Any | None = None,
        verifier: Any | None = None,
        certificate_reference: str | None = None,
    ) -> None:
        self.generator = generator
        self.verifier = verifier
        self.certificate_reference = certificate_reference

    def generate_barcode(
        self,
        cmc_certificate: CMCCertificate,
        signature_algorithm: str = "ES256",
    ) -> VDSNCBarcode:
        if self.generator is None:
            raise NativeOperationError("CMC VDS-NC generation requires an explicitly configured native signer")
        return self.generator.generate_vds_nc_barcode(
            cmc_certificate,
            signature_algorithm,
        )

    def verify_barcode(
        self,
        barcode_data: str,
    ) -> tuple[bool, CMCCertificate | None, list[str]]:
        if self.verifier is None:
            return False, None, ["CMC VDS-NC verification requires an explicitly configured native verifier"]
        return self.verifier.verify_vds_nc_barcode(barcode_data)

    def get_certificate_reference(self) -> str:
        if not self.certificate_reference:
            raise NativeOperationError("No native VDS-NC signer is configured")
        return self.certificate_reference


_vds_nc_service: CMCVDSNCService | None = None


def get_vds_nc_service() -> CMCVDSNCService:
    """Return the process service without creating development keys."""

    global _vds_nc_service
    if _vds_nc_service is None:
        _vds_nc_service = CMCVDSNCService()
    return _vds_nc_service


__all__ = ["CMCVDSNCService", "get_vds_nc_service"]
