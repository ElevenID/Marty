"""
Crypto Bridge - Python wrapper for Rust cryptographic operations.

This module provides cryptographic operations using Rust implementations
via the marty-verification crate.

Usage:
    from marty_plugin.common.crypto_bridge import hash_data
    result = hash_data("sha256", data)
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Import the Rust bindings (required)
# First try package-relative import, then try direct import
try:
    from marty_plugin._marty_rs import (
        parse_mrz as _parse_mrz,
        compute_check_digit as _compute_check_digit,
        validate_check_digit as _validate_check_digit,
        parse_crl as _parse_crl,
        check_certificate_revocation as _check_revocation,
        hash_data as _hash_data,
        verify_signature as _verify_signature,
        parse_device_response as _parse_device_response,
        ChainValidator as _ChainValidator,
        ChainValidationResult as _ChainValidationResult,
        ValidationConfig as _ValidationConfig,
        MrzData,
        CrlInfo,
        RevokedCertificate,
        DeviceResponse,
        # KDF operations
        hkdf_sha256 as _hkdf_sha256,
        hkdf_sha384 as _hkdf_sha384,
        pbkdf2_sha256 as _pbkdf2_sha256,
        # Symmetric encryption
        aes_gcm_encrypt as _aes_gcm_encrypt,
        aes_gcm_decrypt as _aes_gcm_decrypt,
        tdes_cbc_encrypt as _tdes_cbc_encrypt,
        tdes_cbc_decrypt as _tdes_cbc_decrypt,
        # Ed25519 operations
        ed25519_generate as _ed25519_generate,
        ed25519_sign as _ed25519_sign,
        ed25519_verify as _ed25519_verify,
        # ECDH key agreement
        x25519_generate as _x25519_generate,
        x25519_agree as _x25519_agree,
        p256_generate as _p256_generate,
        p256_agree as _p256_agree,
        # ECDSA signing
        ecdsa_p256_generate as _ecdsa_p256_generate,
        ecdsa_p384_generate as _ecdsa_p384_generate,
        ecdsa_p256_sign as _ecdsa_p256_sign,
        ecdsa_p384_sign as _ecdsa_p384_sign,
        ecdsa_p256_verify as _ecdsa_p256_verify,
        ecdsa_p384_verify as _ecdsa_p384_verify,
        # RSA signing
        rsa_generate as _rsa_generate,
        rsa_pkcs1_sha256_sign as _rsa_pkcs1_sha256_sign,
        rsa_pkcs1_sha384_sign as _rsa_pkcs1_sha384_sign,
        rsa_pkcs1_sha512_sign as _rsa_pkcs1_sha512_sign,
        rsa_pss_sha256_sign as _rsa_pss_sha256_sign,
        rsa_pss_sha384_sign as _rsa_pss_sha384_sign,
        rsa_pss_sha512_sign as _rsa_pss_sha512_sign,
        rsa_pkcs1_sha256_verify as _rsa_pkcs1_sha256_verify,
        rsa_pkcs1_sha384_verify as _rsa_pkcs1_sha384_verify,
        rsa_pkcs1_sha512_verify as _rsa_pkcs1_sha512_verify,
        rsa_pss_sha256_verify as _rsa_pss_sha256_verify,
        rsa_pss_sha384_verify as _rsa_pss_sha384_verify,
        rsa_pss_sha512_verify as _rsa_pss_sha512_verify,
        # Key generation
        generate_random_bytes as _generate_random_bytes,
        generate_key as _generate_key,
        # JWK/JWS/JWE
        Jwk as _Jwk,
        jwk_generate as _jwk_generate,
        jws_sign as _jws_sign,
        jws_verify as _jws_verify,
        jwe_encrypt as _jwe_encrypt,
        jwe_decrypt as _jwe_decrypt,
        open_badge_ob2_issue as _open_badge_ob2_issue,
        open_badge_ob2_verify as _open_badge_ob2_verify,
        open_badge_ob3_issue as _open_badge_ob3_issue,
        open_badge_ob3_verify as _open_badge_ob3_verify,
        dtc_create as _dtc_create,
        dtc_sign as _dtc_sign,
        dtc_verify as _dtc_verify,
        # Certificate operations
        load_certificate_pem as _load_certificate_pem,
        load_certificate_der as _load_certificate_der,
        get_certificate_info as _get_certificate_info,
        certificate_pem_to_der as _certificate_pem_to_der,
        certificate_der_to_pem as _certificate_der_to_pem,
        get_certificate_public_key as _get_certificate_public_key,
        is_certificate_expired as _is_certificate_expired,
        is_certificate_not_yet_valid as _is_certificate_not_yet_valid,
        verify_certificate_signature as _verify_certificate_signature,
        # Key serialization
        load_private_key_pem as _load_private_key_pem,
        load_private_key_der as _load_private_key_der,
        save_private_key_pem as _save_private_key_pem,
        load_public_key_pem as _load_public_key_pem,
        load_public_key_der as _load_public_key_der,
        save_public_key_pem as _save_public_key_pem,
        extract_public_key as _extract_public_key,
        detect_private_key_type as _detect_private_key_type,
        detect_public_key_type as _detect_public_key_type,
        get_key_size as _get_key_size,
        raw_private_key_to_pkcs8 as _raw_private_key_to_pkcs8,
        raw_public_key_to_spki as _raw_public_key_to_spki,
        pkcs8_to_raw_private_key as _pkcs8_to_raw_private_key,
        spki_to_raw_public_key as _spki_to_raw_public_key,
        # Ed448 operations
        ed448_generate as _ed448_generate,
        ed448_sign as _ed448_sign,
        ed448_verify as _ed448_verify,
        # PKCS#12 operations
        Pkcs12Data as _Pkcs12Data,
        pkcs12_parse as _pkcs12_parse,
        # ISO 9796-2 operations
        iso9796_verify as _iso9796_verify,
        iso9796_recover as _iso9796_recover,
        # OCSP operations
        build_ocsp_request as _build_ocsp_request,
        get_ocsp_responder_url as _get_ocsp_responder_url,
        parse_ocsp_response as _parse_ocsp_response,
    )
except ImportError:
    # Fall back to direct import (when installed standalone via maturin)
    from _marty_rs import (
        parse_mrz as _parse_mrz,
        compute_check_digit as _compute_check_digit,
        validate_check_digit as _validate_check_digit,
        parse_crl as _parse_crl,
        check_certificate_revocation as _check_revocation,
        hash_data as _hash_data,
        verify_signature as _verify_signature,
        parse_device_response as _parse_device_response,
        ChainValidator as _ChainValidator,
        ChainValidationResult as _ChainValidationResult,
        ValidationConfig as _ValidationConfig,
        MrzData,
        CrlInfo,
        RevokedCertificate,
        DeviceResponse,
        hkdf_sha256 as _hkdf_sha256,
        hkdf_sha384 as _hkdf_sha384,
        pbkdf2_sha256 as _pbkdf2_sha256,
        aes_gcm_encrypt as _aes_gcm_encrypt,
        aes_gcm_decrypt as _aes_gcm_decrypt,
        tdes_cbc_encrypt as _tdes_cbc_encrypt,
        tdes_cbc_decrypt as _tdes_cbc_decrypt,
        ed25519_generate as _ed25519_generate,
        ed25519_sign as _ed25519_sign,
        ed25519_verify as _ed25519_verify,
        x25519_generate as _x25519_generate,
        x25519_agree as _x25519_agree,
        p256_generate as _p256_generate,
        p256_agree as _p256_agree,
        ecdsa_p256_generate as _ecdsa_p256_generate,
        ecdsa_p384_generate as _ecdsa_p384_generate,
        ecdsa_p256_sign as _ecdsa_p256_sign,
        ecdsa_p384_sign as _ecdsa_p384_sign,
        ecdsa_p256_verify as _ecdsa_p256_verify,
        ecdsa_p384_verify as _ecdsa_p384_verify,
        rsa_generate as _rsa_generate,
        rsa_pkcs1_sha256_sign as _rsa_pkcs1_sha256_sign,
        rsa_pkcs1_sha384_sign as _rsa_pkcs1_sha384_sign,
        rsa_pkcs1_sha512_sign as _rsa_pkcs1_sha512_sign,
        rsa_pss_sha256_sign as _rsa_pss_sha256_sign,
        rsa_pss_sha384_sign as _rsa_pss_sha384_sign,
        rsa_pss_sha512_sign as _rsa_pss_sha512_sign,
        rsa_pkcs1_sha256_verify as _rsa_pkcs1_sha256_verify,
        rsa_pkcs1_sha384_verify as _rsa_pkcs1_sha384_verify,
        rsa_pkcs1_sha512_verify as _rsa_pkcs1_sha512_verify,
        rsa_pss_sha256_verify as _rsa_pss_sha256_verify,
        rsa_pss_sha384_verify as _rsa_pss_sha384_verify,
        rsa_pss_sha512_verify as _rsa_pss_sha512_verify,
        generate_random_bytes as _generate_random_bytes,
        generate_key as _generate_key,
        Jwk as _Jwk,
        jwk_generate as _jwk_generate,
        jws_sign as _jws_sign,
        jws_verify as _jws_verify,
        jwe_encrypt as _jwe_encrypt,
        jwe_decrypt as _jwe_decrypt,
        open_badge_ob2_issue as _open_badge_ob2_issue,
        open_badge_ob2_verify as _open_badge_ob2_verify,
        open_badge_ob3_issue as _open_badge_ob3_issue,
        open_badge_ob3_verify as _open_badge_ob3_verify,
        dtc_create as _dtc_create,
        dtc_sign as _dtc_sign,
        dtc_verify as _dtc_verify,
        load_certificate_pem as _load_certificate_pem,
        load_certificate_der as _load_certificate_der,
        get_certificate_info as _get_certificate_info,
        certificate_pem_to_der as _certificate_pem_to_der,
        certificate_der_to_pem as _certificate_der_to_pem,
        get_certificate_public_key as _get_certificate_public_key,
        is_certificate_expired as _is_certificate_expired,
        is_certificate_not_yet_valid as _is_certificate_not_yet_valid,
        verify_certificate_signature as _verify_certificate_signature,
        load_private_key_pem as _load_private_key_pem,
        load_private_key_der as _load_private_key_der,
        save_private_key_pem as _save_private_key_pem,
        load_public_key_pem as _load_public_key_pem,
        load_public_key_der as _load_public_key_der,
        save_public_key_pem as _save_public_key_pem,
        extract_public_key as _extract_public_key,
        detect_private_key_type as _detect_private_key_type,
        detect_public_key_type as _detect_public_key_type,
        get_key_size as _get_key_size,
        raw_private_key_to_pkcs8 as _raw_private_key_to_pkcs8,
        raw_public_key_to_spki as _raw_public_key_to_spki,
        pkcs8_to_raw_private_key as _pkcs8_to_raw_private_key,
        spki_to_raw_public_key as _spki_to_raw_public_key,
        ed448_generate as _ed448_generate,
        ed448_sign as _ed448_sign,
        ed448_verify as _ed448_verify,
        Pkcs12Data as _Pkcs12Data,
        pkcs12_parse as _pkcs12_parse,
        iso9796_verify as _iso9796_verify,
        iso9796_recover as _iso9796_recover,
        build_ocsp_request as _build_ocsp_request,
        get_ocsp_responder_url as _get_ocsp_responder_url,
        parse_ocsp_response as _parse_ocsp_response,
    )


# =============================================================================
# Hash Operations
# =============================================================================

def hash_data(algorithm: str, data: bytes) -> bytes:
    """
    Hash data using the specified algorithm.
    
    Args:
        algorithm: Hash algorithm name ("sha1", "sha256", "sha384", "sha512")
        data: Data to hash
        
    Returns:
        Hash digest as bytes
        
    Raises:
        ValueError: If algorithm is not supported
        NotImplementedError: If Rust bindings are not available
    """
    return bytes(_hash_data(algorithm, data))


def sha256(data: bytes) -> bytes:
    """Compute SHA-256 hash."""
    return hash_data("sha256", data)


def sha384(data: bytes) -> bytes:
    """Compute SHA-384 hash."""
    return hash_data("sha384", data)


def sha512(data: bytes) -> bytes:
    """Compute SHA-512 hash."""
    return hash_data("sha512", data)


def sha1(data: bytes) -> bytes:
    """Compute SHA-1 hash (legacy)."""
    return hash_data("sha1", data)


# =============================================================================
# Signature Verification
# =============================================================================

def verify_signature(
    algorithm: str,
    public_key_der: bytes,
    message: bytes,
    signature: bytes,
) -> bool:
    """
    Verify a cryptographic signature.
    
    Args:
        algorithm: Signature algorithm (e.g., "ecdsa-p256-sha256", "rsa-pkcs1-sha256")
        public_key_der: DER-encoded public key (SubjectPublicKeyInfo)
        message: The message that was signed
        signature: The signature bytes
        
    Returns:
        True if signature is valid, False otherwise
    """
    return _verify_signature(algorithm, public_key_der, message, signature)


# =============================================================================
# MRZ Operations
# =============================================================================

def parse_mrz(lines: list[str]) -> "MrzData | dict":
    """
    Parse MRZ from lines of text.
    
    Args:
        lines: List of MRZ lines (2 for TD3/TD2, 3 for TD1)
        
    Returns:
        MrzData object with parsed information
    """
    return _parse_mrz(lines)


def compute_check_digit(input_string: str) -> str:
    """
    Calculate ICAO check digit for a string.
    
    Args:
        input_string: The string to calculate check digit for
        
    Returns:
        Single digit character '0'-'9'
    """
    return _compute_check_digit(input_string)


def validate_check_digit(data: str, check_digit: str) -> bool:
    """
    Validate a check digit.
    
    Args:
        data: The data portion (without check digit)
        check_digit: The check digit to validate
        
    Returns:
        True if the check digit is correct
    """
    return _validate_check_digit(data, check_digit)


# =============================================================================
# CRL Operations  
# =============================================================================

def parse_crl(der_bytes: bytes) -> "CrlInfo | dict":
    """
    Parse a DER-encoded CRL.
    
    Args:
        der_bytes: DER-encoded CRL bytes
        
    Returns:
        CrlInfo object with parsed information
    """
    return _parse_crl(der_bytes)


def check_certificate_revocation(
    cert_serial: str,
    cert_issuer: str,
    crl_der: bytes,
) -> tuple[bool, str | None]:
    """
    Check if a certificate is revoked according to a CRL.
    
    Args:
        cert_serial: Certificate serial number (hex string)
        cert_issuer: Certificate issuer DN
        crl_der: DER-encoded CRL
        
    Returns:
        Tuple of (is_revoked: bool, reason: Optional[str])
    """
    return _check_revocation(cert_serial, cert_issuer, crl_der)


# =============================================================================
# mDL Document Parsing
# =============================================================================

def parse_device_response(cbor_bytes: bytes) -> "DeviceResponse | dict":
    """
    Parse a CBOR-encoded DeviceResponse.
    
    Args:
        cbor_bytes: CBOR-encoded DeviceResponse bytes
        
    Returns:
        DeviceResponse object with parsed information
    """
    return _parse_device_response(cbor_bytes)


# =============================================================================
# Certificate Chain Validation
# =============================================================================


class ValidationConfig:
    """
    Configuration for certificate chain validation.
    
    Allows Python code to pass policy parameters to the Rust chain validator.
    
    Example:
        # Use a preset configuration
        config = ValidationConfig.soft_fail_revocation()
        
        # Or create a custom configuration
        config = ValidationConfig(
            check_crl=True,
            check_ocsp=True,
            revocation_mode="soft_fail",
            required_key_usage=["digital_signature"],
        )
        
        result = validator.validate_with_config(chain_pem, config)
    """
    
    def __init__(
        self,
        check_crl: bool = False,
        check_ocsp: bool = False,
        revocation_mode: str = "soft_fail",
        validation_moment: str | None = None,
        required_key_usage: list[str] | None = None,
        certificate_type: str = "any",
        ocsp_responder_url: str | None = None,
        ocsp_timeout_secs: int = 10,
    ):
        """
        Initialize validation configuration.
        
        Args:
            check_crl: Whether to check CRL revocation
            check_ocsp: Whether to check OCSP revocation
            revocation_mode: "hard_fail", "soft_fail", or "none"
            validation_moment: ISO 8601 timestamp for point-in-time validation
            required_key_usage: Required key usages (e.g., ["digital_signature"])
            certificate_type: "csca", "ds", "intermediate", or "any"
            ocsp_responder_url: Override OCSP responder URL
            ocsp_timeout_secs: OCSP request timeout in seconds
        """
        self._inner = _ValidationConfig(
            check_crl=check_crl,
            check_ocsp=check_ocsp,
            revocation_mode=revocation_mode,
            validation_moment=validation_moment,
            required_key_usage=required_key_usage or [],
            certificate_type=certificate_type,
            ocsp_responder_url=ocsp_responder_url,
            ocsp_timeout_secs=ocsp_timeout_secs,
        )
    
    @classmethod
    def soft_fail_revocation(cls) -> "ValidationConfig":
        """Create a config for soft-fail revocation checking."""
        instance = cls.__new__(cls)
        instance._inner = _ValidationConfig.soft_fail_revocation()
        return instance
    
    @classmethod
    def hard_fail_revocation(cls) -> "ValidationConfig":
        """Create a config for hard-fail revocation checking."""
        instance = cls.__new__(cls)
        instance._inner = _ValidationConfig.hard_fail_revocation()
        return instance
    
    @classmethod
    def csca_validation(cls) -> "ValidationConfig":
        """Create a config for CSCA (Country Signing CA) validation."""
        instance = cls.__new__(cls)
        instance._inner = _ValidationConfig.csca_validation()
        return instance
    
    @classmethod
    def dsc_validation(cls) -> "ValidationConfig":
        """Create a config for Document Signer certificate validation."""
        instance = cls.__new__(cls)
        instance._inner = _ValidationConfig.dsc_validation()
        return instance
    
    @property
    def check_crl(self) -> bool:
        return self._inner.check_crl
    
    @property
    def check_ocsp(self) -> bool:
        return self._inner.check_ocsp
    
    @property
    def revocation_mode(self) -> str:
        return self._inner.revocation_mode
    
    @property
    def certificate_type(self) -> str:
        return self._inner.certificate_type
    
    def to_dict(self) -> dict:
        return self._inner.to_dict()
    
    def __repr__(self) -> str:
        return repr(self._inner)


class CertificateChainValidator:
    """
    X.509 Certificate chain validator using Rust implementation.
    
    This class provides certificate chain validation functionality that can
    replace the Python certvalidator library.
    
    Example:
        validator = CertificateChainValidator()
        validator.add_trust_anchor(root_ca_pem)
        validator.add_intermediate(intermediate_ca_pem)
        
        result = validator.validate_chain([end_entity_pem, intermediate_pem])
        if result.valid:
            print("Chain is valid!")
        else:
            print(f"Validation failed: {result.errors}")
    """
    
    def __init__(self):
        """Initialize the chain validator."""
        self._inner = _ChainValidator()
    
    def add_trust_anchor(self, pem: str) -> None:
        """
        Add a trust anchor (root CA) from PEM.
        
        Args:
            pem: PEM-encoded root CA certificate
        """
        self._inner.add_trust_anchor(pem)
    
    def add_trust_anchor_der(self, der: bytes) -> None:
        """
        Add a trust anchor (root CA) from DER bytes.
        
        Args:
            der: DER-encoded root CA certificate
        """
        self._inner.add_trust_anchor_der(der)
    
    def add_intermediate(self, pem: str) -> None:
        """
        Add an intermediate certificate from PEM.
        
        Args:
            pem: PEM-encoded intermediate certificate
        """
        self._inner.add_intermediate(pem)
    
    def add_intermediate_der(self, der: bytes) -> None:
        """
        Add an intermediate certificate from DER bytes.
        
        Args:
            der: DER-encoded intermediate certificate
        """
        self._inner.add_intermediate_der(der)
    
    def add_crl(self, crl_der: bytes) -> None:
        """
        Add a CRL for revocation checking.
        
        Args:
            crl_der: DER-encoded CRL
        """
        self._inner.add_crl(crl_der)
    
    def validate_chain(self, chain_pem: list[str]) -> "ChainValidationResult":
        """
        Validate a certificate chain.
        
        Args:
            chain_pem: List of PEM-encoded certificates, ordered from end-entity to root
            
        Returns:
            ChainValidationResult with validation status
        """
        return self._inner.validate_chain(chain_pem)
    
    def validate_certificate(self, cert_pem: str) -> "ChainValidationResult":
        """
        Validate a single certificate.
        
        Args:
            cert_pem: PEM-encoded certificate
            
        Returns:
            ChainValidationResult with validation status
        """
        return self._inner.validate_certificate(cert_pem)
    
    def validate_with_config(
        self, chain_pem: list[str], config: ValidationConfig
    ) -> "ChainValidationResult":
        """
        Validate a certificate chain with custom configuration.
        
        This method applies policy-based validation with configurable revocation
        checking, key usage requirements, and certificate type constraints.
        
        Args:
            chain_pem: List of PEM-encoded certificates, ordered from end-entity to root
            config: ValidationConfig with policy parameters
            
        Returns:
            ChainValidationResult with validation status
        """
        return self._inner.validate_with_config(chain_pem, config._inner)
    
    @classmethod
    def with_config(cls, config: ValidationConfig) -> "CertificateChainValidator":
        """
        Create a new chain validator with a specific configuration.
        
        Args:
            config: ValidationConfig with policy parameters
            
        Returns:
            A new CertificateChainValidator configured with the given policy
        """
        instance = cls.__new__(cls)
        instance._inner = _ChainValidator.with_config(config._inner)
        return instance


class ChainValidationResult:
    """Result of certificate chain validation."""
    
    def __init__(self, valid: bool, subject: str | None = None, issuer: str | None = None,
                 chain_depth: int = 0, errors: list[str] | None = None,
                 warnings: list[str] | None = None):
        self.valid = valid
        self.subject = subject
        self.issuer = issuer
        self.chain_depth = chain_depth
        self.errors = errors or []
        self.warnings = warnings or []
    
    def __repr__(self) -> str:
        return f"ChainValidationResult(valid={self.valid}, subject={self.subject!r})"
    
    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "subject": self.subject,
            "issuer": self.issuer,
            "chain_depth": self.chain_depth,
            "errors": self.errors,
            "warnings": self.warnings,
        }


# =============================================================================
# KDF Operations
# =============================================================================

def hkdf_sha256(ikm: bytes, salt: bytes | None, info: bytes, length: int) -> bytes:
    """
    Derive a key using HKDF-SHA256.
    
    Args:
        ikm: Input keying material
        salt: Optional salt value (can be None or empty)
        info: Context and application specific information
        length: Length of output keying material in bytes
        
    Returns:
        Derived key material
    """
    return bytes(_hkdf_sha256(ikm, salt or b"", info, length))
def hkdf_sha384(ikm: bytes, salt: bytes | None, info: bytes, length: int) -> bytes:
    """
    Derive a key using HKDF-SHA384.
    
    Args:
        ikm: Input keying material
        salt: Optional salt value (can be None or empty)
        info: Context and application specific information
        length: Length of output keying material in bytes
        
    Returns:
        Derived key material
    """
    return bytes(_hkdf_sha384(ikm, salt or b"", info, length))
def pbkdf2_sha256(password: bytes, salt: bytes, iterations: int, length: int) -> bytes:
    """
    Derive a key using PBKDF2-HMAC-SHA256.
    
    Args:
        password: Password bytes
        salt: Salt bytes
        iterations: Number of iterations
        length: Desired key length in bytes
        
    Returns:
        Derived key
    """
    return bytes(_pbkdf2_sha256(password, salt, iterations, length))
# =============================================================================
# Symmetric Encryption
# =============================================================================

def aes_gcm_encrypt(
    key: bytes,
    plaintext: bytes,
    aad: bytes | None = None,
    nonce: bytes | None = None,
) -> tuple[bytes, bytes, bytes]:
    """
    Encrypt data using AES-GCM.
    
    Args:
        key: AES key (16 or 32 bytes)
        plaintext: Data to encrypt
        aad: Optional additional authenticated data
        nonce: Optional 12-byte nonce (random if not provided)
        
    Returns:
        Tuple of (nonce, ciphertext, tag)
    """
    import os
    
    # Generate nonce if not provided
    if nonce is None:
        nonce = os.urandom(12)
    elif len(nonce) != 12:
        raise ValueError("Nonce must be 12 bytes")
    
    result = bytes(_aes_gcm_encrypt(key, nonce, plaintext, aad or b""))
    # Rust returns ciphertext with tag appended
    ciphertext = result[:-16]
    tag = result[-16:]
    return (nonce, ciphertext, tag)
def aes_gcm_decrypt(key: bytes, nonce: bytes, ciphertext: bytes, aad: bytes | None, tag: bytes) -> bytes:
    """
    Decrypt data using AES-GCM.
    
    Args:
        key: AES key (16 or 32 bytes)
        nonce: 12-byte nonce used for encryption
        ciphertext: Encrypted data (without tag)
        aad: Optional additional authenticated data
        tag: 16-byte authentication tag
        
    Returns:
        Decrypted plaintext
        
    Raises:
        ValueError: If authentication fails
    """
    # Rust expects ciphertext + tag concatenated
    return bytes(_aes_gcm_decrypt(key, nonce, ciphertext + tag, aad or b""))
def tdes_cbc_encrypt(key: bytes, plaintext: bytes, iv: bytes) -> bytes:
    """
    Encrypt data using Triple-DES in CBC mode (no padding).
    
    This is used for BAC/PACE protocols in eMRTD.
    
    Args:
        key: 24-byte 3DES key
        plaintext: Data to encrypt (must be multiple of 8 bytes)
        iv: 8-byte initialization vector
        
    Returns:
        Ciphertext
    """
    return bytes(_tdes_cbc_encrypt(key, plaintext, iv))
def tdes_cbc_decrypt(key: bytes, ciphertext: bytes, iv: bytes) -> bytes:
    """
    Decrypt data using Triple-DES in CBC mode (no padding).
    
    Args:
        key: 24-byte 3DES key
        ciphertext: Data to decrypt (must be multiple of 8 bytes)
        iv: 8-byte initialization vector
        
    Returns:
        Plaintext
    """
    return bytes(_tdes_cbc_decrypt(key, ciphertext, iv))
# =============================================================================
# Ed25519 Signing
# =============================================================================

def ed25519_generate() -> tuple[bytes, bytes]:
    """
    Generate an Ed25519 keypair.
    
    Returns:
        Tuple of (private_key_seed, public_key) - both 32 bytes
    """
    result = _ed25519_generate()
    return (bytes(result[0]), bytes(result[1]))
def ed25519_sign(private_key_seed: bytes, message: bytes) -> bytes:
    """
    Sign a message with an Ed25519 private key.
    
    Args:
        private_key_seed: 32-byte private key seed
        message: Message to sign
        
    Returns:
        64-byte signature
    """
    return bytes(_ed25519_sign(private_key_seed, message))
def ed25519_verify(public_key: bytes, message: bytes, signature: bytes) -> bool:
    """
    Verify an Ed25519 signature.
    
    Args:
        public_key: 32-byte public key
        message: Message that was signed
        signature: 64-byte signature
        
    Returns:
        True if signature is valid, False otherwise
    """
    return _ed25519_verify(public_key, message, signature)
# =============================================================================
# ECDH Key Agreement
# =============================================================================

def x25519_generate() -> tuple[bytes, bytes]:
    """
    Generate an X25519 keypair.
    
    Returns:
        Tuple of (private_key, public_key) - both 32 bytes
    """
    result = _x25519_generate()
    return (bytes(result[0]), bytes(result[1]))
def x25519_agree(private_key: bytes, peer_public_key: bytes) -> bytes:
    """
    Perform X25519 key agreement.
    
    Args:
        private_key: 32-byte private key
        peer_public_key: 32-byte peer public key
        
    Returns:
        32-byte shared secret
    """
    return bytes(_x25519_agree(private_key, peer_public_key))
def p256_generate() -> tuple[bytes, bytes]:
    """
    Generate an NIST P-256 keypair.
    
    Returns:
        Tuple of (private_key_bytes, public_key_bytes)
        Private key is 32 bytes, public key is 65 bytes (uncompressed)
    """
    result = _p256_generate()
    return (bytes(result[0]), bytes(result[1]))
def p256_agree(private_key: bytes, peer_public_key: bytes) -> bytes:
    """
    Perform P-256 ECDH key agreement.
    
    Args:
        private_key: 32-byte private key scalar
        peer_public_key: 65-byte uncompressed public key
        
    Returns:
        32-byte shared secret (x-coordinate of shared point)
    """
    return bytes(_p256_agree(private_key, peer_public_key))
# =============================================================================
# ECDSA Signing
# =============================================================================

def ecdsa_p256_generate() -> tuple[bytes, bytes]:
    """
    Generate an ECDSA P-256 keypair for signing.
    
    Returns:
        Tuple of (private_key, public_key)
        Private key is 32 bytes, public key is 65 bytes (uncompressed)
    """
    result = _ecdsa_p256_generate()
    return (bytes(result[0]), bytes(result[1]))
def ecdsa_p384_generate() -> tuple[bytes, bytes]:
    """
    Generate an ECDSA P-384 keypair for signing.
    
    Returns:
        Tuple of (private_key, public_key)
        Private key is 48 bytes, public key is 97 bytes (uncompressed)
    """
    result = _ecdsa_p384_generate()
    return (bytes(result[0]), bytes(result[1]))
def ecdsa_p256_sign(private_key: bytes, message: bytes) -> bytes:
    """
    Sign a message with ECDSA P-256 SHA-256 (ES256).
    
    Args:
        private_key: 32-byte private key scalar
        message: Message to sign
        
    Returns:
        DER-encoded signature
    """
    return bytes(_ecdsa_p256_sign(private_key, message))
def ecdsa_p384_sign(private_key: bytes, message: bytes) -> bytes:
    """
    Sign a message with ECDSA P-384 SHA-384 (ES384).
    
    Args:
        private_key: 48-byte private key scalar
        message: Message to sign
        
    Returns:
        DER-encoded signature
    """
    return bytes(_ecdsa_p384_sign(private_key, message))
def ecdsa_p256_verify(public_key: bytes, message: bytes, signature: bytes) -> bool:
    """
    Verify an ECDSA P-256 SHA-256 signature.
    
    Args:
        public_key: 65-byte uncompressed public key
        message: Message that was signed
        signature: DER-encoded signature
        
    Returns:
        True if signature is valid, False otherwise
    """
    return _ecdsa_p256_verify(public_key, message, signature)
def ecdsa_p384_verify(public_key: bytes, message: bytes, signature: bytes) -> bool:
    """
    Verify an ECDSA P-384 SHA-384 signature.
    
    Args:
        public_key: 97-byte uncompressed public key
        message: Message that was signed
        signature: DER-encoded signature
        
    Returns:
        True if signature is valid, False otherwise
    """
    return _ecdsa_p384_verify(public_key, message, signature)
# =============================================================================
# RSA Signing
# =============================================================================

def rsa_generate(bits: int = 2048) -> tuple[bytes, bytes]:
    """
    Generate an RSA keypair.
    
    Args:
        bits: Key size in bits (2048, 3072, or 4096)
        
    Returns:
        Tuple of (private_key_der, public_key_der) in PKCS#8 and SPKI format
    """
    result = _rsa_generate(bits)
    return (bytes(result[0]), bytes(result[1]))
def rsa_pkcs1_sha256_sign(private_key_der: bytes, message: bytes) -> bytes:
    """Sign a message with RSA PKCS#1 v1.5 SHA-256 (RS256)."""
    return bytes(_rsa_pkcs1_sha256_sign(private_key_der, message))
