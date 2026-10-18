"""
Pre-travel evidence verification and Rust wallet-offer adapter.

This service checks MRZ consistency, barcode signatures and NFC/SOD evidence.
Rust owns credential offers, wallet proof, credential assembly and KMS signing.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Optional

from app.models.doc_models_clean import (
    MRZResult,
    PreTravelVerificationRequest,
    PreTravelVerificationResult,
)
from app.services.mrz_service import MRZProcessingService
from app.services.pretravel_issuance import (
    PreTravelIssuanceConfig,
    RustPreTravelIssuance,
)
from marty_common.services.certificate_validation import CertificateValidationService
from marty_common.verification.trust_list_manager import (
    PKDClient,
    TrustListCache,
    TrustListManager,
    TrustPolicy,
)

from marty_plugin.shared.vds_nc.processor import VDSNCProcessor

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PreTravelConfig:
    issuance: PreTravelIssuanceConfig = field(default_factory=PreTravelIssuanceConfig)
    credential_type: str = "PreTravelCredential"
    pkd_base_url: str | None = os.getenv("PKD_BASE_URL")
    trust_cache_dir: str = "data/trust"


class PreTravelVerificationService:
    """Verify evidence and request a pending Rust wallet offer."""

    def __init__(
        self,
        config: PreTravelConfig | None = None,
        *,
        issuance: RustPreTravelIssuance | None = None,
    ) -> None:
        self.config = config or PreTravelConfig()
        self.issuance = issuance or RustPreTravelIssuance(self.config.issuance)
        self.mrz_service = MRZProcessingService()
        self.cert_validator = CertificateValidationService()
        self._trust_manager: TrustListManager | None = None

    async def _get_trust_manager(self) -> TrustListManager | None:
        """Lazily initialize trust manager backed by PKD."""
        if self._trust_manager:
            return self._trust_manager

        if not self.config.pkd_base_url:
            logger.warning(
                "PKD base URL not configured; skipping PKD-backed verification"
            )
            return None

        pkd_client = PKDClient(pkd_base_url=self.config.pkd_base_url)
        cache = TrustListCache(cache_dir=self.config.trust_cache_dir)
        manager = TrustListManager(
            pkd_client=pkd_client,
            cache=cache,
            refresh_interval_hours=24,
            trust_policy=TrustPolicy.FAIL_CLOSED,
        )
        try:
            await manager.initialize()
            self._trust_manager = manager
        except Exception:  # pragma: no cover - defensive
            logger.exception(
                "Failed to initialize trust manager; continuing without PKD"
            )
            return None
        return self._trust_manager

    async def verify_and_issue(
        self, request: PreTravelVerificationRequest
    ) -> PreTravelVerificationResult:
        """
        Verify provided evidence and request an offer only after successful checks.
        """
        checks: list[str] = []
        mrz: MRZResult | None = None
        if request.audience is not None or request.nonce is not None:
            raise ValueError(
                "Audience and nonce belong to the Rust wallet proof flow, not pretravel evidence"
            )
        if request.credential_type != self.config.credential_type:
            raise ValueError(
                "Pretravel credential type must match the configured Rust template"
            )
        if request.issuance_type.lower() != "sd-jwt":
            raise ValueError(
                "Pretravel mDoc issuance is not qualified; use the configured SD-JWT wallet flow"
            )

        # Basic MRZ validation
        if request.mrz_lines:
            try:
                parsed = self.mrz_service._process_mrz_lines(request.mrz_lines)  # pylint: disable=protected-access
                if parsed is None or parsed.overallValid is not True:
                    return PreTravelVerificationResult(
                        is_valid=False, reason="MRZ validation failed", checks=checks
                    )
                mrz = parsed
                checks.append("mrz_checksums_valid")
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("MRZ parsing failed")
                return PreTravelVerificationResult(
                    is_valid=False, reason=f"MRZ parsing failed: {exc}", checks=checks
                )

        # VDS validation
        vds_valid: Optional[bool] = None
        trust_warnings: list[str] = []
        if request.barcode_data:
            vds_valid, trust_warnings = await self._verify_vds(request.barcode_data)
            checks.append("barcode_verified" if vds_valid else "barcode_present")
            if vds_valid is False:
                return PreTravelVerificationResult(
                    is_valid=False,
                    reason="VDS-NC signature or trust validation failed",
                    mrz=mrz,
                    checks=checks,
                    vds_valid=vds_valid,
                    trust_warnings=trust_warnings or None,
                )

        # NFC validation
        if request.nfc_payload:
            if not self.cert_validator.validate_sod_certificate(request.nfc_payload):
                return PreTravelVerificationResult(
                    is_valid=False,
                    reason="NFC/SOD validation failed",
                    mrz=mrz,
                    checks=checks,
                    vds_valid=vds_valid,
                    trust_warnings=trust_warnings or None,
                )
            checks.append("nfc_validated")

        is_valid = bool(mrz or request.barcode_data or request.nfc_payload)
        if not is_valid:
            return PreTravelVerificationResult(
                is_valid=False, reason="No verifiable data provided", checks=checks
            )

        claims: dict[str, Any] = {
            "barcodeDataPresent": bool(request.barcode_data),
            "nfcPayloadPresent": bool(request.nfc_payload),
        }
        if mrz:
            claims.update(
                {
                    name: getattr(mrz, name)
                    for name in (
                        "documentNumber",
                        "surname",
                        "givenNames",
                        "issuingState",
                        "nationality",
                        "dateOfBirth",
                        "dateOfExpiry",
                    )
                }
            )
        offer = await self.issuance.offer(claims)

        return PreTravelVerificationResult(
            is_valid=True,
            mrz=mrz,
            wallet_offer=offer,
            checks=checks,
            vds_valid=vds_valid,
            trust_warnings=trust_warnings or None,
        )

    async def _verify_vds(self, barcode_data: str) -> tuple[Optional[bool], list[str]]:
        """Verify VDS-NC barcode with PKD-backed trust when available."""
        warnings: list[str] = []
        processor = VDSNCProcessor(public_keys={})
        try:
            document = processor._decode_barcode_data(barcode_data)  # pylint: disable=protected-access
        except Exception as exc:
            return False, [f"VDS decode failed: {exc}"]

        signer_id = document.payload.header.signer_id
        tm = await self._get_trust_manager()
        if tm:
            key = await tm.get_vds_nc_key(signer_id)
            if key:
                from marty_common import crypto_bridge

                public_pem = crypto_bridge.save_public_key_pem(key.public_key)
                processor.public_keys[signer_id] = public_pem
                result = processor.verify_vds_nc_document(
                    barcode_data, verify_signature=True
                )
                return bool(result.is_valid and result.signature_valid), warnings
            warnings.append(f"No PKD key for signer {signer_id}")
            return False, warnings

        warnings.append("PKD not configured; signature verification is unavailable")
        return False, warnings
