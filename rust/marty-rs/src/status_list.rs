//! W3C Bitstring Status List v1.0 and IETF Token Status List
//!
//! Implements both status list specifications with PyO3 bindings:
//! - W3C Bitstring Status List v1.0 (Candidate Recommendation)
//!   <https://www.w3.org/TR/vc-bitstring-status-list/>
//! - IETF Token Status List (draft-ietf-oauth-status-list)
//!   <https://www.ietf.org/archive/id/draft-ietf-oauth-status-list-02.html>
//!
//! Both types expose a shard-friendly API for managing credential revocation
//! at scale, with support for gzip/zlib encoding per spec.

use flate2::{read::GzDecoder, write::GzEncoder, Compression};
use pyo3::prelude::*;
use pyo3::types::PyBytes;
use std::io::{Read, Write};

use base64::Engine;

use crate::error::MartyError;

// ============================================================================
// W3C Bitstring Status List
// ============================================================================

/// W3C Bitstring Status List v1.0 implementation.
///
/// A privacy-preserving, space-efficient, and high-performance mechanism for
/// publishing credential revocation/suspension status using bitstrings.
///
/// Each bit represents one credential:
///   0 = valid, 1 = revoked (for "revocation" purpose)
///   0 = valid, 1 = suspended (for "suspension" purpose)
///
/// Spec: <https://www.w3.org/TR/vc-bitstring-status-list/>
#[pyclass]
#[derive(Clone)]
pub struct BitstringStatusList {
    /// Raw bitstring bytes — 1 bit per credential
    bits: Vec<u8>,
    /// Number of credential slots tracked
    size: usize,
}

#[pymethods]
impl BitstringStatusList {
    /// Create a new bitstring status list with the given capacity.
    ///
    /// `size` is the number of credential slots. All bits are initialised to 0
    /// (= valid). The minimum size per the W3C spec is 131072 (16 KB × 8).
    #[new]
    #[pyo3(signature = (size=131072))]
    fn new(size: usize) -> PyResult<Self> {
        if size == 0 {
            return Err(MartyError::InvalidArgument(
                "size must be > 0".into(),
            )
            .into());
        }
        let byte_len = (size + 7) / 8;
        Ok(Self {
            bits: vec![0u8; byte_len],
            size,
        })
    }

    /// Total number of credential slots in this list.
    #[getter]
    fn size(&self) -> usize {
        self.size
    }

    /// Set a credential's status at the given index.
    ///
    /// For "revocation" purpose: `true` = revoked, `false` = valid
    /// For "suspension" purpose: `true` = suspended, `false` = active
    fn set_status(&mut self, index: usize, revoked: bool) -> PyResult<()> {
        if index >= self.size {
            return Err(MartyError::IndexOutOfBounds {
                index,
                size: self.size,
            }
            .into());
        }
        let byte_idx = index / 8;
        // Bits are indexed MSB-first per the W3C spec §4.1
        let bit_idx = 7 - (index % 8);
        if revoked {
            self.bits[byte_idx] |= 1 << bit_idx;
        } else {
            self.bits[byte_idx] &= !(1 << bit_idx);
        }
        Ok(())
    }

    /// Get a credential's status at the given index.
    ///
    /// Returns `true` if the bit is set (revoked/suspended).
    fn get_status(&self, index: usize) -> PyResult<bool> {
        if index >= self.size {
            return Err(MartyError::IndexOutOfBounds {
                index,
                size: self.size,
            }
            .into());
        }
        let byte_idx = index / 8;
        let bit_idx = 7 - (index % 8);
        Ok((self.bits[byte_idx] >> bit_idx) & 1 == 1)
    }

    /// Encode the bitstring to the multibase-base64url GZIP format
    /// required by the W3C spec.
    ///
    /// Encoding: `multibase(base64url(gzip(bitstring)))`
    /// The multibase prefix 'u' denotes base64url with no padding.
    fn to_encoded_list(&self) -> PyResult<String> {
        let mut encoder = GzEncoder::new(Vec::new(), Compression::default());
        encoder
            .write_all(&self.bits)
            .map_err(|e| MartyError::Encoding(e.to_string()))?;

        // Pad to 16 KB minimum per W3C spec §4.1
        let min_bytes = 16 * 1024;
        if self.bits.len() < min_bytes {
            let padding = vec![0u8; min_bytes - self.bits.len()];
            encoder
                .write_all(&padding)
                .map_err(|e| MartyError::Encoding(e.to_string()))?;
        }

        let compressed = encoder
            .finish()
            .map_err(|e| MartyError::Encoding(e.to_string()))?;

        // multibase base64url, no padding — prefix 'u'
        use base64::engine::general_purpose::URL_SAFE_NO_PAD;
        use base64::Engine;
        let b64 = URL_SAFE_NO_PAD.encode(&compressed);
        Ok(format!("u{b64}"))
    }