def rsa_pkcs1_sha384_sign(private_key_der: bytes, message: bytes) -> bytes:
    """Sign a message with RSA PKCS#1 v1.5 SHA-384 (RS384)."""
    return bytes(_rsa_pkcs1_sha384_sign(private_key_der, message))
def rsa_pkcs1_sha512_sign(private_key_der: bytes, message: bytes) -> bytes:
    """Sign a message with RSA PKCS#1 v1.5 SHA-512 (RS512)."""
    return bytes(_rsa_pkcs1_sha512_sign(private_key_der, message))
def rsa_pss_sha256_sign(private_key_der: bytes, message: bytes) -> bytes:
    """Sign a message with RSA-PSS SHA-256 (PS256)."""
    return bytes(_rsa_pss_sha256_sign(private_key_der, message))
def rsa_pss_sha384_sign(private_key_der: bytes, message: bytes) -> bytes:
    """Sign a message with RSA-PSS SHA-384 (PS384)."""
    return bytes(_rsa_pss_sha384_sign(private_key_der, message))
def rsa_pss_sha512_sign(private_key_der: bytes, message: bytes) -> bytes:
    """Sign a message with RSA-PSS SHA-512 (PS512)."""
    return bytes(_rsa_pss_sha512_sign(private_key_der, message))
