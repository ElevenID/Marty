//! Digital Travel Credential helpers exposed via Python bindings.
//!
//! These helpers operate on JSON blobs that mirror the Python/proto shapes for
//! DTC create/sign/verify. They normalize data groups (base64), compute
//! canonical payloads, and perform lightweight signing/verification.

use std::time::{SystemTime, UNIX_EPOCH};

use base64::{engine::general_purpose, Engine as _};
use const_oid::ObjectIdentifier;
use der::Decode;
use pkcs8::PrivateKeyInfo;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use p256::ecdsa::{signature::Signer, signature::Verifier, Signature as P256Signature, SigningKey as P256SigningKey, VerifyingKey as P256VerifyingKey};
use p256::pkcs8::{DecodePrivateKey as _, DecodePublicKey as _};
use p256::{PublicKey as P256PublicKey, SecretKey as P256SecretKey};
use p384::ecdsa::{Signature as P384Signature, SigningKey as P384SigningKey, VerifyingKey as P384VerifyingKey};
use p384::{PublicKey as P384PublicKey, SecretKey as P384SecretKey};
use spki::SubjectPublicKeyInfoRef;
use x509_cert::Certificate;
use crate::verification::ChainValidator;

#[derive(Debug, Serialize, Deserialize, Clone, Default)]
pub struct DataGroup {
    pub dg_number: i32,
    #[serde(default)]
    pub data: String, // base64-encoded
    #[serde(default)]
    pub data_type: String,
}

#[derive(Debug, Serialize, Deserialize, Clone, Default)]
pub struct Type1Profile {
    #[serde(default)]
    pub mrz_line1: String,
    #[serde(default)]
    pub mrz_line2: String,
    #[serde(default)]
    pub sod_hash: String,
    #[serde(default)]
    pub issuing_state: String,
    #[serde(default)]
    pub passive_auth_ok: bool,
}

#[derive(Debug, Serialize, Deserialize, Clone, Default)]
pub struct Type2Profile {
    #[serde(default)]
    pub chip_auth_public_key: String,
    #[serde(default)]
    pub device_public_key: String,
    #[serde(default)]
    pub attestation_cert_hash: String,
    #[serde(default)]
    pub passive_auth_ok: bool,
}

#[derive(Debug, Serialize, Deserialize, Clone, Default)]
pub struct Type3Profile {
    #[serde(default)]
    pub remote_attestation_report: String,
    #[serde(default)]
    pub device_binding_id: String,
    #[serde(default)]
    pub ephemeral_public_key: String,
    #[serde(default)]
    pub session_id: String,
    #[serde(default)]
    pub attestation_cert_hash: String,
}

#[derive(Debug, Serialize, Deserialize, Clone, Default)]
pub struct SignatureInfo {
    #[serde(default)]
    pub signature_date: String,
    #[serde(default)]
    pub signer_id: String,
    #[serde(default)]
    pub signature: String,
    #[serde(default)]
    pub is_valid: bool,
}

#[derive(Debug, Serialize, Deserialize, Clone, Default)]
pub struct PersonalDetails {
    #[serde(default)]
    pub first_name: String,
    #[serde(default)]
    pub last_name: String,
    #[serde(default)]
    pub date_of_birth: String,
    #[serde(default)]
    pub gender: String,
    #[serde(default)]
    pub nationality: String,
    #[serde(default)]
    pub place_of_birth: String,
    #[serde(default)]
    pub portrait: String, // base64
    #[serde(default)]
    pub signature: String, // base64
    #[serde(default)]
    pub other_names: Vec<String>,
}

#[derive(Debug, Serialize, Deserialize, Clone, Default)]
pub struct DtcRecord {
    #[serde(default)]
    pub dtc_id: String,
    #[serde(default)]
    pub passport_number: String,
    #[serde(default)]
    pub issuing_authority: String,
    #[serde(default)]
    pub issue_date: String,
    #[serde(default)]
    pub expiry_date: String,
    #[serde(default)]
    pub personal_details: PersonalDetails,
    #[serde(default)]
    pub data_groups: Vec<DataGroup>,
    #[serde(default)]
    pub dtc_type: i32,
    #[serde(default)]
    pub access_control: i32,
    #[serde(default)]
    pub access_key: String,
    #[serde(default)]
    pub dtc_valid_from: String,
    #[serde(default)]
    pub dtc_valid_until: String,
    #[serde(default)]
    pub type1_profile: Option<Type1Profile>,
    #[serde(default)]
    pub type2_profile: Option<Type2Profile>,
    #[serde(default)]
    pub type3_profile: Option<Type3Profile>,
    #[serde(default)]
    pub is_signed: bool,
    #[serde(default)]
    pub is_revoked: bool,
    #[serde(default)]
    pub linked_passport: Option<String>,
    #[serde(default)]
    pub creation_date: String,
    #[serde(default)]
    pub signature_info: Option<SignatureInfo>,
}

