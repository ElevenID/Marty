"""Explicit remote custody must not fall back to local PEM files."""

import base64
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from marty_common.infrastructure import key_vault
from marty_common.native_backends import NativeOperationError


@pytest.mark.parametrize("provider", [None, "", "  ", "file", "FILE"])
def test_missing_or_file_provider_rejects_before_directory_or_client_access(
    monkeypatch, tmp_path, provider
):
    def forbidden(*args, **kwargs):
        raise AssertionError("no provider or directory should be opened")

    target = tmp_path / "must-not-be-created"
    monkeypatch.setattr(key_vault.hvac, "Client", forbidden)
    with monkeypatch.context() as context:
        context.setattr(key_vault.Path, "mkdir", forbidden)
        error = (
            NativeOperationError
            if provider and provider.strip().lower() == "file"
            else ValueError
        )
        with pytest.raises(error, match="(custody is retired|explicit managed)"):
            key_vault.build_key_vault_client(
                key_vault.KeyVaultConfig(provider=provider, file_path=str(target))
            )
    assert not target.exists()


def test_retired_file_constructor_does_not_touch_existing_key_data(tmp_path):
    (tmp_path / "old.pem").write_bytes(b"private-data-remains-untouched")
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    with pytest.raises(NativeOperationError, match="custody is retired"):
        key_vault.FileKeyVaultClient(str(tmp_path))
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}


def test_configuration_requires_selection_without_inventing_local_paths():
    config = key_vault.KeyVaultConfig.from_dict({})
    assert config.file_path is None
    with pytest.raises(ValueError, match="explicit managed"):
        key_vault.build_key_vault_client(config)


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["vault", "hashicorp"])
async def test_explicit_transit_keeps_remote_signature_and_public_material(
    monkeypatch, tmp_path, provider
):
    signature = b"remote-provider-test-signature"
    transit = SimpleNamespace(
        sign_data=Mock(
            return_value={
                "data": {
                    "signature": "vault:v1:" + base64.b64encode(signature).decode()
                }
            }
        ),
        read_key=Mock(
            return_value={
                "data": {
                    "latest_version": 3,
                    "keys": {"3": {"public_key": "PUBLIC MATERIAL"}},
                }
            }
        ),
    )
    client = SimpleNamespace(
        secrets=SimpleNamespace(transit=transit), is_authenticated=lambda: True
    )
    constructor = Mock(return_value=client)
    monkeypatch.setattr(key_vault.hvac, "Client", constructor)
    config = key_vault.KeyVaultConfig.from_dict(
        {
            "provider": provider,
            "vault_addr": "https://vault.example.invalid",
            "vault_auth_method": "kubernetes",
            "vault_role": "document-signer",
            "vault_mount_point": "tenant-transit",
        }
    )
    vault = key_vault.build_key_vault_client(config)
    vault._authenticated = True
    assert vault.role == "document-signer"
    assert vault.auth_method == "kubernetes"
    assert vault.mount_point == "tenant-transit"
    constructor.assert_called_once_with(url="https://vault.example.invalid")
    assert await vault.sign("managed-key", b"exact-input", "ecdsa-p256") == signature
    assert await vault.public_material("managed-key") == b"PUBLIC MATERIAL"
    for method, args in (
        (vault.load_private_key, ("managed-key",)),
        (vault.store_private_key, ("managed-key", b"must-not-import")),
    ):
        with pytest.raises(NotImplementedError):
            await method(*args)
    assert list(tmp_path.iterdir()) == []


def test_unimplemented_hsm_provider_does_not_become_a_file_fallback(tmp_path):
    with pytest.raises(NotImplementedError, match="not implemented"):
        key_vault.build_key_vault_client(
            key_vault.KeyVaultConfig(provider="hsm", file_path=str(tmp_path / "unused"))
        )
    assert list(tmp_path.iterdir()) == []