def rsa_pkcs1_sha256_verify(public_key_der: bytes, message: bytes, signature: bytes) -> bool:
    """Verify an RSA PKCS#1 v1.5 SHA-256 signature."""
    return _rsa_pkcs1_sha256_verify(public_key_der, message, signature)
def rsa_pkcs1_sha384_verify(public_key_der: bytes, message: bytes, signature: bytes) -> bool:
    """Verify an RSA PKCS#1 v1.5 SHA-384 signature."""
    return _rsa_pkcs1_sha384_verify(public_key_der, message, signature)
def rsa_pkcs1_sha512_verify(public_key_der: bytes, message: bytes, signature: bytes) -> bool:
    """Verify an RSA PKCS#1 v1.5 SHA-512 signature."""
    return _rsa_pkcs1_sha512_verify(public_key_der, message, signature)
def rsa_pss_sha256_verify(public_key_der: bytes, message: bytes, signature: bytes) -> bool:
    """Verify an RSA-PSS SHA-256 signature."""
    return _rsa_pss_sha256_verify(public_key_der, message, signature)
def rsa_pss_sha384_verify(public_key_der: bytes, message: bytes, signature: bytes) -> bool:
    """Verify an RSA-PSS SHA-384 signature."""
    return _rsa_pss_sha384_verify(public_key_der, message, signature)