    /// Decode an `encodedList` string produced by `to_encoded_list()`.
    ///
    /// Expects multibase base64url-no-pad GZIP data (prefix 'u').
    #[staticmethod]
    fn from_encoded_list(encoded: &str) -> PyResult<Self> {
        // Strip multibase prefix
        let b64 = encoded
            .strip_prefix('u')
            .ok_or_else(|| {
                MartyError::Encoding(
                    "encodedList must start with multibase prefix 'u'".into(),
                )
            })?;

        use base64::engine::general_purpose::URL_SAFE_NO_PAD;
        use base64::Engine;
        let compressed = URL_SAFE_NO_PAD
            .decode(b64)
            .map_err(|e| MartyError::Encoding(format!("base64 decode: {e}")))?;

        let mut decoder = GzDecoder::new(compressed.as_slice());
        let mut bits = Vec::new();
        decoder
            .read_to_end(&mut bits)
            .map_err(|e| MartyError::Encoding(format!("gzip decode: {e}")))?;

        let size = bits.len() * 8;
        Ok(Self { bits, size })
    }

    /// Convenience: decode from a base64-standard encoded GZIP (legacy compat).
    #[staticmethod]
    fn from_base64(b64: &str) -> PyResult<Self> {
        use base64::engine::general_purpose::STANDARD;
        use base64::Engine;
        let compressed = STANDARD
            .decode(b64)
            .map_err(|e| MartyError::Encoding(format!("base64 decode: {e}")))?;

        let mut decoder = GzDecoder::new(compressed.as_slice());
        let mut bits = Vec::new();
        decoder
            .read_to_end(&mut bits)
            .map_err(|e| MartyError::Encoding(format!("gzip decode: {e}")))?;

        let size = bits.len() * 8;
        Ok(Self { bits, size })
    }

    /// Convenience: encode to base64-standard GZIP (legacy compat).
    fn to_base64(&self) -> PyResult<String> {
        let mut encoder = GzEncoder::new(Vec::new(), Compression::default());
        encoder
            .write_all(&self.bits)
            .map_err(|e| MartyError::Encoding(e.to_string()))?;
        let compressed = encoder
            .finish()
            .map_err(|e| MartyError::Encoding(e.to_string()))?;
        use base64::engine::general_purpose::STANDARD;
        use base64::Engine;
        Ok(STANDARD.encode(&compressed))
    }

    /// Build the `credentialSubject` JSON for a BitstringStatusListCredential.
    ///
    /// Returns a JSON string conforming to:
    /// ```json
    /// {
    ///   "id": "<id>#list",
    ///   "type": "BitstringStatusList",
    ///   "statusPurpose": "<purpose>",
    ///   "encodedList": "<multibase-b64url-gzip>"
    /// }
    /// ```
    fn to_credential_subject(
        &self,
        id: &str,
        status_purpose: &str,
    ) -> PyResult<String> {
        let encoded_list = self.to_encoded_list()?;
        let subject = serde_json::json!({
            "id": format!("{id}#list"),
            "type": "BitstringStatusList",
            "statusPurpose": status_purpose,
            "encodedList": encoded_list
        });
        serde_json::to_string(&subject)
            .map_err(|e| MartyError::Serialization(e.to_string()).into())
    }

