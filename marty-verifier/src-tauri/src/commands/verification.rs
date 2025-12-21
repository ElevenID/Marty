//! Credential verification commands

use std::collections::HashMap;

use base64::engine::general_purpose::STANDARD as BASE64_STANDARD;
use base64::Engine;
use marty_secure_storage::TrustAnchorType;
use marty_verification::chip_io::{verify_from_reader, MockPassportReader};
use marty_verification::trust_anchor::CscaRegistry;
use marty_verification::verification::emrtd::{verify_emrtd, SecurityObject};
use serde::{Deserialize, Serialize};
use tauri::State;
use x509_cert::der::Decode;
use x509_cert::Certificate;

use crate::error::{AppError, AppResult};
use crate::state::AppState;

// Re-export storage type
pub use marty_secure_storage::VerificationHistoryEntry;

/// Verification request
#[derive(Debug, Deserialize)]
pub struct VerifyRequest {
    /// Credential type: "mdl", "emrtd", "oid4vp", "sd-jwt"
    pub credential_type: String,
    /// Raw credential data (base64, JWT, or QR content)
    pub credential_data: String,
    /// Whether to use NFC/reader (eMRTD only)
    #[serde(default)]
    pub use_nfc: bool,
    /// Verification policy to apply
    pub policy: Option<VerificationPolicy>,
}

/// Verification policy configuration
#[derive(Debug, Deserialize)]
pub struct VerificationPolicy {
    /// Required claims to verify
    pub required_claims: Vec<String>,
    /// Age threshold for age verification (e.g., 21 for alcohol)
    pub age_threshold: Option<u8>,
    /// Allow expired credentials within grace period
    pub allow_expired_grace: bool,
}

/// Verification result
#[derive(Debug, Serialize)]
pub struct VerificationResult {
    /// Verification ID for tracking
    pub verification_id: String,
    /// Overall verification status
    pub status: VerificationStatus,
    /// Credential type verified
    pub credential_type: String,
    /// Issuer information
    pub issuer: Option<IssuerInfo>,
    /// Disclosed claims (per policy)
    pub disclosed_claims: serde_json::Value,
    /// Trust chain status
    pub trust_chain: TrustChainStatus,
    /// Revocation status
    pub revocation_status: RevocationStatus,
    /// Timestamp of verification
    pub verified_at: String,
    /// Warnings (e.g., offline verification, cached CRL)
    pub warnings: Vec<String>,
    /// eMRTD-specific details (present when credential_type == "emrtd")
    #[serde(skip_serializing_if = "Option::is_none")]
    pub emrtd_details: Option<EmrtdDetails>,
}

/// eMRTD verification details.
#[derive(Debug, Serialize)]
pub struct EmrtdDetails {
    pub dsc_chain_status: String,
    pub sod_signature_status: String,
    pub dg_hash_status: String,
    pub errors: Vec<String>,
}

/// Verification status enum
#[derive(Debug, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum VerificationStatus {
    /// Credential is valid
    Valid,
    /// Credential is invalid
    Invalid,
    /// Credential verification failed
    Failed,
    /// Credential expired
    Expired,
    /// Credential revoked
    Revoked,
    /// Verification pending (offline, queued)
    Pending,
}

/// Issuer information
#[derive(Debug, Serialize)]
pub struct IssuerInfo {
    /// Issuer name
    pub name: Option<String>,
    /// Issuer country/jurisdiction
    pub jurisdiction: Option<String>,
    /// Issuer certificate subject
    pub subject: Option<String>,
}

/// Trust chain verification status
#[derive(Debug, Serialize)]
pub struct TrustChainStatus {
    /// Trust chain is valid
    pub valid: bool,
    /// Chain type: "iaca", "csca", "did", "x509"
    pub chain_type: String,
    /// Trust anchor used
    pub trust_anchor: Option<String>,
    /// Verification was performed offline with cached anchors
    pub offline_verified: bool,
}