def rsa_pss_sha512_verify(public_key_der: bytes, message: bytes, signature: bytes) -> bool:
    """Verify an RSA-PSS SHA-512 signature."""
    return _rsa_pss_sha512_verify(public_key_der, message, signature)


# =============================================================================
# RSA Public Key Construction
# =============================================================================

class RSAPublicKeyBridge:
    """
    RSA public key wrapper that provides a similar interface to cryptography.
    
    Can be constructed from modulus and exponent (for DG15 parsing) or from DER data.
    """
    
    def __init__(self, modulus: int, public_exponent: int):
        """
        Construct RSA public key from modulus and exponent.
        
        Args:
            modulus: RSA modulus (n)
            public_exponent: RSA public exponent (e)
        """
        from cryptography.hazmat.primitives.asymmetric import rsa
        self._modulus = modulus
        self._public_exponent = public_exponent
        self._key = rsa.RSAPublicNumbers(public_exponent, modulus).public_key()
    
    @classmethod
    def from_der(cls, der_data: bytes) -> "RSAPublicKeyBridge":
        """Load RSA public key from DER-encoded SPKI data."""
        from cryptography.hazmat.primitives.serialization import load_der_public_key
        from cryptography.hazmat.primitives.asymmetric import rsa
        key = load_der_public_key(der_data)
        if not isinstance(key, rsa.RSAPublicKey):
            raise ValueError("Not an RSA public key")
        numbers = key.public_numbers()
        return cls(numbers.n, numbers.e)
    
    @property
    def key_size(self) -> int:
        """Get key size in bits."""
        return self._key.key_size
    
    def public_bytes(self, encoding, key_format) -> bytes:
        """
        Serialize public key.
        
        Args:
            encoding: Encoding type (crypto_bridge.Encoding or cryptography.Encoding)
            key_format: Public key format (crypto_bridge.PublicFormat or cryptography.PublicFormat)
        """
        from cryptography.hazmat.primitives import serialization
        
        # Handle crypto_bridge Encoding (can be string 'DER'/'PEM' or enum)
        if isinstance(encoding, str):
            if encoding == 'DER':
                encoding = serialization.Encoding.DER
            else:
                encoding = serialization.Encoding.PEM
        elif hasattr(encoding, 'value'):
            if encoding.value == 'DER' or encoding.value == 1:
                encoding = serialization.Encoding.DER
            else:
                encoding = serialization.Encoding.PEM
        
        # Handle crypto_bridge PublicFormat (can be int or enum)
        if isinstance(key_format, int):
            if key_format == 1:
                key_format = serialization.PublicFormat.SubjectPublicKeyInfo
            else:
                key_format = serialization.PublicFormat.Raw
        elif hasattr(key_format, 'value'):
            if key_format.value == 'SubjectPublicKeyInfo' or key_format.value == 1:
                key_format = serialization.PublicFormat.SubjectPublicKeyInfo
            else:
                key_format = serialization.PublicFormat.Raw
        
        return self._key.public_bytes(encoding, key_format)
    
    def to_cryptography(self):
        """Return the underlying cryptography RSA public key."""
        return self._key
    
    def __repr__(self) -> str:
        return f"RSAPublicKeyBridge(key_size={self.key_size})"


class PublicFormat:
    """Public key format constants (compatible with cryptography.serialization.PublicFormat)."""
    SubjectPublicKeyInfo = 1
    Raw = 2


# =============================================================================
# Key Generation
# =============================================================================

def generate_random_bytes(length: int) -> bytes:
    """
    Generate cryptographically secure random bytes.
    
    Args:
        length: Number of bytes to generate
        
    Returns:
        Random bytes
    """
    return bytes(_generate_random_bytes(length))


def generate_key(key_type: str) -> dict:
    """
    Generate a cryptographic key of the specified type.
    
    Args:
        key_type: Key type ("ed25519", "x25519", "p256", "p384", "rsa2048", 
                  "rsa3072", "rsa4096", "aes128", "aes256", "hmac_sha256")
        
    Returns:
        Dict with "key_type" and key material (private_key, public_key, or key)
    """
    return _generate_key(key_type)


# =============================================================================
# JWK/JWS/JWE Operations
# =============================================================================

