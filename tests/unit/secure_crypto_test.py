import pytest

from marty_common import crypto as crypto_module
from marty_common.native_backends import NativeOperationError


@pytest.mark.parametrize(
    ("algorithm", "key_size"),
    [
        ("RSA", 2048),
        ("EC", 256),
    ],
)
def test_generate_and_sign_verify(algorithm, key_size):
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa

    data = b"test message"
    if algorithm == "RSA":
        private = rsa.generate_private_key(public_exponent=65537, key_size=key_size)
        sig = private.sign(data, padding.PKCS1v15(), hashes.SHA256())
        sig_alg = "RS256"
    else:
        private = ec.generate_private_key(ec.SECP256R1())
        sig = private.sign(data, ec.ECDSA(hashes.SHA256()))
        sig_alg = "ES256"
    pub = private.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    assert crypto_module.verify_signature(data, sig, pub, sig_alg)
    assert not crypto_module.verify_signature(data + b"!", sig, pub, sig_alg)
    with pytest.raises(NativeOperationError, match="Rust managed-KMS"):
        crypto_module.generate_key_pair(algorithm=algorithm, key_size=key_size)
    with pytest.raises(NativeOperationError, match="Rust managed-KMS"):
        crypto_module.sign_data(data, b"private-key-input", sig_alg)


def test_password_hash_roundtrip():
    encoded = crypto_module.hash_password("secret123")
    assert encoded.startswith("pbkdf2-sha256$")
    assert crypto_module.verify_password("secret123", encoded)
    assert not crypto_module.verify_password("wrong", encoded)


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

    with pytest.raises(NativeOperationError, match="verification failed"):
        crypto_module.verify_signature(data, fake_signature, raw_key, "RS256")


def test_password_hashing_rejects_legacy_digest_format():
    assert not crypto_module.verify_password("test", "legacy-sha256")