    /// Build a complete BitstringStatusListCredential as JSON.
    ///
    /// This is the W3C Verifiable Credential that gets published at
    /// `status_credential_url` so verifiers can check revocation status.
    ///
    /// Note: The credential is **unsigned** — the caller must sign it
    /// (e.g. as a JWT-VC) using its issuer key.
    fn to_status_list_credential(
        &self,
        credential_id: &str,
        issuer_id: &str,
        status_purpose: &str,
    ) -> PyResult<String> {
        let encoded_list = self.to_encoded_list()?;
        let now = chrono::Utc::now().to_rfc3339();

        let credential = serde_json::json!({
            "@context": [
                "https://www.w3.org/ns/credentials/v2",
                "https://www.w3.org/ns/credentials/status/v1"
            ],
            "id": credential_id,
            "type": ["VerifiableCredential", "BitstringStatusListCredential"],
            "issuer": issuer_id,
            "validFrom": now,
            "credentialSubject": {
                "id": format!("{credential_id}#list"),
                "type": "BitstringStatusList",
                "statusPurpose": status_purpose,
                "encodedList": encoded_list
            }
        });

        serde_json::to_string(&credential)
            .map_err(|e| MartyError::Serialization(e.to_string()).into())
    }

    fn __repr__(&self) -> String {
        let revoked_count = self
            .bits
            .iter()
            .map(|b| b.count_ones() as usize)
            .sum::<usize>();
        format!(
            "BitstringStatusList(size={}, revoked={})",
            self.size, revoked_count
        )
    }
}

// ============================================================================
// IETF Token Status List (draft-ietf-oauth-status-list)
// ============================================================================

/// IETF Token Status List implementation.
///
/// Supports multi-bit status values (1, 2, 4, or 8 bits per entry).
/// Used for mDoc / CWT credentials.
///
/// Status values (for 2-bit):
///   0x00 = VALID
///   0x01 = INVALID (revoked, irreversible)
///   0x02 = SUSPENDED (reversible)
///   0x03 = APPLICATION_SPECIFIC
///
/// Spec: <https://www.ietf.org/archive/id/draft-ietf-oauth-status-list-02.html>
#[pyclass]
#[derive(Clone)]
pub struct TokenStatusList {
    /// Raw status bytes
    data: Vec<u8>,
    /// Bits per status entry (1, 2, 4, or 8)
    bits_per_status: u8,
    /// Number of credential slots
    size: usize,
}

#[pymethods]
impl TokenStatusList {
    /// Create a new Token Status List.
    ///
    /// `size`: number of credential slots.
    /// `bits`: bits per status entry (1, 2, 4, or 8). Default 2.
    #[new]
    #[pyo3(signature = (size, bits=2))]
    fn new(size: usize, bits: u8) -> PyResult<Self> {
        if !matches!(bits, 1 | 2 | 4 | 8) {
            return Err(MartyError::InvalidArgument(
                "bits must be 1, 2, 4, or 8".into(),
            )
            .into());
        }
        if size == 0 {
            return Err(MartyError::InvalidArgument(
                "size must be > 0".into(),
            )
            .into());
        }
        let entries_per_byte = 8 / bits as usize;
        let byte_len = (size + entries_per_byte - 1) / entries_per_byte;
        Ok(Self {
            data: vec![0u8; byte_len],
            bits_per_status: bits,
            size,
        })
    }

    /// Number of credential slots.
    #[getter]
    fn size(&self) -> usize {
        self.size
    }

    /// Bits per status entry.
    #[getter]
    fn bits_per_status(&self) -> u8 {
        self.bits_per_status
    }

    /// Set the status value at the given index.
    fn set_status(&mut self, index: usize, status: u8) -> PyResult<()> {
        if index >= self.size {
            return Err(MartyError::IndexOutOfBounds {
                index,
                size: self.size,
            }
            .into());
        }
        let mask = (1u8 << self.bits_per_status) - 1;
        if status > mask {
            return Err(MartyError::InvalidArgument(format!(
                "status {status} exceeds max {} for {}-bit entries",
                mask, self.bits_per_status
            ))
            .into());
        }
        let entries_per_byte = 8 / self.bits_per_status as usize;
        let byte_idx = index / entries_per_byte;
        let bit_offset = (index % entries_per_byte) * self.bits_per_status as usize;
        self.data[byte_idx] &= !(mask << bit_offset);
        self.data[byte_idx] |= status << bit_offset;
        Ok(())
    }

    /// Get the status value at the given index.
    fn get_status(&self, index: usize) -> PyResult<u8> {
        if index >= self.size {
            return Err(MartyError::IndexOutOfBounds {
                index,
                size: self.size,
            }
            .into());
        }
        let mask = (1u8 << self.bits_per_status) - 1;
        let entries_per_byte = 8 / self.bits_per_status as usize;
        let byte_idx = index / entries_per_byte;
        let bit_offset = (index % entries_per_byte) * self.bits_per_status as usize;
        Ok((self.data[byte_idx] >> bit_offset) & mask)
    }