class Jwk:
    """
    JSON Web Key (JWK) wrapper.
    
    This class wraps the Rust JWK implementation to provide a Pythonic interface.
    
    Example:
        # Generate a key
        key = Jwk.generate("ed25519")
        
        # Sign data
        jws = jws_sign(b"hello", key, "EdDSA")
        
        # Verify
        payload = jws_verify(jws, key.to_public())
    """
    
    def __init__(self, inner=None):
        """Initialize with an inner Rust JWK object."""
        self._inner = inner
    
    @classmethod
    def generate(cls, key_type: str) -> "Jwk":
        """
        Generate a new JWK of the specified type.
        
        Args:
            key_type: "p256", "p384", "ed25519", "x25519", or "oct"
            
        Returns:
            Generated JWK
        """
        inner = _jwk_generate(key_type)
        return cls(inner)
    
    @classmethod
    def from_json(cls, json_str: str) -> "Jwk":
        """
        Parse a JWK from JSON.
        
        Args:
            json_str: JSON string representation of JWK
            
        Returns:
            Parsed JWK
        """
        inner = _Jwk.from_json(json_str)
        return cls(inner)
    
    def to_json(self) -> str:
        """
        Serialize this JWK to JSON.
        
        Returns:
            JSON string representation
        """
        return self._inner.to_json()
    
    def to_public(self) -> "Jwk":
        """
        Get the public key portion of this JWK.
        
        Returns:
            New JWK containing only the public key
        """
        return Jwk(self._inner.to_public())
    
    def thumbprint(self) -> str:
        """
        Compute the JWK thumbprint (RFC 7638).
        
        Returns:
            Base64url-encoded thumbprint
        """
        return self._inner.thumbprint()
    
    @property
    def kty(self) -> str:
        """Key type (e.g., "EC", "OKP", "oct")."""
        return self._inner.kty
    
    @property
    def kid(self) -> str | None:
        """Key ID."""
        return self._inner.kid
    
    @property
    def alg(self) -> str | None:
        """Algorithm hint."""
        return self._inner.alg
    
    @property
    def crv(self) -> str | None:
        """Curve name (for EC/OKP keys)."""
        return self._inner.crv
    
    def is_private(self) -> bool:
        """Check if this JWK contains private key material."""
        return self._inner.is_private()
    
    def is_symmetric(self) -> bool:
        """Check if this is a symmetric key (oct)."""
        return self._inner.is_symmetric()
    
    def __repr__(self) -> str:
        return f"Jwk(kty='{self.kty}', crv={self.crv!r}, kid={self.kid!r})"


def jwk_generate(key_type: str) -> Jwk:
    """
    Generate a new JWK of the specified type.
    
    Args:
        key_type: "p256", "p384", "ed25519", "x25519", or "oct"
        
    Returns:
        Generated JWK
    """
    return Jwk.generate(key_type)


def jws_sign(payload: bytes, key: Jwk, algorithm: str) -> str:
    """
    Create a JWS (JSON Web Signature).
    
    Args:
        payload: Data to sign
        key: JWK with private key
        algorithm: Signing algorithm (ES256, ES384, EdDSA, HS256, etc.)
        
    Returns:
        JWS compact serialization string
    """
    return _jws_sign(payload, key._inner, algorithm)


def jws_verify(jws: str, key: Jwk) -> bytes:
    """
    Verify a JWS and return the payload.
    
    Args:
        jws: JWS compact serialization string
        key: JWK with public key (or symmetric key)
        
    Returns:
        Verified payload bytes
        
    Raises:
        VerificationError: If signature verification fails
    """
    return bytes(_jws_verify(jws, key._inner))


def jwe_encrypt(plaintext: bytes, recipient_key: Jwk, encryption: str = "A256GCM") -> str:
    """
    Create a JWE (JSON Web Encryption).
    
    Args:
        plaintext: Data to encrypt
        recipient_key: JWK with recipient's public key
        encryption: Content encryption algorithm (A128GCM or A256GCM)
        
    Returns:
        JWE compact serialization string
    """
    return _jwe_encrypt(plaintext, recipient_key._inner, encryption)


def jwe_decrypt(jwe: str, key: Jwk) -> bytes:
    """
    Decrypt a JWE.
    
    Args:
        jwe: JWE compact serialization string
        key: JWK with private key
        
    Returns:
        Decrypted plaintext
        
    Raises:
        DecryptionError: If decryption fails
    """
    return bytes(_jwe_decrypt(jwe, key._inner))


def open_badge_ob2_issue(request_json: str) -> str:
    """
    Issue an Open Badges v2 assertion (optionally signed).

    Args:
        request_json: JSON payload with assertion + signing options

    Returns:
        JSON result with issued credential
    """
    return _open_badge_ob2_issue(request_json)


def open_badge_ob2_verify(request_json: str) -> str:
    """
    Verify an Open Badges v2 assertion.

    Args:
        request_json: JSON payload with assertion + document_store

    Returns:
        JSON verification result
    """
    return _open_badge_ob2_verify(request_json)


def open_badge_ob3_issue(request_json: str) -> str:
    """
    Issue an Open Badges v3 credential (Data Integrity proof).

    Args:
        request_json: JSON payload with credential + signing options

    Returns:
        JSON result with issued credential
    """
    return _open_badge_ob3_issue(request_json)


def open_badge_ob3_verify(request_json: str) -> str:
    """
    Verify an Open Badges v3 credential (Data Integrity proof).

    Args:
        request_json: JSON payload with credential + document_store

    Returns:
        JSON verification result
    """
    return _open_badge_ob3_verify(request_json)


# =============================================================================
# DTC (Digital Travel Credential) Operations
# =============================================================================

def dtc_create(request_json: str) -> str:
    """
    Normalize a DTC payload (JSON in/out).

    Args:
        request_json: JSON payload describing the DTC record

    Returns:
        JSON string of the normalized DTC record
    """
    return _dtc_create(request_json)


def dtc_sign(request_json: str) -> str:
    """
    Sign a DTC payload (JSON in/out).

    Args:
        request_json: JSON payload with DTC record + signing_key_pem

    Returns:
        JSON string of the signed DTC record
    """
    return _dtc_sign(request_json)


def dtc_verify(request_json: str) -> str:
    """
    Verify a DTC payload (JSON in/out).

    Args:
        request_json: JSON payload with DTC record + signer_public_key_pem

    Returns:
        JSON string of the verification result
    """
    return _dtc_verify(request_json)


# =============================================================================
# Certificate Operations
# =============================================================================

def _load_certificate_pem_to_der(pem_data: str) -> bytes:
    """
    Load a certificate from PEM format and return DER bytes.
    
    Args:
        pem_data: PEM-encoded certificate string
        
    Returns:
        DER-encoded certificate bytes
    """
    return bytes(_load_certificate_pem(pem_data))


def _load_certificate_der_validate(der_data: bytes) -> bytes:
    """
    Validate and load a certificate from DER format.
    
    Args:
        der_data: DER-encoded certificate bytes
        
    Returns:
        DER-encoded certificate bytes (validated)
    """
    return bytes(_load_certificate_der(der_data))


def get_certificate_info(der_data: bytes) -> dict:
    """
    Get information from a DER-encoded certificate.
    
    Args:
        der_data: DER-encoded certificate bytes
        
    Returns:
        Dictionary with certificate info (subject, issuer, serial_number, 
        not_before, not_after, is_ca, key_usage, subject_alt_names, fingerprint_sha256)
    """
    return _get_certificate_info(der_data)


def certificate_pem_to_der(pem_data: str) -> bytes:
    """
    Convert certificate from PEM to DER format.
    
    Args:
        pem_data: PEM-encoded certificate string
        
    Returns:
        DER-encoded certificate bytes
    """
    return bytes(_certificate_pem_to_der(pem_data))


def certificate_der_to_pem(der_data: bytes) -> str:
    """
    Convert certificate from DER to PEM format.
    
    Args:
        der_data: DER-encoded certificate bytes
        
    Returns:
        PEM-encoded certificate string
    """
    return _certificate_der_to_pem(der_data)


def get_certificate_public_key(der_data: bytes) -> bytes:
    """
    Extract public key from certificate in SPKI DER format.
    
    Args:
        der_data: DER-encoded certificate bytes
        
    Returns:
        SPKI DER-encoded public key bytes
    """
    return bytes(_get_certificate_public_key(der_data))


def is_certificate_expired(der_data: bytes) -> bool:
    """
    Check if a certificate is expired.
    
    Args:
        der_data: DER-encoded certificate bytes
        
    Returns:
        True if expired, False otherwise
    """
    return _is_certificate_expired(der_data)


def is_certificate_not_yet_valid(der_data: bytes) -> bool:
    """
    Check if a certificate is not yet valid.
    
    Args:
        der_data: DER-encoded certificate bytes
        
    Returns:
        True if not yet valid, False otherwise
    """
    return _is_certificate_not_yet_valid(der_data)


def verify_certificate_signature(cert_der: bytes, issuer_der: bytes) -> bool:
    """
    Verify that a certificate was signed by another certificate.
    
    Args:
        cert_der: DER-encoded certificate to verify
        issuer_der: DER-encoded issuer certificate
        
    Returns:
        True if signature is valid, False otherwise
    """
    return _verify_certificate_signature(cert_der, issuer_der)


# =============================================================================
# Key Serialization Operations
# =============================================================================

def load_private_key_pem(pem_data: str) -> bytes:
    """
    Load a private key from PEM format.
    
    Supports PKCS#8, SEC1 (EC), and PKCS#1 (RSA) formats.
    
    Args:
        pem_data: PEM-encoded private key string
        
    Returns:
        PKCS#8 DER-encoded private key bytes
    """
    return bytes(_load_private_key_pem(pem_data))


def load_private_key_der(der_data: bytes) -> bytes:
    """
    Validate and load a private key from DER format.
    
    Args:
        der_data: PKCS#8 DER-encoded private key bytes
        
    Returns:
        PKCS#8 DER-encoded private key bytes (validated)
    """
    return bytes(_load_private_key_der(der_data))


def save_private_key_pem(private_key_der: bytes) -> str:
    """
    Save a private key to PEM format (PKCS#8).
    
    Args:
        private_key_der: PKCS#8 DER-encoded private key bytes
        
    Returns:
        PEM-encoded private key string
    """
    return _save_private_key_pem(private_key_der)


def load_public_key_pem(pem_data: str) -> bytes:
    """
    Load a public key from PEM format (SPKI).
    
    Args:
        pem_data: PEM-encoded public key string
        
    Returns:
        SPKI DER-encoded public key bytes
    """
    return bytes(_load_public_key_pem(pem_data))


def load_public_key_der(der_data: bytes) -> bytes:
    """
    Validate and load a public key from DER format.
    
    Args:
        der_data: SPKI DER-encoded public key bytes
        
    Returns:
        SPKI DER-encoded public key bytes (validated)
    """
    return bytes(_load_public_key_der(der_data))


def save_public_key_pem(public_key_der: bytes) -> str:
    """
    Save a public key to PEM format (SPKI).
    
    Args:
        public_key_der: SPKI DER-encoded public key bytes
        
    Returns:
        PEM-encoded public key string
    """
    return _save_public_key_pem(public_key_der)