fn now_iso() -> String {
    let secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    // Coarse ISO8601 without timezone (UTC assumed)
    format!("{:010}Z", secs)
}

fn b64_encode(bytes: &[u8]) -> String {
    general_purpose::STANDARD.encode(bytes)
}

fn b64_decode(s: &str) -> Option<Vec<u8>> {
    general_purpose::STANDARD.decode(s.as_bytes()).ok()
}

fn canonical_payload(record: &DtcRecord) -> Result<Vec<u8>, String> {
    // Serialize with stable key ordering (BTreeMap) and without signature_info to avoid self-reference
    let mut map = serde_json::to_value(record).map_err(|e| e.to_string())?;
    if let Value::Object(ref mut obj) = map {
        obj.remove("signature_info");
        obj.remove("is_signed");
    }
    serde_json::to_vec(&map).map_err(|e| e.to_string())
}

fn normalize_base64(value: &mut String) {
    // If already base64, leave as-is; otherwise attempt to interpret as bytes
    if b64_decode(value).is_none() {
        // treat as UTF-8 and encode
        let enc = b64_encode(value.as_bytes());
        *value = enc;
    }
}

fn normalize_record(mut record: DtcRecord) -> DtcRecord {
    if record.dtc_id.is_empty() {
        record.dtc_id = now_iso();
    }
    if record.creation_date.is_empty() {
        record.creation_date = now_iso();
    }
    // Normalize data groups
    for dg in &mut record.data_groups {
        normalize_base64(&mut dg.data);
    }
    // Normalize portrait/signature
    normalize_base64(&mut record.personal_details.portrait);
    normalize_base64(&mut record.personal_details.signature);

    // Fill Type1 sod_hash if missing
    if let Some(ref mut t1) = record.type1_profile {
        if t1.sod_hash.is_empty() {
            let dg_bytes: Vec<u8> = record
                .data_groups
                .iter()
                .filter_map(|dg| b64_decode(&dg.data))
                .flatten()
                .collect();
            if !dg_bytes.is_empty() {
                let mut hasher = Sha256::new();
                hasher.update(&dg_bytes);
                t1.sod_hash = hex::encode(hasher.finalize());
            }
        }
        if t1.issuing_state.is_empty() {
            t1.issuing_state = record.issuing_authority.clone();
        }
    }

    record
}

fn decode_pem_body(pem: &str) -> Result<Vec<u8>, String> {
    let mut b64 = String::new();
    for line in pem.lines() {
        let line = line.trim();
        if line.starts_with("-----") || line.is_empty() {
            continue;
        }
        b64.push_str(line);
    }
    if b64.is_empty() {
        return Err("PEM payload missing".to_string());
    }
    general_purpose::STANDARD
        .decode(b64.as_bytes())
        .map_err(|e| format!("Invalid PEM base64: {}", e))
}

#[derive(Debug, Clone, Copy)]
enum EcCurve {
    P256,
    P384,
}

fn curve_from_oid(oid: ObjectIdentifier) -> Option<EcCurve> {
    match oid {
        oid if oid == ObjectIdentifier::new_unwrap("1.2.840.10045.3.1.7") => Some(EcCurve::P256),
        oid if oid == ObjectIdentifier::new_unwrap("1.3.132.0.34") => Some(EcCurve::P384),
        _ => None,
    }
}

