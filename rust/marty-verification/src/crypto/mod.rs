//! Unified cryptographic primitives for certificate verification.
//!
//! This module provides a single source of truth for all cryptographic operations
//! used in mDL (ISO 18013-5) and eMRTD (ICAO 9303) verification.
//!
//! # Design Principles
//!
//! - **UniFFI-compatible**: Uses `Arc` for shared state, avoids complex generics
//! - **Consistent error handling**: All operations return `VerificationResult`
//! - **Algorithm-agnostic API**: Unified `verify_signature()` function
//!
//! # Supported Algorithms
//!
//! ## Signature Algorithms
//! - ECDSA with P-256/P-384/P-521 curves
//! - EdDSA (Ed25519, Ed448)
//! - RSA PKCS#1 v1.5 with SHA-1/256/384/512
//! - RSA PSS with SHA-256/384/512
//!
//! ## Hash Algorithms  
//! - SHA-1 (legacy, for compatibility)
//! - SHA-256, SHA-384, SHA-512
//!
//! ## Key Derivation
//! - HKDF (RFC 5869)
//! - PBKDF2 (RFC 2898)
//!
//! ## Symmetric Encryption
//! - AES-GCM (256-bit)
//! - AES-CBC (for BAC protocol)

#[cfg(feature = "cert-builder")]
pub mod cert_builder;
pub mod certificate;
#[cfg(feature = "cert-builder")]
pub mod crl;
pub mod des;
pub mod ecdh;
pub mod ecdsa;
pub mod ed25519;
pub mod ed448;
pub mod hashing;
pub mod iso9796;
pub mod kdf;
pub mod keygen;
pub mod ocsp;
pub mod pkcs12;
pub mod rsa;
pub mod serialization;
pub mod symmetric;

use serde::{Deserialize, Serialize};

use crate::{VerificationError, VerificationResult};

/// Supported signature algorithms for certificate and document verification.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum SignatureAlgorithm {
    /// ECDSA with P-256 curve and SHA-256 (ES256)
    EcdsaP256Sha256,
    /// ECDSA with P-384 curve and SHA-384 (ES384)
    EcdsaP384Sha384,
    /// ECDSA with P-521 curve and SHA-512 (ES512)
    EcdsaP521Sha512,
    /// Ed25519 pure EdDSA (EdDSA with curve25519)
    Ed25519,
    /// Ed448 pure EdDSA (EdDSA with curve448)
    Ed448,
    /// RSA PKCS#1 v1.5 with SHA-1 (RS1) - LEGACY, use only for eMRTD compatibility
    #[deprecated(note = "SHA-1 is cryptographically weak; use only for legacy eMRTD verification")]
    RsaPkcs1Sha1,
    /// RSA PKCS#1 v1.5 with SHA-256 (RS256)
    RsaPkcs1Sha256,
    /// RSA PKCS#1 v1.5 with SHA-384 (RS384)
    RsaPkcs1Sha384,
    /// RSA PKCS#1 v1.5 with SHA-512 (RS512)
    RsaPkcs1Sha512,
    /// RSA PSS with SHA-256 (PS256)
    RsaPssSha256,
    /// RSA PSS with SHA-384 (PS384)
    RsaPssSha384,
    /// RSA PSS with SHA-512 (PS512)
    RsaPssSha512,
}

impl SignatureAlgorithm {
    /// Get the OID for this signature algorithm.
    #[allow(deprecated)]
    pub fn oid(&self) -> &'static str {
        match self {
            Self::EcdsaP256Sha256 => "1.2.840.10045.4.3.2",
            Self::EcdsaP384Sha384 => "1.2.840.10045.4.3.3",
            Self::EcdsaP521Sha512 => "1.2.840.10045.4.3.4",
            Self::Ed25519 => "1.3.101.112",
            Self::Ed448 => "1.3.101.113",
            Self::RsaPkcs1Sha1 => "1.2.840.113549.1.1.5",
            Self::RsaPkcs1Sha256 => "1.2.840.113549.1.1.11",
            Self::RsaPkcs1Sha384 => "1.2.840.113549.1.1.12",
            Self::RsaPkcs1Sha512 => "1.2.840.113549.1.1.13",
            Self::RsaPssSha256 => "1.2.840.113549.1.1.10",
            Self::RsaPssSha384 => "1.2.840.113549.1.1.10",
            Self::RsaPssSha512 => "1.2.840.113549.1.1.10",
        }
    }

    /// Try to determine algorithm from OID string.
    #[allow(deprecated)]
    pub fn from_oid(oid: &str) -> VerificationResult<Self> {
        match oid {
            "1.2.840.10045.4.3.2" => Ok(Self::EcdsaP256Sha256),
            "1.2.840.10045.4.3.3" => Ok(Self::EcdsaP384Sha384),
            "1.2.840.10045.4.3.4" => Ok(Self::EcdsaP521Sha512),
            "1.3.101.112" => Ok(Self::Ed25519),
            "1.3.101.113" => Ok(Self::Ed448),
            "1.2.840.113549.1.1.5" => Ok(Self::RsaPkcs1Sha1),
            "1.2.840.113549.1.1.11" => Ok(Self::RsaPkcs1Sha256),
            "1.2.840.113549.1.1.12" => Ok(Self::RsaPkcs1Sha384),
            "1.2.840.113549.1.1.13" => Ok(Self::RsaPkcs1Sha512),
            _ => Err(VerificationError::internal(format!(
                "Unsupported signature algorithm OID: {}",
                oid
            ))),
        }
    }

    /// Check if this is an ECDSA algorithm.
    pub fn is_ecdsa(&self) -> bool {
        matches!(
            self,
            Self::EcdsaP256Sha256 | Self::EcdsaP384Sha384 | Self::EcdsaP521Sha512
        )
    }

    /// Check if this is an EdDSA algorithm (Ed25519 or Ed448).
    pub fn is_eddsa(&self) -> bool {
        matches!(self, Self::Ed25519 | Self::Ed448)
    }

    /// Check if this is an RSA algorithm.
    #[allow(deprecated)]
    pub fn is_rsa(&self) -> bool {
        matches!(
            self,
            Self::RsaPkcs1Sha1
                | Self::RsaPkcs1Sha256
                | Self::RsaPkcs1Sha384
                | Self::RsaPkcs1Sha512
                | Self::RsaPssSha256
                | Self::RsaPssSha384
                | Self::RsaPssSha512
        )
    }
}

