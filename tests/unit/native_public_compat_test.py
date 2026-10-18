"""Public native compatibility works without reintroducing private custody."""

import importlib.util
from pathlib import Path

import pytest

from marty_common import crypto_bridge
from marty_common.native_backends import NativeBackendUnavailable


def test_optional_public_signature_verifier_accepts_real_rfc8032_vector():
    # RFC 8032 section 7.1, test 1: public key, empty message, public signature.
    public_key = bytes.fromhex(
        "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
    )
    signature = bytes.fromhex(
        "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555f"
        "b8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"
    )
    from marty_common.crypto_bridge import ed25519_verify

    assert ed25519_verify(public_key, b"", signature)
    assert not ed25519_verify(public_key, b"changed", signature)


def test_missing_optional_public_operation_does_not_block_required_verification(
    monkeypatch,
):
    import _marty_rs

    monkeypatch.delattr(_marty_rs, "verify_ed25519", raising=False)
    path = Path(crypto_bridge.__file__)
    spec = importlib.util.spec_from_file_location("isolated_public_bridge", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.compute_check_digit("L898902C3") == "6"
    assert "verify_ed25519" not in module.get_available_functions()["marty_rs"]
    with pytest.raises(NativeBackendUnavailable, match="verify_ed25519"):
        module.verify_ed25519(b"public", b"message", b"signature")


def test_remote_preparation_and_public_conversion_keep_direct_import_compatibility():
    import _marty_rs
    import marty_verification
    from marty_common.crypto_bridge import (
        oid4vci_prepare_sd_jwt,
        oid4vci_assemble_sd_jwt,
        spki_to_raw_public_key,
    )

    assert oid4vci_prepare_sd_jwt is _marty_rs.oid4vci_prepare_sd_jwt
    assert oid4vci_assemble_sd_jwt is _marty_rs.oid4vci_assemble_sd_jwt
    assert spki_to_raw_public_key is marty_verification.spki_to_raw_public_key