def extract_public_key(private_key_der: bytes) -> bytes:
    """
    Extract public key from private key.
    
    Args:
        private_key_der: PKCS#8 DER-encoded private key bytes
        
    Returns:
        SPKI DER-encoded public key bytes
    """
    return bytes(_extract_public_key(private_key_der))


def detect_private_key_type(der_data: bytes) -> str:
    """
    Detect the type of a private key.
    
    Args:
        der_data: PKCS#8 DER-encoded private key bytes
        
    Returns:
        Key type string (e.g., "EC_P256", "EC_P384", "RSA", "Ed25519")
    """
    return _detect_private_key_type(der_data)


def detect_public_key_type(der_data: bytes) -> str:
    """
    Detect the type of a public key.
    
    Args:
        der_data: SPKI DER-encoded public key bytes
        
    Returns:
        Key type string (e.g., "EC_P256", "EC_P384", "RSA", "Ed25519")
    """
    return _detect_public_key_type(der_data)


def get_key_size(public_key_der: bytes) -> int:
    """
    Get the key size in bits.
    
    Args:
        public_key_der: SPKI DER-encoded public key bytes
        
    Returns:
        Key size in bits
    """
    return _get_key_size(public_key_der)


def raw_private_key_to_pkcs8(raw_key: bytes, key_type: str) -> bytes:
    """
    Convert raw EC private key bytes to PKCS#8 DER format.
    
    Args:
        raw_key: Raw private key bytes (32 bytes for P-256, 48 for P-384, 32 for Ed25519)
        key_type: One of "EC_P256", "EC_P384", "Ed25519", "P256", "P384", "secp256r1", "secp384r1"
        
    Returns:
        PKCS#8 DER-encoded private key bytes
    """
    return _raw_private_key_to_pkcs8(raw_key, key_type)


def raw_public_key_to_spki(raw_key: bytes, key_type: str) -> bytes:
    """
    Convert raw public key bytes to SPKI DER format.
    
    Args:
        raw_key: Raw public key bytes (65 bytes for P-256/P-384 uncompressed, 32 for Ed25519)
        key_type: One of "EC_P256", "EC_P384", "Ed25519", "P256", "P384", "secp256r1", "secp384r1"
        
    Returns:
        SPKI DER-encoded public key bytes
    """
    return _raw_public_key_to_spki(raw_key, key_type)


def pkcs8_to_raw_private_key(pkcs8_der: bytes) -> tuple[bytes, str]:
    """
    Extract raw private key bytes from PKCS#8 DER format.
    
    Args:
        pkcs8_der: PKCS#8 DER-encoded private key bytes
        
    Returns:
        Tuple of (raw_key_bytes, key_type)
    """
    return _pkcs8_to_raw_private_key(pkcs8_der)


def spki_to_raw_public_key(spki_der: bytes) -> tuple[bytes, str]:
    """
    Extract raw public key bytes from SPKI DER format.
    
    Args:
        spki_der: SPKI DER-encoded public key bytes
        
    Returns:
        Tuple of (raw_key_bytes, key_type)
    """
    return _spki_to_raw_public_key(spki_der)


# =============================================================================
# Ed448 Operations
# =============================================================================

def ed448_generate() -> tuple[bytes, bytes]:
    """
    Generate a new Ed448 key pair.
    
    Returns:
        Tuple of (private_key_bytes, public_key_bytes)
        Private key is 57 bytes, public key is 57 bytes
    """
    return _ed448_generate()


def ed448_sign(private_key: bytes, message: bytes, context: bytes | None = None) -> bytes:
    """
    Sign a message using Ed448.
    
    Args:
        private_key: 57-byte Ed448 private key
        message: Message bytes to sign
        context: Optional context string (max 255 bytes) per RFC 8032
                 Note: Context is currently not supported by the Rust implementation
        
    Returns:
        114-byte signature
    """
    # Note: context is currently not passed to Rust (not yet implemented in binding)
    return bytes(_ed448_sign(private_key, message))


def ed448_verify(public_key: bytes, message: bytes, signature: bytes, context: bytes | None = None) -> bool:
    """
    Verify an Ed448 signature.
    
    Args:
        public_key: 57-byte Ed448 public key
        message: Message bytes that were signed
        signature: 114-byte signature
        context: Optional context string (max 255 bytes) per RFC 8032
                 Note: Context is currently not supported by the Rust implementation
        
    Returns:
        True if signature is valid, False otherwise
    """
    # Note: context is currently not passed to Rust (not yet implemented in binding)
    return _ed448_verify(public_key, message, signature)


# =============================================================================
# PKCS#12 Operations
# =============================================================================

class Pkcs12Data:
    """Container for parsed PKCS#12 data."""
    
    def __init__(self, rust_data):
        """Initialize from Rust Pkcs12Data object."""
        self._inner = rust_data
    
    @property
    def private_key_der(self) -> bytes | None:
        """Get the private key as DER bytes (PKCS#8 format)."""
        return self._inner.private_key_der
    
    @property
    def certificate_der(self) -> bytes | None:
        """Get the end-entity certificate as DER bytes."""
        return self._inner.certificate_der
    
    @property
    def certificate_chain(self) -> list[bytes]:
        """Get the certificate chain as list of DER bytes."""
        return self._inner.certificate_chain
    
    @property
    def private_key_pem(self) -> str | None:
        """Get the private key as PEM string."""
        return self._inner.private_key_pem()
    
    @property
    def certificate_pem(self) -> str | None:
        """Get the end-entity certificate as PEM string."""
        return self._inner.certificate_pem()
    
    @property
    def chain_pem(self) -> list[str]:
        """Get the certificate chain as list of PEM strings."""
        return self._inner.chain_pem()
    
    @property
    def key_algorithm(self) -> str | None:
        """Get the private key algorithm (RSA, EC_P256, EC_P384, Ed25519, etc.)."""
        return self._inner.key_algorithm()


def pkcs12_parse(data: bytes, password: str = "") -> Pkcs12Data:
    """
    Parse a PKCS#12 (PFX) file.
    
    Args:
        data: PKCS#12 file contents as bytes
        password: Password for decryption (empty string for no password)
        
    Returns:
        Pkcs12Data object containing the parsed key and certificates
        
    Raises:
        ValueError: If the PKCS#12 data is invalid or password is incorrect
    """
    rust_data = _pkcs12_parse(data, password)
    return Pkcs12Data(rust_data)


# =============================================================================
# ISO 9796-2 Operations (Active Authentication)
# =============================================================================

def iso9796_verify(
    public_key_der: bytes,
    signature: bytes,
    message: bytes | None = None,
    scheme: str | int = "scheme2",
    hash_algorithm: str = "sha256",
) -> bool:
    """
    Verify an ISO 9796-2 signature.
    
    This signature scheme is used in eMRTD Active Authentication.
    
    Args:
        public_key_der: RSA public key in DER (SPKI) format
        signature: The signature bytes
        message: Original message (optional for schemes with full recovery)
        scheme: 1, 2, 3 or "scheme1", "scheme2", "scheme3"
        hash_algorithm: "sha1", "sha224", "sha256", "sha384", or "sha512"
        
    Returns:
        True if signature is valid
    """
    
    # Convert scheme string to int if needed
    if isinstance(scheme, str):
        scheme_map = {"scheme1": 1, "scheme2": 2, "scheme3": 3}
        scheme = scheme_map.get(scheme.lower(), 2)
    
    return _iso9796_verify(public_key_der, message or b"", signature, scheme, hash_algorithm)


def iso9796_recover(
    public_key_der: bytes,
    signature: bytes,
    scheme: str | int = "scheme2",
    hash_algorithm: str | None = "sha256",
) -> bytes:
    """
    Recover the message from an ISO 9796-2 signature.
    
    This is used in eMRTD Active Authentication to verify the challenge response.
    
    Args:
        public_key_der: RSA public key in DER (SPKI) format
        signature: The signature bytes
        scheme: 1, 2, 3 or "scheme1", "scheme2", "scheme3"
        hash_algorithm: "sha1", "sha224", "sha256", "sha384", or "sha512" (optional for scheme 1)
        
    Returns:
        Recovered message bytes
        
    Raises:
        ValueError: If message recovery fails
    """
    
    # Convert scheme string to int if needed
    if isinstance(scheme, str):
        scheme_map = {"scheme1": 1, "scheme2": 2, "scheme3": 3}
        scheme = scheme_map.get(scheme.lower(), 2)
    
    return bytes(_iso9796_recover(public_key_der, signature, scheme, hash_algorithm))


# =============================================================================
# OCSP Operations
# =============================================================================

def build_ocsp_request(cert_der: bytes, issuer_der: bytes) -> bytes:
    """
    Build an OCSP request for a certificate.
    
    Args:
        cert_der: DER-encoded certificate to check
        issuer_der: DER-encoded issuer certificate
        
    Returns:
        DER-encoded OCSP request bytes
    """
    return bytes(_build_ocsp_request(cert_der, issuer_der))


def get_ocsp_responder_url(cert_der: bytes) -> str | None:
    """
    Extract the OCSP responder URL from a certificate's AIA extension.
    
    Args:
        cert_der: DER-encoded certificate
        
    Returns:
        OCSP responder URL or None if not present
    """
    return _get_ocsp_responder_url(cert_der)


def parse_ocsp_response(response_der: bytes) -> dict:
    """
    Parse an OCSP response.
    
    Args:
        response_der: DER-encoded OCSP response bytes
        
    Returns:
        Dictionary with parsed response:
        - status: "good", "revoked", or "unknown"
        - produced_at: ISO timestamp when response was produced
        - this_update: ISO timestamp for this update
        - next_update: Optional ISO timestamp for next update
        - revocation_time: Optional ISO timestamp if revoked
        - revocation_reason: Optional reason string if revoked
    """
    return _parse_ocsp_response(response_der)


# =============================================================================
# Utility Functions
# =============================================================================

