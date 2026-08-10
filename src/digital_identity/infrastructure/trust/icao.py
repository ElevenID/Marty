"""Native ICAO trust-profile adapter for eMRTD validation."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from digital_identity.application.ports.trust_profile import (
    ChainValidationResult,
    RefreshResult,
    RevocationCheckResult,
    RevocationStatus,
    TrustAnchor,
    ValidationStatus,
)
from marty_plugin.native_backends import require_backend

logger = logging.getLogger(__name__)


@dataclass
class IcaoTrustProfile:
    """ICAO 9303 trust validation backed exclusively by Rust."""

    trust_store_path: Path
    master_list_sources: list[str]
    pkd_urls: list[str]
    _rust_registry: Any = None
    _chain_validator: Any = None
    _native: Any = None

    def __post_init__(self) -> None:
        self._native = require_backend("marty_verification")
        if self.trust_store_path.exists():
            self._rust_registry = self._native.CscaRegistry.from_directory(
                str(self.trust_store_path)
            )
        else:
            self._rust_registry = self._native.CscaRegistry()

        self._chain_validator = self._native.ChainValidator()
        for pem in self._rust_registry.get_anchors_pem():
            self._chain_validator.add_trust_anchor(pem)

        logger.info(
            "Initialized native ICAO trust profile with %d CSCA anchors",
            len(self._rust_registry),
        )

    async def get_trust_anchors(
        self,
        jurisdiction: str | None = None,
        country_code: str | None = None,
    ) -> list[TrustAnchor]:
        """Return native registry anchors, optionally filtered by country."""
        lookup = (country_code or jurisdiction or "").upper() or None
        country_pems: list[tuple[str | None, str]] = []
        if lookup:
            country_pems.extend(
                (lookup, pem)
                for pem in self._rust_registry.get_country_cscas_pem(lookup)
            )
        else:
            for country in self._rust_registry.supported_countries():
                country_pems.extend(
                    (country, pem)
                    for pem in self._rust_registry.get_country_cscas_pem(country)
                )

        anchors: dict[str, TrustAnchor] = {}
        for country, pem in country_pems:
            der = bytes(self._native.certificate_pem_to_der(pem))
            info = self._native.get_certificate_info(der)
            fingerprint = info["fingerprint_sha256"]
            anchors[fingerprint] = TrustAnchor(
                id=fingerprint,
                subject=info["subject"],
                issuer=info["issuer"],
                serial_number=info["serial_number"],
                valid_from=self._parse_datetime(info["not_before"]),
                valid_until=self._parse_datetime(info["not_after"]),
                certificate_pem=pem,
                certificate_der=der,
                key_usage=list(info["key_usage"]),
                country_code=country,
                metadata={"source": "icao_pkd"},
            )
        return list(anchors.values())

    async def get_anchor_by_id(self, anchor_id: str) -> TrustAnchor | None:
        for anchor in await self.get_trust_anchors():
            if anchor.id == anchor_id:
                return anchor
        return None

    async def validate_chain(
        self,
        certificate_pem: str | None = None,
        certificate_der: bytes | None = None,
    ) -> ChainValidationResult:
        if not certificate_pem and not certificate_der:
            return ChainValidationResult(
                status=ValidationStatus.INVALID,
                errors=["No certificate provided"],
            )

        try:
            if certificate_pem is None:
                certificate_pem = self._native.certificate_der_to_pem(certificate_der)
            result = self._chain_validator.validate_chain([certificate_pem])
            if result.valid:
                return ChainValidationResult(
                    status=ValidationStatus.VALID,
                    trust_anchor_id=result.issuer,
                    chain_length=result.chain_depth,
                    chain_path=[result.subject or "leaf"],
                    warnings=list(result.warnings or []),
                )
            return ChainValidationResult(
                status=ValidationStatus.INVALID,
                errors=list(result.errors or ["Chain validation failed"]),
                warnings=list(result.warnings or []),
            )
        except Exception as exc:
            logger.error("Native ICAO chain validation failed closed: %s", exc)
            return ChainValidationResult(
                status=ValidationStatus.INVALID,
                errors=[f"Validation error: {exc}"],
            )

    async def check_revocation(
        self,
        certificate_pem: str | None = None,
        certificate_der: bytes | None = None,
    ) -> RevocationCheckResult:
        """Report native revocation endpoints; fetching remains orchestration-owned."""
        try:
            if certificate_der is None:
                if certificate_pem is None:
                    raise ValueError("No certificate provided")
                certificate_der = bytes(
                    self._native.certificate_pem_to_der(certificate_pem)
                )
            ocsp_url = self._native.get_ocsp_responder_url(certificate_der)
            crl_urls = list(self._native.get_crl_distribution_points(certificate_der))
            if not ocsp_url and not crl_urls:
                return RevocationCheckResult(
                    status=RevocationStatus.UNKNOWN,
                    errors=["Certificate contains no OCSP or CRL endpoint"],
                )
            return RevocationCheckResult(
                status=RevocationStatus.UNKNOWN,
                errors=["ICAO CRL/OCSP fetch is not configured"],
            )
        except Exception as exc:
            return RevocationCheckResult(
                status=RevocationStatus.UNKNOWN,
                errors=[str(exc)],
            )

    async def refresh(self) -> RefreshResult:
        """Fail closed until a configured PKD synchronization provider is attached."""
        return RefreshResult(
            success=False,
            errors=["ICAO PKD refresh provider is not configured"],
        )

    async def is_issuer_trusted(self, issuer_id: str) -> bool:
        return bool(self._rust_registry.get_country_cscas_pem(issuer_id.upper()))

    @staticmethod
    def _parse_datetime(value: str) -> datetime:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