fn detect_curve_from_private_key_pem(pem: &str) -> Result<EcCurve, String> {
    let der = decode_pem_body(pem)?;
    if let Ok(pkcs8) = PrivateKeyInfo::try_from(der.as_slice()) {
        if let Some(params) = pkcs8.algorithm.parameters {
            let oid = params.decode_as::<ObjectIdentifier>().map_err(|e| e.to_string())?;
            if let Some(curve) = curve_from_oid(oid) {
                return Ok(curve);
            }
        }
    }

    if P256SecretKey::from_sec1_der(&der).is_ok() {
        return Ok(EcCurve::P256);
    }
    if P384SecretKey::from_sec1_der(&der).is_ok() {
        return Ok(EcCurve::P384);
    }

    Err("Unsupported EC private key format or curve".to_string())
}

fn detect_curve_from_public_key_pem(pem: &str) -> Result<EcCurve, String> {
    let der = decode_pem_body(pem)?;
    if let Ok(spki) = SubjectPublicKeyInfoRef::try_from(der.as_slice()) {
        if let Some(params) = spki.algorithm.parameters {
            let oid = params.decode_as::<ObjectIdentifier>().map_err(|e| e.to_string())?;
            if let Some(curve) = curve_from_oid(oid) {
                return Ok(curve);
            }
        }
    }

    match der.len() {
        65 => Ok(EcCurve::P256),
        97 => Ok(EcCurve::P384),
        _ => Err("Unsupported EC public key format or curve".to_string()),
    }
}

fn parse_p256_signing_key(pem: &str) -> Result<P256SigningKey, String> {
    let pkcs8 = P256SigningKey::from_pkcs8_pem(pem).map_err(|e| e.to_string());
    if let Ok(key) = pkcs8 {
        return Ok(key);
    }
    let pkcs8_err = pkcs8.err().unwrap_or_else(|| "unknown PKCS#8 error".to_string());
    let der = decode_pem_body(pem)
        .map_err(|e| format!("PKCS#8 parse failed: {}; SEC1 decode failed: {}", pkcs8_err, e))?;
    let secret = P256SecretKey::from_sec1_der(&der)
        .map_err(|e| format!("PKCS#8 parse failed: {}; SEC1 parse failed: {}", pkcs8_err, e))?;
    Ok(P256SigningKey::from(secret))
}

fn parse_p384_signing_key(pem: &str) -> Result<P384SigningKey, String> {
    let pkcs8 = P384SigningKey::from_pkcs8_pem(pem).map_err(|e| e.to_string());
    if let Ok(key) = pkcs8 {
        return Ok(key);
    }
    let pkcs8_err = pkcs8.err().unwrap_or_else(|| "unknown PKCS#8 error".to_string());
    let der = decode_pem_body(pem)
        .map_err(|e| format!("PKCS#8 parse failed: {}; SEC1 decode failed: {}", pkcs8_err, e))?;
    let secret = P384SecretKey::from_sec1_der(&der)
        .map_err(|e| format!("PKCS#8 parse failed: {}; SEC1 parse failed: {}", pkcs8_err, e))?;
    Ok(P384SigningKey::from(secret))
}

fn sign_ecdsa(payload: &[u8], signing_key_pem: &str) -> Result<String, String> {
    match detect_curve_from_private_key_pem(signing_key_pem)? {
        EcCurve::P256 => {
            let sk = parse_p256_signing_key(signing_key_pem)?;
            let sig: P256Signature = sk.sign(payload);
            Ok(b64_encode(sig.to_der().as_bytes()))
        }
        EcCurve::P384 => {
            let sk = parse_p384_signing_key(signing_key_pem)?;
            let sig: P384Signature = sk.sign(payload);
            Ok(b64_encode(sig.to_der().as_bytes()))
        }
    }
}

fn parse_p256_verifying_key(pem: &str) -> Result<P256VerifyingKey, String> {
    if let Ok(key) = P256VerifyingKey::from_public_key_pem(pem) {
        return Ok(key);
    }
    let der = decode_pem_body(pem)?;
    let public_key = P256PublicKey::from_sec1_bytes(&der).map_err(|e| e.to_string())?;
    Ok(P256VerifyingKey::from(public_key))
}

fn parse_p384_verifying_key(pem: &str) -> Result<P384VerifyingKey, String> {
    if let Ok(key) = P384VerifyingKey::from_public_key_pem(pem) {
        return Ok(key);
    }
    let der = decode_pem_body(pem)?;
    let public_key = P384PublicKey::from_sec1_bytes(&der).map_err(|e| e.to_string())?;
    Ok(P384VerifyingKey::from(public_key))
}