def is_rust_available() -> bool:
    """Check if Rust bindings are available.
    
    This function always returns True as Rust bindings are now required.
    Kept for backwards compatibility.
    """
    return True


def get_backend_name() -> str:
    """Get the name of the active crypto backend."""
    return "rust"


# =============================================================================
# Certificate Wrapper (x509.Certificate replacement)
# =============================================================================

class Certificate:
    """
    Certificate wrapper that provides a similar interface to cryptography.x509.Certificate
    but uses Rust for parsing and operations.
    
    This allows progressive migration from Python cryptography to Rust.
    """
    
    def __init__(self, der_data: bytes):
        """
        Initialize a Certificate from DER data.
        
        Args:
            der_data: DER-encoded certificate bytes
        """
        
        self._der_data = der_data
        self._info: dict | None = None
    
    @classmethod
    def from_pem(cls, pem_data: bytes | str) -> "Certificate":
        """
        Load a certificate from PEM data.
        
        Args:
            pem_data: PEM-encoded certificate string or bytes
        """
        if isinstance(pem_data, bytes):
            pem_data = pem_data.decode('utf-8')
        der_data = _certificate_pem_to_der(pem_data)
        return cls(der_data)
    
    @classmethod
    def from_der(cls, der_data: bytes) -> "Certificate":
        """
        Load a certificate from DER data.
        
        Args:
            der_data: DER-encoded certificate bytes
        """
        return cls(der_data)
    
    @property
    def _certificate_info(self) -> dict:
        """Get cached certificate info."""
        if self._info is None:
            self._info = _get_certificate_info(self._der_data)
        return self._info
    
    @property
    def subject(self) -> str:
        """Get certificate subject as string."""
        return self._certificate_info.get("subject", "")
    
    @property
    def issuer(self) -> str:
        """Get certificate issuer as string."""
        return self._certificate_info.get("issuer", "")
    
    @property
    def serial_number(self) -> int:
        """Get certificate serial number."""
        serial_str = self._certificate_info.get("serial_number", "0")
        # Handle hex format if needed
        if isinstance(serial_str, str) and serial_str.startswith("0x"):
            return int(serial_str, 16)
        return int(serial_str)
    
    @property
    def serial_number_hex(self) -> str:
        """Get certificate serial number as hex string."""
        return self._certificate_info.get("serial_number_hex", "")
    
    @property
    def not_valid_before(self) -> str:
        """Get certificate not-valid-before timestamp (ISO format)."""
        return self._certificate_info.get("not_before", "")
    
    @property
    def not_valid_after(self) -> str:
        """Get certificate not-valid-after timestamp (ISO format)."""
        return self._certificate_info.get("not_after", "")
    
    @property
    def signature_algorithm(self) -> str:
        """Get signature algorithm OID."""
        return self._certificate_info.get("signature_algorithm", "")
    
    @property
    def public_key_algorithm(self) -> str:
        """Get public key algorithm type."""
        return self._certificate_info.get("public_key_algorithm", "")
    
    @property
    def key_size(self) -> int | None:
        """Get public key size in bits."""
        return self._certificate_info.get("key_size")
    
    @property
    def is_ca(self) -> bool:
        """Check if certificate is a CA certificate."""
        return self._certificate_info.get("is_ca", False)
    
    @property
    def key_usage(self) -> list[str]:
        """Get key usage extensions."""
        return self._certificate_info.get("key_usage", [])
    
    @property
    def extended_key_usage(self) -> list[str]:
        """Get extended key usage OIDs."""
        return self._certificate_info.get("extended_key_usage", [])
    
    @property
    def subject_alt_names(self) -> list[str]:
        """Get subject alternative names."""
        return self._certificate_info.get("subject_alt_names", [])
    
    def is_expired(self) -> bool:
        """Check if certificate is expired."""
        return _is_certificate_expired(self._der_data)
    
    def is_not_yet_valid(self) -> bool:
        """Check if certificate is not yet valid."""
        return _is_certificate_not_yet_valid(self._der_data)
    
    def get_public_key_der(self) -> bytes:
        """Get the public key as DER-encoded SPKI."""
        return bytes(_get_certificate_public_key(self._der_data))
    
    def verify_signature(self, issuer_cert: "Certificate") -> bool:
        """
        Verify this certificate was signed by the issuer.
        
        Args:
            issuer_cert: The issuer's certificate
            
        Returns:
            True if signature is valid
        """
        return _verify_certificate_signature(self._der_data, issuer_cert._der_data)
    
    def to_der(self) -> bytes:
        """Get certificate as DER bytes."""
        return self._der_data
    
    def to_pem(self) -> bytes:
        """Get certificate as PEM bytes."""
        return _certificate_der_to_pem(self._der_data)
    
    def public_key(self):
        """
        Get the public key as a cryptography-compatible object.
        
        This provides interoperability with libraries like PyJWT that expect
        cryptography key objects for signature verification.
        
        Returns:
            A cryptography public key object (RSAPublicKey, EllipticCurvePublicKey, etc.)
        """
        from cryptography.hazmat.primitives.serialization import load_der_public_key
        pub_key_der = self.get_public_key_der()
        return load_der_public_key(pub_key_der)
    
    def public_bytes(self, encoding) -> bytes:
        """
        Get certificate bytes in specified encoding.
        
        Args:
            encoding: Encoding type (use crypto_bridge.Encoding.DER or .PEM)
            
        Returns:
            Certificate bytes in requested encoding
        """
        if hasattr(encoding, 'value'):
            encoding = encoding.value
        if encoding == 'DER' or encoding == 1:
            return self._der_data
        elif encoding == 'PEM' or encoding == 2:
            return self.to_pem().encode() if isinstance(self.to_pem(), str) else self.to_pem()
        else:
            return self._der_data
    
    @property
    def extensions(self) -> "CertificateExtensions":
        """Get certificate extensions accessor."""
        return CertificateExtensions(self._certificate_info)
    
    def to_cryptography(self):
        """
        Convert to a cryptography.x509.Certificate object.
        
        This provides interoperability with libraries that require cryptography
        Certificate objects (like certvalidator).
        
        Returns:
            A cryptography.x509.Certificate object
        """
        from cryptography import x509
        from cryptography.hazmat.backends import default_backend
        return x509.load_der_x509_certificate(self._der_data, default_backend())
    
    def __repr__(self) -> str:
        return f"Certificate(subject='{self.subject}', issuer='{self.issuer}')"


class CertificateExtensions:
    """
    Accessor for certificate extensions, providing an x509-like interface.
    """
    
    def __init__(self, cert_info: dict):
        self._info = cert_info
    
    def get_extension_for_class(self, extension_class):
        """
        Get extension by class type.
        
        Supports SubjectAlternativeName and BasicConstraints.
        """
        class_name = extension_class.__name__ if hasattr(extension_class, '__name__') else str(extension_class)
        
        if 'SubjectAlternativeName' in class_name:
            sans = self._info.get('subject_alt_names', [])
            if not sans:
                raise ExtensionNotFound(f"Extension {class_name} not found")
            return SubjectAlternativeNameExtension(sans)
        elif 'BasicConstraints' in class_name:
            is_ca = self._info.get('is_ca', False)
            return BasicConstraintsExtension(is_ca)
        else:
            raise ExtensionNotFound(f"Extension {class_name} not found")


class ExtensionNotFound(Exception):
    """Raised when a certificate extension is not found."""
    pass


class SubjectAlternativeNameExtension:
    """Subject Alternative Name extension wrapper."""
    
    def __init__(self, names: list[str]):
        self._names = names
    
    @property
    def value(self) -> "SubjectAlternativeNameValue":
        return SubjectAlternativeNameValue(self._names)


class SubjectAlternativeNameValue:
    """Value accessor for SAN extension."""
    
    def __init__(self, names: list[str]):
        self._names = names
    
    def get_values_for_type(self, name_type) -> list[str]:
        """
        Get SAN values for a specific type.
        
        Args:
            name_type: DNSName, UniformResourceIdentifier, etc.
        """
        type_name = name_type.__name__ if hasattr(name_type, '__name__') else str(name_type)
        
        # Filter based on type - SANs from Rust are prefixed with type
        result = []
        for name in self._names:
            if 'DNS' in type_name and (name.startswith('DNS:') or not ':' in name):
                result.append(name.replace('DNS:', ''))
            elif 'URI' in type_name and name.startswith('URI:'):
                result.append(name.replace('URI:', ''))
            elif 'email' in type_name.lower() and name.startswith('email:'):
                result.append(name.replace('email:', ''))
        return result if result else self._names  # Return all if no match


class BasicConstraintsExtension:
    """Basic Constraints extension wrapper."""
    
    def __init__(self, is_ca: bool):
        self._is_ca = is_ca
    
    @property
    def value(self) -> "BasicConstraintsValue":
        return BasicConstraintsValue(self._is_ca)


class BasicConstraintsValue:
    """Value accessor for BasicConstraints extension."""
    
    def __init__(self, is_ca: bool):
        self.ca = is_ca
        self.path_length = None


class Encoding:
    """Certificate encoding types."""
    DER = 'DER'
    PEM = 'PEM'


def load_pem_x509_certificate(pem_data: bytes | str) -> Certificate:
    """
    Load a certificate from PEM data.
    
    Drop-in replacement for cryptography.x509.load_pem_x509_certificate.
    
    Args:
        pem_data: PEM-encoded certificate
        
    Returns:
        Certificate object
    """
    return Certificate.from_pem(pem_data)


def load_der_x509_certificate(der_data: bytes) -> Certificate:
    """
    Load a certificate from DER data.
    
    Drop-in replacement for cryptography.x509.load_der_x509_certificate.
    
    Args:
        der_data: DER-encoded certificate
        
    Returns:
        Certificate object
    """
    return Certificate.from_der(der_data)


def load_certificate_pem(pem_data: bytes | str) -> Certificate:
    """
    Load a certificate from PEM data.
    
    Args:
        pem_data: PEM-encoded certificate
        
    Returns:
        Certificate object
    """
    return Certificate.from_pem(pem_data)