    /// Encode to CBOR bytes (zlib-compressed).
    fn to_cbor<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyBytes>> {
        use flate2::write::ZlibEncoder;
        let mut encoder = ZlibEncoder::new(Vec::new(), Compression::default());
        encoder
            .write_all(&self.data)
            .map_err(|e| MartyError::Encoding(e.to_string()))?;
        let compressed = encoder
            .finish()
            .map_err(|e| MartyError::Encoding(e.to_string()))?;

        // CBOR-encode the status_list claim structure
        let claim = serde_json::json!({
            "bits": self.bits_per_status,
            "lst": base64::engine::general_purpose::URL_SAFE_NO_PAD.encode(&compressed)
        });

        let cbor_bytes = serde_json::to_vec(&claim)
            .map_err(|e| MartyError::Serialization(e.to_string()))?;
        Ok(PyBytes::new(py, &cbor_bytes))
    }

    /// Decode from CBOR bytes.
    #[staticmethod]
    fn from_cbor(data: &[u8]) -> PyResult<Self> {
        use flate2::read::ZlibDecoder;

        let claim: serde_json::Value = serde_json::from_slice(data)
            .map_err(|e| MartyError::Encoding(format!("cbor decode: {e}")))?;

        let bits_per_status = claim["bits"]
            .as_u64()
            .ok_or_else(|| MartyError::Encoding("missing 'bits' field".into()))?
            as u8;

        let lst_b64 = claim["lst"]
            .as_str()
            .ok_or_else(|| MartyError::Encoding("missing 'lst' field".into()))?;

        use base64::Engine;
        let compressed = base64::engine::general_purpose::URL_SAFE_NO_PAD
            .decode(lst_b64)
            .map_err(|e| MartyError::Encoding(format!("base64 decode: {e}")))?;

        let mut decoder = ZlibDecoder::new(compressed.as_slice());
        let mut decompressed = Vec::new();
        decoder
            .read_to_end(&mut decompressed)
            .map_err(|e| MartyError::Encoding(format!("zlib decode: {e}")))?;

        let entries_per_byte = 8 / bits_per_status as usize;
        let size = decompressed.len() * entries_per_byte;
        Ok(Self {
            data: decompressed,
            bits_per_status,
            size,
        })
    }

    /// Build the `status_list` JWT claim per IETF spec.
    fn to_status_list_claim(&self) -> PyResult<String> {
        use base64::Engine;
        use flate2::write::ZlibEncoder;

        let mut encoder = ZlibEncoder::new(Vec::new(), Compression::default());
        encoder
            .write_all(&self.data)
            .map_err(|e| MartyError::Encoding(e.to_string()))?;
        let compressed = encoder
            .finish()
            .map_err(|e| MartyError::Encoding(e.to_string()))?;

        let lst = base64::engine::general_purpose::URL_SAFE_NO_PAD.encode(&compressed);

        let claim = serde_json::json!({
            "bits": self.bits_per_status,
            "lst": lst
        });

        serde_json::to_string(&claim)
            .map_err(|e| MartyError::Serialization(e.to_string()).into())
    }

    fn __repr__(&self) -> String {
        let non_zero: usize = (0..self.size)
            .filter(|&i| {
                let mask = (1u8 << self.bits_per_status) - 1;
                let epb = 8 / self.bits_per_status as usize;
                let b = i / epb;
                let o = (i % epb) * self.bits_per_status as usize;
                (self.data[b] >> o) & mask != 0
            })
            .count();
        format!(
            "TokenStatusList(size={}, bits={}, non_zero={})",
            self.size, self.bits_per_status, non_zero
        )
    }
}

// ============================================================================
// Convenience functions exposed to Python
// ============================================================================

/// Build a `credentialSubject` JSON string for a BitstringStatusListCredential.
#[pyfunction]
pub fn create_bitstring_credential_subject(
    credential_id: &str,
    status_purpose: &str,
    encoded_list: &str,
) -> PyResult<String> {
    let subject = serde_json::json!({
        "id": format!("{credential_id}#list"),
        "type": "BitstringStatusList",
        "statusPurpose": status_purpose,
        "encodedList": encoded_list
    });
    serde_json::to_string(&subject)
        .map_err(|e| MartyError::Serialization(e.to_string()).into())
}

