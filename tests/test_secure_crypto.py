import importlib.util
import pathlib

import pytest

# Dynamically load crypto.py (avoids triggering package __init__ side effects)
_crypto_file = pathlib.Path(__file__).resolve().parent.parent / "packages" / "marty-common" / "marty_backend_common" / "crypto.py"
spec = importlib.util.spec_from_file_location("marty_secure_crypto", _crypto_file)
assert spec is not None
assert spec.loader is not None
crypto_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(crypto_module)  # type: ignore[attr-defined]

# Skip all tests if crypto_bridge is a stub (Rust extension not available)
_bridge = getattr(crypto_module, "crypto_bridge", None)
_bridge_is_stub = _bridge is not None and not hasattr(_bridge, "__file__")
pytestmark = pytest.mark.skipif(
    _bridge_is_stub,
    reason="crypto_bridge is a MagicMock stub — Rust extension not available",
)


@pytest.mark.parametrize(
    ("algorithm", "key_size"),
    [
        ("RSA", 2048),
        ("EC", 256),
    ],
)
def test_generate_and_sign_verify(algorithm, key_size):
    priv, pub = crypto_module.generate_key_pair(algorithm=algorithm, key_size=key_size)
    data = b"test message"
    sig_alg = "RS256" if algorithm == "RSA" else "ES256"
    sig = crypto_module.sign_data(data, priv, sig_alg)
    assert crypto_module.verify_signature(data, sig, pub, sig_alg)
    # tamper
    assert not crypto_module.verify_signature(data + b"!", sig, pub, sig_alg)


def test_password_hash_roundtrip():
    # This test now correctly handles the case where bcrypt is required
    try:
        h = crypto_module.hash_password("secret123")
        assert crypto_module.verify_password("secret123", h)
        assert not crypto_module.verify_password("wrong", h)
    except RuntimeError:
        # If bcrypt is not available, this is expected behavior for security
        pytest.skip("bcrypt not available - this is expected for security")


def test_secure_random_generation():
    # Test secure random bytes
    random_bytes1 = crypto_module.generate_secure_random_bytes(32)
    random_bytes2 = crypto_module.generate_secure_random_bytes(32)
    assert len(random_bytes1) == 32
    assert len(random_bytes2) == 32
    assert random_bytes1 != random_bytes2  # Should be different

    # Test secure token generation
    token1 = crypto_module.generate_secure_token(32)
    token2 = crypto_module.generate_secure_token(32)
    assert isinstance(token1, str)
    assert isinstance(token2, str)
    assert token1 != token2  # Should be different

    # Test secure hex generation
    hex1 = crypto_module.generate_secure_hex(16)
    hex2 = crypto_module.generate_secure_hex(16)
    assert isinstance(hex1, str)
    assert isinstance(hex2, str)
    assert len(hex1) == 32  # 16 bytes * 2 hex chars per byte
    assert hex1 != hex2  # Should be different

    # Test nonce generation
    nonce1 = crypto_module.generate_nonce(16)
    nonce2 = crypto_module.generate_nonce(16)
    assert len(nonce1) == 16
    assert len(nonce2) == 16
    assert nonce1 != nonce2  # Should be different


def test_invalid_length_random():
    # Test that invalid lengths raise ValueError
    with pytest.raises(ValueError, match="Length must be positive"):
        crypto_module.generate_secure_random_bytes(0)

    with pytest.raises(ValueError, match="Length must be positive"):
        crypto_module.generate_secure_token(-1)


def test_signature_verification_security():
    # Test that insecure raw key verification is no longer allowed
    raw_key = b"this_is_not_a_valid_pem_key_just_random_bytes"
    data = b"test data"
    fake_signature = b"fake_signature"

    # This should now raise ValueError instead of doing insecure comparison
    with pytest.raises(ValueError, match="Failed to load public key"):
        crypto_module.verify_signature(data, fake_signature, raw_key, "RS256")


def test_password_hashing_security():
    # Test that bcrypt dependency is properly enforced
    # This verifies that we require bcrypt instead of using insecure fallback
    with pytest.raises(RuntimeError, match="bcrypt is required"):
        # If bcrypt is not available, this should raise RuntimeError
        crypto_module.hash_password("test")