/// Revocation status
#[derive(Debug, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum RevocationStatus {
    /// Not revoked
    Valid,
    /// Revoked
    Revoked,
    /// Revocation check failed (offline)
    Unknown,
    /// Using cached revocation data
    CachedValid,
}

/// Verify a credential
#[tauri::command]
pub async fn verify_credential(
    request: VerifyRequest,
    state: State<'_, AppState>,
) -> AppResult<VerificationResult> {
    tracing::info!(
        credential_type = %request.credential_type,
        "Verifying credential"
    );

    // Check if feature is licensed
    state.check_feature(&request.credential_type).await?;

    // Generate verification ID
    let verification_id = uuid::Uuid::new_v4().to_string();

    // Check online status
    let is_online = *state.is_online.read().await;

    let result = if request.credential_type.to_lowercase() == "emrtd" {
        verify_emrtd_payload(&request, &state, is_online).await?
    } else {
        // TODO: extend for other credential types
        placeholder_success(&request, is_online)
    };

    // Store verification event
    state
        .storage
        .store_verification_event(&verification_id, &request.credential_type, &result.status)
        .await?;

    // TODO: Queue for reporting if enabled and reporter is added to AppState

    Ok(result)
}

/// Placeholder response for non-eMRTD types (to be replaced as other types are wired up).
fn placeholder_success(request: &VerifyRequest, is_online: bool) -> VerificationResult {
    VerificationResult {
        verification_id: uuid::Uuid::new_v4().to_string(),
        status: VerificationStatus::Valid,
        credential_type: request.credential_type.clone(),
        issuer: Some(IssuerInfo {
            name: Some("Example Issuer".to_string()),
            jurisdiction: Some("US".to_string()),
            subject: None,
        }),
        disclosed_claims: serde_json::json!({
            "given_name": "John",
            "family_name": "Doe",
            "age_over_21": true
        }),
        trust_chain: TrustChainStatus {
            valid: true,
            chain_type: "iaca".to_string(),
            trust_anchor: Some("US-CA".to_string()),
            offline_verified: !is_online,
        },
        revocation_status: if is_online {
            RevocationStatus::Valid
        } else {
            RevocationStatus::CachedValid
        },
        verified_at: chrono::Utc::now().to_rfc3339(),
        warnings: if is_online {
            vec![]
        } else {
            vec!["Verified offline with cached trust anchors".to_string()]
        },
        emrtd_details: None,
    }
}

#[derive(Debug, Deserialize)]
struct EmrtdPayload {
    /// Base64-encoded EF.SOD
    sod_base64: String,
    /// Map of DG names (e.g., "DG1") to base64-encoded contents
    data_groups: HashMap<String, String>,
    /// Optional country hint (ISO 3166)
    country: Option<String>,
}