impl std::fmt::Display for SignatureAlgorithm {
    #[allow(deprecated)]
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let name = match self {
            Self::EcdsaP256Sha256 => "ECDSA-P256-SHA256",
            Self::EcdsaP384Sha384 => "ECDSA-P384-SHA384",
            Self::EcdsaP521Sha512 => "ECDSA-P521-SHA512",
            Self::Ed25519 => "Ed25519",
            Self::Ed448 => "Ed448",
            Self::RsaPkcs1Sha1 => "RSA-PKCS1-SHA1",
            Self::RsaPkcs1Sha256 => "RSA-PKCS1-SHA256",
            Self::RsaPkcs1Sha384 => "RSA-PKCS1-SHA384",
            Self::RsaPkcs1Sha512 => "RSA-PKCS1-SHA512",
            Self::RsaPssSha256 => "RSA-PSS-SHA256",
            Self::RsaPssSha384 => "RSA-PSS-SHA384",
            Self::RsaPssSha512 => "RSA-PSS-SHA512",
        };
        write!(f, "{}", name)
    }
}

/// Supported hash algorithms.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum HashAlgorithm {
    /// SHA-1 (legacy, 160-bit)
    Sha1,
    /// SHA-256 (256-bit)
    Sha256,
    /// SHA-384 (384-bit)
    Sha384,
    /// SHA-512 (512-bit)
    Sha512,
}

impl HashAlgorithm {
    /// Get the OID for this hash algorithm.
    pub fn oid(&self) -> &'static str {
        match self {
            Self::Sha1 => "1.3.14.3.2.26",
            Self::Sha256 => "2.16.840.1.101.3.4.2.1",
            Self::Sha384 => "2.16.840.1.101.3.4.2.2",
            Self::Sha512 => "2.16.840.1.101.3.4.2.3",
        }
    }

    /// Try to determine algorithm from OID string.
    pub fn from_oid(oid: &str) -> VerificationResult<Self> {
        match oid {
            "1.3.14.3.2.26" => Ok(Self::Sha1),
            "2.16.840.1.101.3.4.2.1" => Ok(Self::Sha256),
            "2.16.840.1.101.3.4.2.2" => Ok(Self::Sha384),
            "2.16.840.1.101.3.4.2.3" => Ok(Self::Sha512),
            _ => Err(VerificationError::internal(format!(
                "Unsupported hash algorithm OID: {}",
                oid
            ))),
        }
    }

    /// Get the output length in bytes.
    pub fn output_len(&self) -> usize {
        match self {
            Self::Sha1 => 20,
            Self::Sha256 => 32,
            Self::Sha384 => 48,
            Self::Sha512 => 64,
        }
    }
}

impl std::fmt::Display for HashAlgorithm {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let name = match self {
            Self::Sha1 => "SHA-1",
            Self::Sha256 => "SHA-256",
            Self::Sha384 => "SHA-384",
            Self::Sha512 => "SHA-512",
        };
        write!(f, "{}", name)
    }
}

