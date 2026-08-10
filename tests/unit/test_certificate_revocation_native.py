"""Tests for native OCSP/CRL orchestration."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from digital_identity.application.services.certificate_revocation_service import (
    CertificateRevocationService,
)
from digital_identity.domain.value_objects import RevocationPolicy
from marty_plugin.native_backends import NativeOperationError


class Native:
    def __init__(self, signature_valid: bool = True) -> None:
        self.signature_valid = signature_valid

    def get_certificate_info(self, _certificate: bytes) -> dict[str, str]:
        return {"issuer": "CN=Issuer"}

    def verify_crl_signature(self, _crl: bytes, _issuer: bytes) -> bool:
        return self.signature_valid


class Processor:
    def __init__(
        self,
        *,
        ocsp_url: str | None = None,
        ocsp_result: dict | None = None,
        crl_urls: list[str] | None = None,
        signature_valid: bool = True,
        revoked: bool = False,
    ) -> None:
        self.native = Native(signature_valid)
        self.ocsp_url = ocsp_url
        self.ocsp_result = ocsp_result
        self.crl_urls = crl_urls or []
        self.revoked = revoked

    def get_ocsp_url_from_certificate(self, _certificate: bytes) -> str | None:
        return self.ocsp_url

    async def check_ocsp_status(
        self, _certificate: bytes, _issuer: bytes, _url: str
    ) -> dict:
        return dict(self.ocsp_result or {})

    def get_crl_urls_from_certificate(self, _certificate: bytes) -> list[str]:
        return self.crl_urls

    async def _fetch_crl_from_url(self, url: str) -> dict:
        return {"success": True, "data": b"crl", "url": url}

    def _crl_der(self, value: bytes) -> bytes:
        return value

    def check_revocation_against_crl(
        self, _certificate: bytes, issuer: str, _crl: bytes
    ) -> tuple[bool, str | None]:
        assert issuer == "CN=Issuer"
        return self.revoked, "key_compromise" if self.revoked else None


def service(processor: Processor) -> CertificateRevocationService:
    return CertificateRevocationService(processor, SimpleNamespace())


@pytest.mark.asyncio
async def test_native_ocsp_good_result() -> None:
    processor = Processor(
        ocsp_url="https://ocsp.invalid",
        ocsp_result={"success": True, "status": "good"},
    )
    result = await service(processor)._check_online(
        b"certificate", RevocationPolicy(), b"issuer"
    )
    assert result == {"is_revoked": False}


@pytest.mark.asyncio
async def test_native_verified_crl_revocation_result() -> None:
    processor = Processor(crl_urls=["https://crl.invalid"], revoked=True)
    result = await service(processor)._check_online(
        b"certificate", RevocationPolicy(), b"issuer"
    )
    assert result == {"is_revoked": True, "reason": "key_compromise"}


@pytest.mark.asyncio
async def test_revocation_source_without_issuer_fails_closed() -> None:
    processor = Processor(crl_urls=["https://crl.invalid"])
    with pytest.raises(NativeOperationError, match="requires the issuer certificate"):
        await service(processor)._check_online(b"certificate", RevocationPolicy())


@pytest.mark.asyncio
async def test_invalid_crl_signature_fails_closed() -> None:
    processor = Processor(crl_urls=["https://crl.invalid"], signature_valid=False)
    with pytest.raises(NativeOperationError, match="signature verification failed"):
        await service(processor)._check_online(
            b"certificate", RevocationPolicy(), b"issuer"
        )