async fn verify_emrtd_payload(
    request: &VerifyRequest,
    state: &AppState,
    is_online: bool,
) -> AppResult<VerificationResult> {
    // NFC-only mode with no payload currently not implemented
    if request.use_nfc && request.credential_data.trim().is_empty() {
        return Err(AppError::Verification(
            "NFC read requested but no reader integration is configured yet. Provide an eMRTD payload or disable use_nfc.".to_string(),
        ));
    }

    let payload: EmrtdPayload = serde_json::from_str(&request.credential_data)
        .map_err(|e| AppError::Verification(format!("Invalid eMRTD payload JSON: {}", e)))?;

    let sod_bytes = BASE64_STANDARD
        .decode(payload.sod_base64.as_bytes())
        .map_err(|e| AppError::Verification(format!("Invalid SOD base64: {}", e)))?;

    // Build security object from SOD
    let security_object =
        SecurityObject::from_sod_der(&sod_bytes, payload.country.clone()).map_err(|e| {
            AppError::Verification(format!("Failed to parse SOD for verification: {}", e))
        })?;

    // Decode DGs
    let mut dg_map: HashMap<u8, Vec<u8>> = HashMap::new();
    for (dg_name, b64) in payload.data_groups {
        let num = dg_name
            .trim_start_matches("DG")
            .parse::<u8>()
            .map_err(|_| {
                AppError::Verification(format!("Invalid data group name: {}", dg_name))
            })?;
        let dg_bytes = BASE64_STANDARD
            .decode(b64.as_bytes())
            .map_err(|e| AppError::Verification(format!("Invalid base64 for {}: {}", dg_name, e)))?;
        dg_map.insert(num, dg_bytes);
    }

    // Build CSCA registry from secure storage
    let registry = build_csca_registry(&state).await?;

    // NFC path: route through reader abstraction to exercise chip I/O flow.
    let verification = if request.use_nfc {
        let reader =
            MockPassportReader::new(sod_bytes.clone(), dg_map.clone(), payload.country.clone());
        verify_from_reader(&reader, &registry)
    } else {
        // Build security object from SOD
        let security_object =
            SecurityObject::from_sod_der(&sod_bytes, payload.country.clone()).map_err(|e| {
                AppError::Verification(format!("Failed to parse SOD for verification: {}", e))
            })?;
        verify_emrtd(&security_object, &dg_map, &registry)
    };

    let status = if verification.verified {
        VerificationStatus::Valid
    } else if verification
        .errors
        .iter()
        .any(|e| e.contains("expired") || e.contains("not yet valid"))
    {
        VerificationStatus::Invalid
    } else {
        VerificationStatus::Failed
    };

    let warnings = if is_online {
        Vec::new()
    } else {
        vec!["Verified offline with cached CSCA anchors".to_string()]
    };

    let issuer_subject = security_object
        .signer_certificate
        .certificate
        .tbs_certificate
        .subject
        .to_string();

    let country = security_object
        .signer_certificate
        .country
        .or(verification.country.clone());

    Ok(VerificationResult {
        verification_id: request
            .credential_data
            .get(0..12)
            .map(|s| s.to_string())
            .unwrap_or_else(|| uuid::Uuid::new_v4().to_string()),
        status,
        credential_type: request.credential_type.clone(),
        issuer: Some(IssuerInfo {
            name: Some("Passport Issuer".to_string()),
            jurisdiction: country.clone(),
            subject: Some(issuer_subject),
        }),
        disclosed_claims: serde_json::json!({ "document_type": "passport" }),
        trust_chain: TrustChainStatus {
            valid: verification.dsc_chain_status
                == marty_verification::verification::emrtd::ChainStatus::Valid,
            chain_type: "csca".to_string(),
            trust_anchor: country,
            offline_verified: !is_online,
        },
        revocation_status: RevocationStatus::Unknown,
        verified_at: chrono::Utc::now().to_rfc3339(),
        warnings: if verification.errors.is_empty() {
            warnings
        } else {
            let mut w = warnings;
            w.extend(verification.errors.clone());
            w
        },
        emrtd_details: Some(EmrtdDetails {
            dsc_chain_status: format!("{:?}", verification.dsc_chain_status),
            sod_signature_status: format!("{:?}", verification.sod_signature_status),
            dg_hash_status: format!("{:?}", verification.dg_hash_status),
            errors: verification.errors,
        }),
    })
}

async fn build_csca_registry(state: &AppState) -> AppResult<CscaRegistry> {
    let anchors = state
        .storage
        .get_trust_anchors(TrustAnchorType::Csca, None)
        .await?;

    let mut registry = CscaRegistry::new();
    for anchor in anchors {
        let cert = Certificate::from_der(&anchor.certificate_der).map_err(|e| {
            AppError::Verification(format!(
                "Failed to parse CSCA certificate {}: {}",
                anchor.id, e
            ))
        })?;
        registry
            .add_country_csca(&anchor.jurisdiction, cert)
            .map_err(|e| AppError::Verification(e.to_string()))?;
    }

    Ok(registry)
}

/// Get verification history
#[tauri::command]
pub async fn get_verification_history(
    limit: Option<usize>,
    state: State<'_, AppState>,
) -> AppResult<Vec<VerificationHistoryEntry>> {
    let limit = limit.unwrap_or(100);
    let history = state.storage.get_verification_history(limit).await?;
    Ok(history)
}