/// Verify a signature using the specified algorithm.
///
/// This is the main entry point for signature verification. It dispatches
/// to the appropriate implementation based on the algorithm.
///
/// # Arguments
///
/// * `algorithm` - The signature algorithm to use
/// * `public_key_der` - DER-encoded public key (SubjectPublicKeyInfo)
/// * `message` - The message that was signed
/// * `signature` - The signature bytes
///
/// # Returns
///
/// `Ok(true)` if signature is valid, `Ok(false)` if invalid,
/// or `Err` if verification cannot be performed.
#[allow(deprecated)]
pub fn verify_signature(
    algorithm: SignatureAlgorithm,
    public_key_der: &[u8],
    message: &[u8],
    signature: &[u8],
) -> VerificationResult<bool> {
    match algorithm {
        SignatureAlgorithm::EcdsaP256Sha256 => {
            ecdsa::verify_p256_sha256(public_key_der, message, signature)
        }
        SignatureAlgorithm::EcdsaP384Sha384 => {
            ecdsa::verify_p384_sha384(public_key_der, message, signature)
        }
        SignatureAlgorithm::EcdsaP521Sha512 => {
            ecdsa::verify_p521_sha512(public_key_der, message, signature)
        }
        SignatureAlgorithm::Ed25519 => {
            ed25519::verify_ed25519_spki(public_key_der, message, signature)
        }
        SignatureAlgorithm::Ed448 => ed448::verify_ed448_spki(public_key_der, message, signature),
        SignatureAlgorithm::RsaPkcs1Sha1 =>
        {
            #[allow(deprecated)]
            rsa::verify_pkcs1_sha1(public_key_der, message, signature)
        }
        SignatureAlgorithm::RsaPkcs1Sha256 => {
            rsa::verify_pkcs1_sha256(public_key_der, message, signature)
        }
        SignatureAlgorithm::RsaPkcs1Sha384 => {
            rsa::verify_pkcs1_sha384(public_key_der, message, signature)
        }
        SignatureAlgorithm::RsaPkcs1Sha512 => {
            rsa::verify_pkcs1_sha512(public_key_der, message, signature)
        }
        SignatureAlgorithm::RsaPssSha256 => {
            rsa::verify_pss_sha256(public_key_der, message, signature)
        }
        SignatureAlgorithm::RsaPssSha384 => {
            rsa::verify_pss_sha384(public_key_der, message, signature)
        }
        SignatureAlgorithm::RsaPssSha512 => {
            rsa::verify_pss_sha512(public_key_der, message, signature)
        }
    }
}

/// Compute a hash using the specified algorithm.
///
/// # Arguments
///
/// * `algorithm` - The hash algorithm to use
/// * `data` - The data to hash
///
/// # Returns
///
/// The hash digest as a byte vector.
pub fn compute_hash(algorithm: HashAlgorithm, data: &[u8]) -> Vec<u8> {
    hashing::hash(algorithm, data)
}

/// Verify that a hash matches expected value.
///
/// # Arguments
///
/// * `algorithm` - The hash algorithm that was used
/// * `data` - The original data
/// * `expected_hash` - The expected hash value
///
/// # Returns
///
/// `true` if hash matches, `false` otherwise.
pub fn verify_hash(algorithm: HashAlgorithm, data: &[u8], expected_hash: &[u8]) -> bool {
    let computed = compute_hash(algorithm, data);
    constant_time_compare(&computed, expected_hash)
}

/// Constant-time comparison to prevent timing attacks.
fn constant_time_compare(a: &[u8], b: &[u8]) -> bool {
    if a.len() != b.len() {
        return false;
    }

    let mut diff = 0u8;
    for (x, y) in a.iter().zip(b.iter()) {
        diff |= x ^ y;
    }
    diff == 0
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_signature_algorithm_display() {
        assert_eq!(
            SignatureAlgorithm::EcdsaP256Sha256.to_string(),
            "ECDSA-P256-SHA256"
        );
        assert_eq!(
            SignatureAlgorithm::RsaPkcs1Sha256.to_string(),
            "RSA-PKCS1-SHA256"
        );
    }

    #[test]
    fn test_signature_algorithm_from_oid() {
        assert_eq!(
            SignatureAlgorithm::from_oid("1.2.840.10045.4.3.2").unwrap(),
            SignatureAlgorithm::EcdsaP256Sha256
        );
        assert_eq!(
            SignatureAlgorithm::from_oid("1.2.840.113549.1.1.11").unwrap(),
            SignatureAlgorithm::RsaPkcs1Sha256
        );
        assert!(SignatureAlgorithm::from_oid("invalid").is_err());
    }

    #[test]
    fn test_hash_algorithm_output_len() {
        assert_eq!(HashAlgorithm::Sha1.output_len(), 20);
        assert_eq!(HashAlgorithm::Sha256.output_len(), 32);
        assert_eq!(HashAlgorithm::Sha384.output_len(), 48);
        assert_eq!(HashAlgorithm::Sha512.output_len(), 64);
    }

    #[test]
    fn test_constant_time_compare() {
        assert!(constant_time_compare(b"hello", b"hello"));
        assert!(!constant_time_compare(b"hello", b"world"));
        assert!(!constant_time_compare(b"hello", b"hell"));
    }
}
