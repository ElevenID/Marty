//! Credential verification commands

use serde::{Deserialize, Serialize};
use tauri::State;

use crate::error::AppResult;
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

    // TODO: Implement actual verification logic
    // For now, return a placeholder result
    let result = VerificationResult {
        verification_id: verification_id.clone(),
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
    };

    // Store verification event
    state
        .storage
        .store_verification_event(&verification_id, &request.credential_type, &result.status)
        .await?;

    // TODO: Queue for reporting if enabled and reporter is added to AppState

    Ok(result)
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
