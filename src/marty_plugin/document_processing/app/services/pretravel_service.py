"""
Pre-travel verification and credential issuance service.

This service validates basic inputs (MRZ/barcode/NFC placeholders) and, on success,
issues a tokenized credential using SD-JWT by default or an mdoc placeholder.
It is intentionally lightweight and leverages existing MRZ parsing utilities.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
import os
from typing import Any, Optional

from app.models.doc_models_clean import (
    MRZResult,
    PreTravelVerificationRequest,
    PreTravelVerificationResult,
    TokenizedCredential,
)
from app.services.mrz_service import MRZProcessingService
from cryptography.hazmat.primitives import serialization
from marty_plugin.common.infrastructure.key_vault import (
    FileKeyVaultClient,
    KeyVaultConfig,
    build_key_vault_client,
)
from marty_plugin.common.services.certificate_validation import CertificateValidationService
from marty_plugin.common.verification.trust_list_manager import (
    PKDClient,
    TrustListCache,
    TrustListManager,
    TrustPolicy,
)
from marty_plugin.common.vc.sd_jwt import (
    SdJwtConfig,
    SdJwtIssuanceInput,
    SdJwtIssuer,
)
from marty_plugin.shared.vds_nc.processor import VDSNCProcessor

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PreTravelConfig:
    issuer: str = "https://issuer.pre-travel.example.com"
    signing_key_id: str = "pretravel-signer"
    signing_alg: str = "ES256"
    key_vault_path: str = "data/keys"
    pkd_base_url: str | None = os.getenv("PKD_BASE_URL")
    trust_cache_dir: str = "data/trust"


class PreTravelVerificationService:
    """Handle pre-travel verification and token issuance."""

    def __init__(self, config: PreTravelConfig | None = None) -> None:
        self.config = config or PreTravelConfig()
        kv_config = KeyVaultConfig(provider="file", file_path=self.config.key_vault_path)
        self.key_vault = self._ensure_key_vault(kv_config)
        self.mrz_service = MRZProcessingService()
        self.cert_validator = CertificateValidationService()
        self._trust_manager: TrustListManager | None = None

    @staticmethod
    def _ensure_key_vault(config: KeyVaultConfig) -> FileKeyVaultClient:
        kv = build_key_vault_client(config)
        # Ensure signing key exists
        try:
            import asyncio

            asyncio.run(kv.ensure_key("pretravel-signer", "ecdsa-p256"))  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover - defensive
            logger.exception("Failed to ensure signing key, continuing with existing state")
        return kv  # type: ignore[return-value]

    async def _get_trust_manager(self) -> TrustListManager | None:
        """Lazily initialize trust manager backed by PKD."""
        if self._trust_manager:
            return self._trust_manager

        if not self.config.pkd_base_url:
            logger.warning("PKD base URL not configured; skipping PKD-backed verification")
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
            logger.exception("Failed to initialize trust manager; continuing without PKD")
            return None
        return self._trust_manager

    async def verify_and_issue(
        self, request: PreTravelVerificationRequest
    ) -> PreTravelVerificationResult:
        """
        Perform minimal verification (MRZ parsing today) and issue a token on success.
        NFC/VDS data are accepted but currently not validated beyond presence.
        """
        checks: list[str] = []
        mrz: MRZResult | None = None

        # Basic MRZ validation
        if request.mrz_lines:
            try:
                parsed = self.mrz_service._process_mrz_lines(request.mrz_lines)  # pylint: disable=protected-access
                mrz = parsed
                checks.append("mrz_parsed")
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

        credential: TokenizedCredential | None = None
        if request.issuance_type.lower() == "sd-jwt":
            credential = await self._issue_sd_jwt(request, mrz)
        else:
            # mdoc placeholder until full pipeline is wired
            credential = TokenizedCredential(
                format="mdoc",
                token="mdoc-placeholder",
                disclosures=None,
                presentation_definition=self._build_presentation_definition(request),
            )

        return PreTravelVerificationResult(
            is_valid=True,
            mrz=mrz,
            credential=credential,
            checks=checks,
            vds_valid=vds_valid,
            trust_warnings=trust_warnings or None,
        )

    async def _issue_sd_jwt(
        self, request: PreTravelVerificationRequest, mrz: MRZResult | None
    ) -> TokenizedCredential:
        issuer_cfg = SdJwtConfig(
            issuer=self.config.issuer,
            signing_key_id=self.config.signing_key_id,
            signing_algorithm=self.config.signing_alg,
            kid=self.config.signing_key_id,
        )

        def _empty_chain() -> list[Any]:
            return []

        issuer = SdJwtIssuer(
            key_vault=self.key_vault,
            certificate_chain_provider=_empty_chain,
            config=issuer_cfg,
        )

        base_claims: dict[str, Any] = {}
        if mrz:
            base_claims = {
                "documentNumber": mrz.documentNumber,
                "surname": mrz.surname,
                "givenNames": mrz.givenNames,
                "issuingState": mrz.issuingState,
                "nationality": mrz.nationality,
                "dateOfBirth": mrz.dateOfBirth,
                "dateOfExpiry": mrz.dateOfExpiry,
            }

        selective_disclosures = {
            "barcodeDataPresent": bool(request.barcode_data),
            "nfcPayloadPresent": bool(request.nfc_payload),
        }

        issuance = SdJwtIssuanceInput(
            subject_id=mrz.documentNumber if mrz and mrz.documentNumber else "unknown",
            credential_type=request.credential_type,
            base_claims=base_claims,
            selective_disclosures=selective_disclosures,
            audience=request.audience,
            nonce=request.nonce,
        )

        result = await issuer.issue(issuance)
        return TokenizedCredential(
            format="sd-jwt",
            token=result.token,
            disclosures=result.disclosures,
            presentation_definition=self._build_presentation_definition(request),
        )

    def _build_presentation_definition(
        self, request: PreTravelVerificationRequest
    ) -> dict[str, Any]:
        """
        Minimal OID4VP/OID4VCP-friendly presentation definition stub.
        """
        return {
            "id": "pre-travel-vp",
            "format": {"jwt_vc": {"alg": [self.config.signing_alg]}},
            "input_descriptors": [
                {
                    "id": "pre-travel-credential",
                    "name": request.credential_type,
                    "constraints": {"fields": [{"path": ["$.vc.credentialSubject.documentNumber"]}]},
                }
            ],
        }

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
                public_pem = key.public_key.public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo,
                ).decode("utf-8")
                processor.public_keys[signer_id] = public_pem
                result = processor.verify_vds_nc_document(barcode_data, verify_signature=True)
                return bool(result.is_valid and result.signature_valid), warnings
            warnings.append(f"No PKD key for signer {signer_id}")
            return False, warnings

        # Fallback: verify structure without signature when PKD is unavailable
        warnings.append("PKD not configured; signature not verified")
        result = processor.verify_vds_nc_document(barcode_data, verify_signature=False)
        return bool(result.is_valid), warnings