fn verify_ecdsa(payload: &[u8], sig_b64: &str, public_key_pem: &str) -> Result<bool, String> {
    let sig_bytes = b64_decode(sig_b64).ok_or_else(|| "invalid signature b64".to_string())?;

    match detect_curve_from_public_key_pem(public_key_pem)? {
        EcCurve::P256 => {
            let vk = parse_p256_verifying_key(public_key_pem)?;
            let sig = P256Signature::from_der(&sig_bytes).map_err(|e| e.to_string())?;
            Ok(vk.verify(payload, &sig).is_ok())
        }
        EcCurve::P384 => {
            let vk = parse_p384_verifying_key(public_key_pem)?;
            let sig = P384Signature::from_der(&sig_bytes).map_err(|e| e.to_string())?;
            Ok(vk.verify(payload, &sig).is_ok())
        }
    }
}

fn public_key_bytes_from_pem(pem: &str) -> Result<Vec<u8>, String> {
    let der = decode_pem_body(pem)?;
    if let Ok(spki) = SubjectPublicKeyInfoRef::try_from(der.as_slice()) {
        return Ok(spki.subject_public_key.raw_bytes().to_vec());
    }
    Ok(der)
}

fn public_key_bytes_from_cert_pem(pem: &str) -> Result<Vec<u8>, String> {
    let der = decode_pem_body(pem)?;
    let cert = Certificate::from_der(&der).map_err(|e| e.to_string())?;
    Ok(cert
        .tbs_certificate
        .subject_public_key_info
        .subject_public_key
        .raw_bytes()
        .to_vec())
}

fn validate_chain(trust_anchors: &[String], chain: &[String]) -> Result<bool, String> {
    if trust_anchors.is_empty() || chain.is_empty() {
        return Ok(true); // nothing to validate
    }
    let mut validator = ChainValidator::new();
    for ta in trust_anchors {
        validator
            .add_trust_anchor_pem(ta)
            .map_err(|e| e.to_string())?;
    }
    for (idx, cert) in chain.iter().enumerate() {
        if idx == chain.len() - 1 {
            // last element assumed root, already added above
            continue;
        }
        validator
            .add_intermediate_pem(cert)
            .map_err(|e| e.to_string())?;
    }
    let result = validator.validate_chain(chain).map_err(|e| e.to_string())?;
    Ok(result.valid)
}

pub fn create_dtc_json(input: &str) -> Result<String, String> {
    let record: DtcRecord = serde_json::from_str(input).map_err(|e| e.to_string())?;
    let norm = normalize_record(record);
    serde_json::to_string(&norm).map_err(|e| e.to_string())
}

pub fn sign_dtc_json(input: &str) -> Result<String, String> {
    // Accept optional signing_key_pem and signer_public_key_pem in the JSON envelope
    let value: Value = serde_json::from_str(input).map_err(|e| e.to_string())?;
    let signing_key = value
        .get("signing_key_pem")
        .and_then(|v| v.as_str())
        .map(|s| s.to_string())
        .ok_or_else(|| "signing_key_pem is required".to_string())?;
    let signer_id = value
        .get("signer_id")
        .and_then(|v| v.as_str())
        .unwrap_or("rust-dtc");

    let mut record: DtcRecord = serde_json::from_value(value.clone()).map_err(|e| e.to_string())?;
    let norm = normalize_record(record.clone());
    let payload = canonical_payload(&norm)?;
    let sig_b64 = sign_ecdsa(&payload, &signing_key)?;

    record.is_signed = true;
    record.signature_info = Some(SignatureInfo {
        signature_date: now_iso(),
        signer_id: signer_id.to_string(),
        signature: sig_b64,
        is_valid: true,
    });

    serde_json::to_string(&record).map_err(|e| e.to_string())
}

