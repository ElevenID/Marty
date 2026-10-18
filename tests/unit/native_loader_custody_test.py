"""Legacy wheel symbols cannot bypass the supported native adapter policy."""

from unittest.mock import AsyncMock

import pytest

from marty_common.native_backends import NativeOperationError, load_native_backend
from marty_plugin.native_backends import require_backend


@pytest.mark.parametrize(
    ("module_name", "private_operation"),
    [
        ("_marty_rs", "vds_nc_sign_profile"),
        ("marty_verification", "build_self_signed_certificate_with_key"),
        ("marty_verification", "rsa_generate"),
    ],
)
def test_private_legacy_function_never_reached_through_either_loader(
    monkeypatch, module_name, private_operation
):
    import importlib

    native = importlib.import_module(module_name)

    def forbidden(*args, **kwargs):
        raise AssertionError("legacy private function was invoked")

    monkeypatch.setattr(native, private_operation, forbidden, raising=False)
    for loader in (load_native_backend, require_backend):
        view = loader(module_name)
        assert private_operation not in dir(view)
        with pytest.raises(NativeOperationError, match="managed-KMS"):
            getattr(view, private_operation)(b"never-process-private-material")
    with pytest.raises(NativeOperationError, match="managed-KMS"):
        load_native_backend(module_name, (private_operation,))


def test_loader_hides_unreviewed_attributes_and_keeps_public_verification(monkeypatch):
    import marty_verification

    monkeypatch.setattr(
        marty_verification, "new_private_signer", lambda: None, raising=False
    )
    view = load_native_backend("marty_verification", ("compute_check_digit",))
    assert view.compute_check_digit("L898902C3") == "6"
    assert not hasattr(view, "new_private_signer")
    assert "new_private_signer" not in dir(view)
    assert "new_private_signer" not in vars(view)


@pytest.mark.parametrize(
    "alias",
    [
        "marty_verification_py",
        "marty_verification_py._marty_verification",
        "_marty_verification",
    ],
)
def test_native_package_alias_cannot_return_an_unfiltered_private_module(
    monkeypatch, alias
):
    import sys
    import marty_verification

    monkeypatch.setitem(sys.modules, alias, marty_verification)
    view = load_native_backend(alias)
    assert view.compute_check_digit("L898902C3") == "6"
    with pytest.raises(NativeOperationError, match="managed-KMS"):
        view.load_private_key_pem("never-process-private-material")


def test_vds_private_sign_adapter_fails_before_native_invocation(monkeypatch):
    import _marty_rs
    from marty_plugin.shared.vds_nc.native import sign_profile

    monkeypatch.setattr(
        _marty_rs,
        "vds_nc_sign_profile",
        lambda *args: pytest.fail("private signer called"),
        raising=False,
    )
    with pytest.raises(NativeOperationError, match="managed-KMS"):
        sign_profile(
            private_key_pem="private-input",
            signer_id="issuer",
            certificate_reference="cert",
            document_type="CMC",
            issuing_country="AUS",
            document_data={},
            algorithm="ES256",
        )


@pytest.mark.asyncio
async def test_missing_dsc_rejects_before_managed_key_creation_or_private_retrieval(
    monkeypatch,
):
    from types import SimpleNamespace
    from marty_common.crypto import document_signer_certificate as certificates

    repository = SimpleNamespace(get=AsyncMock(return_value=None), upsert=AsyncMock())
    vault = SimpleNamespace(ensure_key=AsyncMock(), load_private_key=AsyncMock())
    monkeypatch.setattr(
        certificates, "CertificateRepository", lambda session: repository
    )
    with pytest.raises(NativeOperationError, match="Rust managed-KMS"):
        await certificates.ensure_document_signer_certificate(object(), vault)
    vault.ensure_key.assert_not_called()
    vault.load_private_key.assert_not_called()
    repository.upsert.assert_not_called()


def test_chip_simulator_private_helpers_reject_before_private_serialization():
    from marty_common.security.active_authentication import (
        ActiveAuthenticationProtocol,
        ActiveAuthenticationChallenge,
    )
    from marty_common.security.iso9796_verifier import ISO9796Verifier

    class PrivateKeyTrap:
        def private_bytes(self, *args, **kwargs):
            pytest.fail("private key serialized")

    with pytest.raises(NativeOperationError, match="simulator signing is retired"):
        ActiveAuthenticationProtocol().create_mock_aa_response(
            ActiveAuthenticationChallenge(b"0123456789abcdef", "SHA-256", 128),
            PrivateKeyTrap(),
        )
    with pytest.raises(NativeOperationError, match="simulator signing is retired"):
        ISO9796Verifier().create_test_signature(b"message", PrivateKeyTrap())


@pytest.mark.asyncio
async def test_existing_dsc_record_still_parses_without_key_provider_access(
    monkeypatch,
):
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from marty_common.crypto import document_signer_certificate as certificates

    # A test-only certificate supplies parser input, not managed issuance proof.
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name(
        [x509.NameAttribute(x509.NameOID.COMMON_NAME, "Public test fixture")]
    )
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(datetime(2026, 1, 1, tzinfo=timezone.utc))
        .not_valid_after(datetime(2030, 1, 1, tzinfo=timezone.utc))
        .sign(key, hashes.SHA256())
    )
    repository = SimpleNamespace(
        get=AsyncMock(
            return_value=SimpleNamespace(
                pem=certificate.public_bytes(serialization.Encoding.PEM)
            )
        )
    )
    vault = SimpleNamespace(ensure_key=AsyncMock(), load_private_key=AsyncMock())
    monkeypatch.setattr(
        certificates, "CertificateRepository", lambda session: repository
    )
    parsed = await certificates.ensure_document_signer_certificate(object(), vault)
    assert parsed.to_der() == certificate.public_bytes(serialization.Encoding.DER)
    parsed = await certificates.load_or_create_document_signer_certificate(
        object(), vault
    )
    assert parsed.to_der() == certificate.public_bytes(serialization.Encoding.DER)
    vault.ensure_key.assert_not_called()
    vault.load_private_key.assert_not_called()
