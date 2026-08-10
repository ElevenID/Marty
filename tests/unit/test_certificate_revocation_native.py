"""Tests for native OCSP/CRL orchestration."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from digital_identity.application.services.certificate_revocation_service import (
    CertificateRevocationService,
)
from digital_identity.domain.value_objects import RevocationPolicy
from marty_plugin.native_backends import NativeOperationError
from marty_plugin.trust_svc.revocation import RevocationProcessor


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
        self, _certificate: bytes, issuer: bytes, _crl: bytes
    ) -> tuple[bool, str | None]:
        assert issuer == b"issuer"
        if not self.native.signature_valid:
            raise NativeOperationError("CRL signature verification failed")
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


class _OcspResponse:
    status = 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def read(self) -> bytes:
        return b"signed-response"


class _OcspSession:
    def post(self, *_args, **_kwargs) -> _OcspResponse:
        return _OcspResponse()


class _OcspDatabase:
    def __init__(self) -> None:
        self.updated = False

    async def update_dsc_revocation_status(self, *_args) -> None:
        self.updated = True


class _AuthenticatedOcspNative:
    def __init__(self, *, reject: bool = False) -> None:
        self.reject = reject
        self.validated_args: tuple[bytes, bytes, bytes] | None = None

    def build_ocsp_request(self, certificate: bytes, issuer: bytes) -> bytes:
        assert certificate == b"certificate"
        assert issuer == b"issuer"
        return b"request"

    def validate_ocsp_response(
        self, response: bytes, certificate: bytes, issuer: bytes
    ) -> dict[str, object]:
        self.validated_args = (response, certificate, issuer)
        if self.reject:
            raise NativeOperationError("invalid BasicOCSPResponse signature")
        return {
            "cert_status": "good",
            "signature_valid": True,
            "certificate_id_valid": True,
            "freshness_valid": True,
        }

    def hash_data(self, algorithm: str, value: bytes) -> bytes:
        assert algorithm == "sha256"
        assert value == b"certificate"
        return b"hash"


def _revocation_processor(native: _AuthenticatedOcspNative) -> RevocationProcessor:
    processor = RevocationProcessor.__new__(RevocationProcessor)
    processor.native = native
    processor.session = _OcspSession()
    processor.db_manager = _OcspDatabase()
    return processor


@pytest.mark.asyncio
async def test_ocsp_trust_decision_uses_authenticated_native_validation() -> None:
    native = _AuthenticatedOcspNative()
    processor = _revocation_processor(native)

    result = await processor.check_ocsp_status(
        b"certificate", b"issuer", "https://ocsp.invalid"
    )

    assert result["success"] is True
    assert result["status"] == "good"
    assert native.validated_args == (b"signed-response", b"certificate", b"issuer")
    assert processor.db_manager.updated is True


@pytest.mark.asyncio
async def test_invalid_ocsp_signature_fails_closed_without_database_update() -> None:
    native = _AuthenticatedOcspNative(reject=True)
    processor = _revocation_processor(native)

    result = await processor.check_ocsp_status(
        b"certificate", b"issuer", "https://ocsp.invalid"
    )

    assert result["success"] is False
    assert "invalid BasicOCSPResponse signature" in result["error"]
    assert processor.db_manager.updated is False