pub fn verify_dtc_json(input: &str) -> Result<String, String> {
    let value: Value = serde_json::from_str(input).map_err(|e| e.to_string())?;
    let record: DtcRecord = serde_json::from_value(value.clone()).map_err(|e| e.to_string())?;
    let norm = normalize_record(record.clone());

    let mut checks: Vec<Value> = Vec::new();
    let mut is_valid = true;
    let signer_public_key_pem = value
        .get("signer_public_key_pem")
        .or_else(|| value.get("signature_info").and_then(|s| s.get("signer_public_key_pem")))
        .and_then(|v| v.as_str())
        .map(|s| s.to_string());

    // Signature check
    if let Some(sig_info) = &record.signature_info {
        let payload = canonical_payload(&norm)?;
        if let Some(pub_pem) = signer_public_key_pem.as_deref() {
            let ok = verify_ecdsa(&payload, &sig_info.signature, pub_pem)?;
            is_valid &= ok;
            checks.push(json!({"check_name": "Signature", "passed": ok}));
        } else {
            is_valid = false;
            checks.push(json!({"check_name": "Signature", "passed": false, "details": "missing public key"}));
        }
    } else {
        is_valid = false;
        checks.push(json!({"check_name": "Signature", "passed": false, "details": "missing"}));
    }

    // Type-specific checks
    match record.dtc_type {
        4 => {
            // Type1
            if let Some(t1) = &norm.type1_profile {
                let has_lines = !t1.mrz_line1.is_empty() && !t1.mrz_line2.is_empty();
                let dg_bytes: Vec<u8> = norm
                    .data_groups
                    .iter()
                    .filter_map(|dg| b64_decode(&dg.data))
                    .flatten()
                    .collect();
                let hash_ok = if !dg_bytes.is_empty() {
                    let mut hasher = Sha256::new();
                    hasher.update(&dg_bytes);
                    hex::encode(hasher.finalize()) == t1.sod_hash
                } else {
                    false
                };
                let ok = has_lines && hash_ok;
                is_valid &= ok;
                checks.push(json!({"check_name": "Type1Profile", "passed": ok}));
            } else {
                is_valid = false;
                checks.push(json!({"check_name": "Type1Profile", "passed": false, "details": "missing profile"}));
            }
        }
        5 => {
            // Type2
            if let Some(t2) = &norm.type2_profile {
                let ok = !t2.chip_auth_public_key.is_empty() && !t2.device_public_key.is_empty();
                is_valid &= ok;
                checks.push(json!({"check_name": "Type2Profile", "passed": ok}));
            } else {
                is_valid = false;
                checks.push(json!({"check_name": "Type2Profile", "passed": false, "details": "missing profile"}));
            }
        }
        6 => {
            // Type3
            if let Some(t3) = &norm.type3_profile {
                let ok = !t3.remote_attestation_report.is_empty() && !t3.device_binding_id.is_empty();
                is_valid &= ok;
                checks.push(json!({"check_name": "Type3Profile", "passed": ok}));
            } else {
                is_valid = false;
                checks.push(json!({"check_name": "Type3Profile", "passed": false, "details": "missing profile"}));
            }
        }
        _ => {}
    }

    // Optional PKI trust chain validation
    let trust_anchors: Vec<String> = value
        .get("trust_anchors_pem")
        .and_then(|v| v.as_array())
        .map(|arr| arr.iter().filter_map(|s| s.as_str().map(|x| x.to_string())).collect())
        .unwrap_or_default();
    let cert_chain: Vec<String> = value
        .get("certificate_chain_pem")
        .and_then(|v| v.as_array())
        .map(|arr| arr.iter().filter_map(|s| s.as_str().map(|x| x.to_string())).collect())
        .unwrap_or_default();
    if let (Some(pub_pem), Some(leaf_pem)) = (signer_public_key_pem.as_deref(), cert_chain.first()) {
        let signer_bytes = public_key_bytes_from_pem(pub_pem)?;
        let leaf_bytes = public_key_bytes_from_cert_pem(leaf_pem)?;
        let ok = signer_bytes == leaf_bytes;
        is_valid &= ok;
        checks.push(json!({"check_name": "SignerKeyMatchesCertificate", "passed": ok}));
    }
    if !trust_anchors.is_empty() && !cert_chain.is_empty() {
        let chain_ok = validate_chain(&trust_anchors, &cert_chain)?;
        is_valid &= chain_ok;
        checks.push(json!({"check_name": "TrustChain", "passed": chain_ok}));
    }

    let resp = json!({
        "is_valid": is_valid,
        "verification_results": checks,
        "dtc_data": record,
        "error_message": if is_valid { "" } else { "Verification failed" },
    });

    serde_json::to_string(&resp).map_err(|e| e.to_string())
}