def load_certificate_der(der_data: bytes) -> Certificate:
    """
    Load a certificate from DER data.
    
    Args:
        der_data: DER-encoded certificate
        
    Returns:
        Certificate object
    """
    return Certificate.from_der(der_data)


# Compatibility aliases for drop-in x509 replacement
DNSName = type('DNSName', (), {})
UniformResourceIdentifier = type('UniformResourceIdentifier', (), {})
SubjectAlternativeName = type('SubjectAlternativeName', (), {})
BasicConstraints = type('BasicConstraints', (), {})


# =============================================================================
# Certificate Builder (Rust-based certificate generation)
# =============================================================================

# Try to import cert_builder bindings (feature-gated)
CERT_BUILDER_AVAILABLE = False
try:
    try:
        from marty_plugin._marty_rs import (
            CertProfile as _CertProfile,
            CertificateBuilderConfig as _CertificateBuilderConfig,
            build_self_signed_certificate as _build_self_signed_certificate,
            build_self_signed_certificate_with_key as _build_self_signed_certificate_with_key,
        )
        CERT_BUILDER_AVAILABLE = True
    except ImportError:
        from _marty_rs import (
            CertProfile as _CertProfile,
            CertificateBuilderConfig as _CertificateBuilderConfig,
            build_self_signed_certificate as _build_self_signed_certificate,
            build_self_signed_certificate_with_key as _build_self_signed_certificate_with_key,
        )
        CERT_BUILDER_AVAILABLE = True
except ImportError:
    _CertProfile = None
    _CertificateBuilderConfig = None
    _build_self_signed_certificate = None
    _build_self_signed_certificate_with_key = None


class CertProfile:
    """
    Certificate profile for certificate generation.
    
    Defines the purpose and extensions for the generated certificate.
    
    Example:
        # Create a CA profile
        profile = CertProfile.ca(path_length=1)
        
        # Create an end-entity profile
        profile = CertProfile.end_entity()
        
        # Create a DSC profile for eMRTD
        profile = CertProfile.dsc(country_code="US")
    """
    
    def __init__(self, inner=None):
        """Initialize with internal profile object."""
        if not CERT_BUILDER_AVAILABLE:
            raise NotImplementedError("Rust cert-builder feature required for CertProfile")
        self._inner = inner
    
    @classmethod
    def ca(cls, path_length: int | None = None) -> "CertProfile":
        """Create a CA profile with optional path length constraint."""
        if not CERT_BUILDER_AVAILABLE:
            raise NotImplementedError("Rust cert-builder feature required for CertProfile")
        instance = cls.__new__(cls)
        instance._inner = _CertProfile.ca(path_length)
        return instance
    
    @classmethod
    def sub_ca(cls, path_length: int = 0) -> "CertProfile":
        """Create a SubCA profile with path length constraint."""
        if not CERT_BUILDER_AVAILABLE:
            raise NotImplementedError("Rust cert-builder feature required for CertProfile")
        instance = cls.__new__(cls)
        instance._inner = _CertProfile.sub_ca(path_length)
        return instance
    
    @classmethod
    def end_entity(cls) -> "CertProfile":
        """Create an EndEntity (leaf) profile."""
        if not CERT_BUILDER_AVAILABLE:
            raise NotImplementedError("Rust cert-builder feature required for CertProfile")
        instance = cls.__new__(cls)
        instance._inner = _CertProfile.end_entity()
        return instance
    
    @classmethod
    def csca(cls, country_code: str) -> "CertProfile":
        """Create a CSCA profile for eMRTD."""
        if not CERT_BUILDER_AVAILABLE:
            raise NotImplementedError("Rust cert-builder feature required for CertProfile")
        instance = cls.__new__(cls)
        instance._inner = _CertProfile.csca(country_code)
        return instance
    
    @classmethod
    def iaca(cls, jurisdiction: str) -> "CertProfile":
        """Create an IACA profile for mDL."""
        if not CERT_BUILDER_AVAILABLE:
            raise NotImplementedError("Rust cert-builder feature required for CertProfile")
        instance = cls.__new__(cls)
        instance._inner = _CertProfile.iaca(jurisdiction)
        return instance
    
    @classmethod
    def dsc(cls, country_code: str) -> "CertProfile":
        """Create a DSC profile for eMRTD document signer."""
        if not CERT_BUILDER_AVAILABLE:
            raise NotImplementedError("Rust cert-builder feature required for CertProfile")
        instance = cls.__new__(cls)
        instance._inner = _CertProfile.dsc(country_code)
        return instance


class CertificateBuilder:
    """
    Certificate builder for generating X.509 certificates.
    
    Uses Rust implementation for certificate generation.
    
    Example:
        # Generate a self-signed CA certificate
        builder = CertificateBuilder()
        builder.subject_cn("My CA")
        builder.validity_days(3650)
        builder.profile(CertProfile.ca())
        builder.key_type("ecdsa-p256")
        cert_der, key_pem = builder.build_self_signed()
        
        # Generate a certificate using an existing key
        builder = CertificateBuilder()
        builder.subject_cn("Document Signer")
        builder.profile(CertProfile.end_entity())
        builder.key_type("rsa2048")
        cert_der = builder.build_self_signed_with_key(private_key_pem)
    """
    
    def __init__(self):
        """Initialize a new certificate builder."""
        if not CERT_BUILDER_AVAILABLE:
            raise NotImplementedError("Rust cert-builder feature required for CertificateBuilder")
        self._inner = _CertificateBuilderConfig()
    
    def subject_cn(self, cn: str) -> "CertificateBuilder":
        """Set the subject Common Name."""
        self._inner = self._inner.subject_cn(cn)
        return self
    
    def subject_country(self, country: str) -> "CertificateBuilder":
        """Set the subject Country."""
        self._inner = self._inner.subject_country(country)
        return self
    
    def subject_org(self, org: str) -> "CertificateBuilder":
        """Set the subject Organization."""
        self._inner = self._inner.subject_org(org)
        return self
    
    def subject_ou(self, ou: str) -> "CertificateBuilder":
        """Set the subject Organizational Unit."""
        self._inner = self._inner.subject_ou(ou)
        return self
    
    def issuer_cn(self, cn: str) -> "CertificateBuilder":
        """Set the issuer Common Name (for self-signed, optional)."""
        self._inner = self._inner.issuer_cn(cn)
        return self
    
    def validity_days(self, days: int) -> "CertificateBuilder":
        """Set the validity period in days from now."""
        self._inner = self._inner.validity_days(days)
        return self
    
    def profile(self, profile: CertProfile) -> "CertificateBuilder":
        """Set the certificate profile."""
        self._inner = self._inner.profile(profile._inner)
        return self
    
    def key_type(self, key_type: str) -> "CertificateBuilder":
        """
        Set the key type for the generated keypair.
        
        Supported types: "ecdsa-p256", "ecdsa-p384", "rsa2048", "rsa3072", 
        "rsa4096", "ed25519"
        """
        self._inner = self._inner.key_type(key_type)
        return self
    
    def build_self_signed(self) -> tuple[bytes, str]:
        """
        Build a self-signed certificate with a new keypair.
        
        Returns:
            Tuple of (certificate_der_bytes, private_key_pem_str)
        """
        return self._inner.build_self_signed()
    
    def build_self_signed_with_key(self, private_key_pem: str) -> bytes:
        """
        Build a self-signed certificate using an existing private key.
        
        Args:
            private_key_pem: PEM-encoded private key
            
        Returns:
            DER-encoded certificate bytes
        """
        return self._inner.build_self_signed_with_key(private_key_pem)
    
    def build_signed_by(self, issuer_cert_der: bytes, issuer_key_pem: str) -> tuple[bytes, str]:
        """
        Build a certificate signed by an issuer CA.
        
        Args:
            issuer_cert_der: DER-encoded issuer certificate
            issuer_key_pem: PEM-encoded issuer private key
            
        Returns:
            Tuple of (certificate_der_bytes, private_key_pem_str)
        """
        return self._inner.build_signed_by(issuer_cert_der, issuer_key_pem)


def build_self_signed_certificate(
    common_name: str,
    validity_days: int = 365,
    key_type: str = "ecdsa-p256",
    is_ca: bool = False,
    country: str | None = None,
    organization: str | None = None,
) -> tuple[bytes, str]:
    """
    Create a self-signed certificate with a new keypair.
    
    This is a convenience function for simple certificate generation.
    
    Args:
        common_name: Subject Common Name
        validity_days: Certificate validity in days (default: 365)
        key_type: Key type (default: "ecdsa-p256")
        is_ca: Whether this is a CA certificate (default: False)
        country: Subject country code (optional)
        organization: Subject organization (optional)
        
    Returns:
        Tuple of (certificate_der_bytes, private_key_pem_str)
    """
    if not CERT_BUILDER_AVAILABLE:
        raise NotImplementedError("Rust cert-builder feature required")
    return _build_self_signed_certificate(
        common_name=common_name,
        validity_days=validity_days,
        key_type=key_type,
        is_ca=is_ca,
        country=country,
        organization=organization,
    )


def build_self_signed_certificate_with_key(
    private_key_pem: str,
    common_name: str,
    validity_days: int = 365,
    key_type: str | None = None,
    is_ca: bool = False,
    country: str | None = None,
    organization: str | None = None,
) -> bytes:
    """
    Create a self-signed certificate using an existing private key.
    
    Args:
        private_key_pem: PEM-encoded private key
        common_name: Subject Common Name
        validity_days: Certificate validity in days (default: 365)
        key_type: Key type hint (auto-detected if not provided)
        is_ca: Whether this is a CA certificate (default: False)
        country: Subject country code (optional)
        organization: Subject organization (optional)
        
    Returns:
        DER-encoded certificate bytes
    """
    if not CERT_BUILDER_AVAILABLE:
        raise NotImplementedError("Rust cert-builder feature required")
    return _build_self_signed_certificate_with_key(
        private_key_pem=private_key_pem,
        common_name=common_name,
        validity_days=validity_days,
        key_type=key_type,
        is_ca=is_ca,
        country=country,
        organization=organization,
    )