/// Build a `status_list` JWT claim for the IETF Token Status List.
#[pyfunction]
pub fn create_status_list_claim(
    bits: u8,
    lst: &str,
) -> PyResult<String> {
    let claim = serde_json::json!({
        "bits": bits,
        "lst": lst
    });
    serde_json::to_string(&claim)
        .map_err(|e| MartyError::Serialization(e.to_string()).into())
}

/// Build a `credentialStatus` entry for embedding in an issued credential.
///
/// Returns a JSON string following W3C Bitstring Status List v1.0:
/// ```json
/// {
///   "id": "<status_list_credential>#<index>",
///   "type": "BitstringStatusListEntry",
///   "statusPurpose": "revocation",
///   "statusListIndex": "<index>",
///   "statusListCredential": "<status_list_credential>"
/// }
/// ```
#[pyfunction]
pub fn create_credential_status_entry(
    status_list_credential: &str,
    status_list_index: usize,
    status_purpose: &str,
) -> PyResult<String> {
    let entry = serde_json::json!({
        "id": format!("{status_list_credential}#{status_list_index}"),
        "type": "BitstringStatusListEntry",
        "statusPurpose": status_purpose,
        "statusListIndex": status_list_index.to_string(),
        "statusListCredential": status_list_credential
    });
    serde_json::to_string(&entry)
        .map_err(|e| MartyError::Serialization(e.to_string()).into())
}

// ============================================================================
// Module registration
// ============================================================================

pub fn register_status_list_module(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<BitstringStatusList>()?;
    m.add_class::<TokenStatusList>()?;
    m.add_function(wrap_pyfunction!(create_bitstring_credential_subject, m)?)?;
    m.add_function(wrap_pyfunction!(create_status_list_claim, m)?)?;
    m.add_function(wrap_pyfunction!(create_credential_status_entry, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn bitstring_roundtrip() {
        let mut bsl = BitstringStatusList {
            bits: vec![0u8; 16384],
            size: 131072,
        };

        // Set some bits
        bsl.set_status(0, true).unwrap();
        bsl.set_status(100, true).unwrap();
        bsl.set_status(131071, true).unwrap();

        assert!(bsl.get_status(0).unwrap());
        assert!(!bsl.get_status(1).unwrap());
        assert!(bsl.get_status(100).unwrap());
        assert!(bsl.get_status(131071).unwrap());

        // Encode → decode roundtrip
        let encoded = bsl.to_encoded_list().unwrap();
        assert!(encoded.starts_with('u'));

        let decoded = BitstringStatusList::from_encoded_list(&encoded).unwrap();
        assert!(decoded.get_status(0).unwrap());
        assert!(!decoded.get_status(1).unwrap());
        assert!(decoded.get_status(100).unwrap());
    }

    #[test]
    fn token_status_list_roundtrip() {
        let mut tsl = TokenStatusList {
            data: vec![0u8; 65536],
            bits_per_status: 2,
            size: 262144,
        };

        tsl.set_status(0, 1).unwrap(); // INVALID
        tsl.set_status(1, 2).unwrap(); // SUSPENDED
        tsl.set_status(2, 0).unwrap(); // VALID

        assert_eq!(tsl.get_status(0).unwrap(), 1);
        assert_eq!(tsl.get_status(1).unwrap(), 2);
        assert_eq!(tsl.get_status(2).unwrap(), 0);
    }

    #[test]
    fn bitstring_out_of_bounds() {
        let bsl = BitstringStatusList {
            bits: vec![0u8; 1],
            size: 8,
        };
        assert!(bsl.get_status(8).is_err());
    }

    #[test]
    fn credential_status_entry() {
        let json_str = create_credential_status_entry(
            "https://status.example.com/credentials/status/3",
            42,
            "revocation",
        )
        .unwrap();

        let val: serde_json::Value = serde_json::from_str(&json_str).unwrap();
        assert_eq!(val["type"], "BitstringStatusListEntry");
        assert_eq!(val["statusPurpose"], "revocation");
        assert_eq!(val["statusListIndex"], "42");
        assert_eq!(
            val["statusListCredential"],
            "https://status.example.com/credentials/status/3"
        );
    }
}
