//! Credential verification commands

use std::collections::HashMap;

use base64::engine::general_purpose::STANDARD as BASE64_STANDARD;
use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use base64::Engine;
use chrono::{DateTime, Duration, Utc};
use marty_secure_storage::TrustAnchorType;
use marty_verification::chip_io::{verify_from_reader, MockPassportReader};
use marty_verification::trust_anchor::CscaRegistry;
use marty_verification::verification::emrtd::{verify_emrtd, SecurityObject};
use ring::hmac;
use serde::{Deserialize, Serialize};
use tauri::State;
use uuid::Uuid;
use x509_cert::der::Decode;
use x509_cert::Certificate;

use crate::config::{LivenessRetentionConfig, PadProviderConfig, PadProviderType};
use crate::error::{AppError, AppResult};
use crate::state::{AppState, StoredLivenessChallenge};

// Re-export storage type
pub use marty_secure_storage::VerificationHistoryEntry;

const DEFAULT_CHALLENGE_TTL_SECS: i64 = 60;
const MAX_CLOCK_SKEW_SECS: i64 = 5;
const DEFAULT_STEP_TIME_LIMIT_MS: i32 = 5000;

#[derive(Debug, Clone, Copy, Serialize, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum LivenessMode {
    #[default]
    Unknown,
    OnDevice,
    Network,
}

impl LivenessMode {
    fn as_str(&self) -> &'static str {
        match self {
            LivenessMode::Unknown => "unknown",
            LivenessMode::OnDevice => "on_device",
            LivenessMode::Network => "network",
        }
    }
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum LivenessStepType {
    #[default]
    Unknown,
    HeadPose,
    Blink,
    Phrase,
}

impl LivenessStepType {
    fn as_str(&self) -> &'static str {
        match self {
            LivenessStepType::Unknown => "unknown",
            LivenessStepType::HeadPose => "head_pose",
            LivenessStepType::Blink => "blink",
            LivenessStepType::Phrase => "phrase",
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LivenessStep {
    pub step_id: String,
    pub step_type: LivenessStepType,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub prompt: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub pose_direction: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub time_limit_ms: Option<i32>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LivenessChallenge {
    pub challenge_id: String,
    pub nonce: String,
    pub session_id: String,
    pub steps: Vec<LivenessStep>,
    pub issued_at: String,
    pub expires_at: String,
    pub signature: String,
    pub preferred_mode: LivenessMode,
    pub allow_network_fallback: bool,
    pub accessibility_mode: bool,
}

#[derive(Debug, Deserialize)]
pub struct IssueLivenessChallengeRequest {
    #[serde(default)]
    pub session_id: Option<String>,
    #[serde(default)]
    pub preferred_mode: Option<LivenessMode>,
    #[serde(default)]
    pub allow_network_fallback: Option<bool>,
    #[serde(default)]
    pub accessibility_mode: Option<bool>,
    #[serde(default)]
    pub ttl_seconds: Option<i64>,
}

#[derive(Debug, Serialize)]
pub struct IssueLivenessChallengeResponse {
    pub challenge: LivenessChallenge,
}

#[cfg(feature = "biometrics")]
impl From<LivenessChallenge> for marty_biometrics::LivenessChallenge {
    fn from(value: LivenessChallenge) -> Self {
        marty_biometrics::LivenessChallenge {
            challenge_id: value.challenge_id,
            nonce: value.nonce,
            session_id: value.session_id,
            steps: value.steps.into_iter().map(|s| s.into()).collect(),
            issued_at: value.issued_at,
            expires_at: value.expires_at,
            signature: value.signature,
            preferred_mode: Some(value.preferred_mode.into()),
            allow_network_fallback: value.allow_network_fallback,
            accessibility_mode: value.accessibility_mode,
        }
    }
}

#[cfg(feature = "biometrics")]
impl From<LivenessStep> for marty_biometrics::LivenessStep {
    fn from(step: LivenessStep) -> Self {
        marty_biometrics::LivenessStep {
            step_id: step.step_id,
            step_type: step.step_type.into(),
            prompt: step.prompt,
            pose_direction: step.pose_direction,
            time_limit_ms: step.time_limit_ms.map(|v| v as u32),
        }
    }
}

#[cfg(feature = "biometrics")]
impl From<LivenessMode> for marty_biometrics::LivenessMode {
    fn from(mode: LivenessMode) -> Self {
        match mode {
            LivenessMode::OnDevice => marty_biometrics::LivenessMode::OnDevice,
            LivenessMode::Network => marty_biometrics::LivenessMode::Network,
            LivenessMode::Unknown => marty_biometrics::LivenessMode::Unknown,
        }
    }
}

#[cfg(feature = "biometrics")]
impl From<LivenessStepType> for marty_biometrics::LivenessStepType {
    fn from(step: LivenessStepType) -> Self {
        match step {
            LivenessStepType::HeadPose => marty_biometrics::LivenessStepType::HeadPose,
            LivenessStepType::Blink => marty_biometrics::LivenessStepType::Blink,
            LivenessStepType::Phrase => marty_biometrics::LivenessStepType::Phrase,
            LivenessStepType::Unknown => marty_biometrics::LivenessStepType::Unknown,
        }
    }
}

/// Issue a signed liveness challenge (nonce + steps) for the UI to present.
#[tauri::command]
pub async fn issue_liveness_challenge(
    request: IssueLivenessChallengeRequest,
    state: State<'_, AppState>,
) -> AppResult<IssueLivenessChallengeResponse> {
    let accessibility_mode = request.accessibility_mode.unwrap_or(false);
    let ttl_secs = request
        .ttl_seconds
        .unwrap_or(DEFAULT_CHALLENGE_TTL_SECS)
        .clamp(15, 120);

    let issued_at = Utc::now();
    let expires_at = issued_at + Duration::seconds(ttl_secs);

    let preferred_mode = request.preferred_mode.unwrap_or(LivenessMode::OnDevice);

    let challenge = LivenessChallenge {
        challenge_id: Uuid::new_v4().to_string(),
        nonce: Uuid::new_v4().to_string(),
        session_id: request
            .session_id
            .unwrap_or_else(|| Uuid::new_v4().to_string()),
        steps: build_liveness_steps(accessibility_mode),
        issued_at: issued_at.to_rfc3339(),
        expires_at: expires_at.to_rfc3339(),
        signature: String::new(),
        preferred_mode,
        allow_network_fallback: request.allow_network_fallback.unwrap_or(true),
        accessibility_mode,
    };

    let signature = sign_challenge(&challenge, state.liveness_secret.as_slice());
    let mut signed_challenge = challenge;
    signed_challenge.signature = signature.clone();

    state
        .record_liveness_challenge(StoredLivenessChallenge {
            challenge_id: signed_challenge.challenge_id.clone(),
            nonce: signed_challenge.nonce.clone(),
            session_id: signed_challenge.session_id.clone(),
            issued_at,
            expires_at,
            used: false,
        })
        .await;

    Ok(IssueLivenessChallengeResponse {
        challenge: signed_challenge,
    })
}

fn build_liveness_steps(accessibility_mode: bool) -> Vec<LivenessStep> {
    let pose_options = ["left", "right", "up", "down"];
    let phrase_options = [
        "secure systems stay safe",
        "trust but verify always",
        "liveness check in progress",
        "identity matters today",
        "security starts with you",
    ];

    let pick_pose = pose_options[(Uuid::new_v4().as_u128() % pose_options.len() as u128) as usize];
    let pick_phrase =
        phrase_options[(Uuid::new_v4().as_u128() % phrase_options.len() as u128) as usize];

    let mut steps = vec![
        LivenessStep {
            step_id: Uuid::new_v4().to_string(),
            step_type: LivenessStepType::HeadPose,
            prompt: Some(format!("Turn your head {}", pick_pose)),
            pose_direction: Some(pick_pose.to_string()),
            time_limit_ms: Some(DEFAULT_STEP_TIME_LIMIT_MS),
        },
        LivenessStep {
            step_id: Uuid::new_v4().to_string(),
            step_type: LivenessStepType::Blink,
            prompt: Some("Blink twice".to_string()),
            pose_direction: None,
            time_limit_ms: Some(DEFAULT_STEP_TIME_LIMIT_MS),
        },
    ];

    if !accessibility_mode {
        steps.push(LivenessStep {
            step_id: Uuid::new_v4().to_string(),
            step_type: LivenessStepType::Phrase,
            prompt: Some(pick_phrase.to_string()),
            pose_direction: None,
            time_limit_ms: Some(DEFAULT_STEP_TIME_LIMIT_MS),
        });
    }

    steps
}

fn signing_payload(challenge: &LivenessChallenge) -> String {
    let step_parts: Vec<String> = challenge
        .steps
        .iter()
        .map(|step| {
            format!(
                "{}:{}:{}:{}:{}",
                step.step_id,
                step.step_type.as_str(),
                step.pose_direction.as_deref().unwrap_or(""),
                step.prompt.as_deref().unwrap_or(""),
                step.time_limit_ms.unwrap_or(DEFAULT_STEP_TIME_LIMIT_MS)
            )
        })
        .collect();

    format!(
        "{}|{}|{}|{}|{}|{}|{}|{}|{}",
        challenge.challenge_id,
        challenge.nonce,
        challenge.session_id,
        challenge.issued_at,
        challenge.expires_at,
        challenge.preferred_mode.as_str(),
        challenge.allow_network_fallback,
        challenge.accessibility_mode,
        step_parts.join(";")
    )
}

fn sign_challenge(challenge: &LivenessChallenge, secret: &[u8]) -> String {
    let key = hmac::Key::new(hmac::HMAC_SHA256, secret);
    let payload = signing_payload(challenge);
    let tag = hmac::sign(&key, payload.as_bytes());
    URL_SAFE_NO_PAD.encode(tag.as_ref())
}

pub(crate) fn verify_challenge_signature(challenge: &LivenessChallenge, secret: &[u8]) -> bool {
    let expected = sign_challenge(challenge, secret);
    expected == challenge.signature
}

pub(crate) async fn validate_liveness_challenge(
    challenge: &LivenessChallenge,
    expected_session_id: Option<&str>,
    state: &AppState,
) -> AppResult<()> {
    if !verify_challenge_signature(challenge, state.liveness_secret.as_slice()) {
        return Err(AppError::Verification(
            "Invalid liveness challenge signature".to_string(),
        ));
    }

    let issued_at = DateTime::parse_from_rfc3339(&challenge.issued_at)
        .map_err(|e| AppError::Verification(format!("Invalid issued_at: {}", e)))?
        .with_timezone(&Utc);
    let expires_at = DateTime::parse_from_rfc3339(&challenge.expires_at)
        .map_err(|e| AppError::Verification(format!("Invalid expires_at: {}", e)))?
        .with_timezone(&Utc);

    let now = Utc::now();
    if now > expires_at {
        return Err(AppError::Verification(
            "Liveness challenge expired".to_string(),
        ));
    }

    if now + Duration::seconds(MAX_CLOCK_SKEW_SECS) < issued_at {
        return Err(AppError::Verification(
            "Liveness capture started before challenge issuance".to_string(),
        ));
    }

    if expires_at < issued_at {
        return Err(AppError::Verification(
            "Liveness challenge expiry precedes issuance".to_string(),
        ));
    }

    if let Some(expected_session) = expected_session_id {
        if expected_session != challenge.session_id {
            return Err(AppError::Verification(
                "Session mismatch for liveness challenge".to_string(),
            ));
        }
    }

    // Replay protection: challenge must be issued by this instance and unused
    let recorded = state
        .consume_liveness_challenge(&challenge.challenge_id)
        .await
        .ok_or_else(|| {
            AppError::Verification("Liveness challenge not recognized or already used".to_string())
        })?;

    if recorded.nonce != challenge.nonce || recorded.session_id != challenge.session_id {
        return Err(AppError::Verification(
            "Liveness challenge metadata mismatch".to_string(),
        ));
    }

    if recorded.expires_at < now {
        return Err(AppError::Verification(
            "Liveness challenge expired in storage".to_string(),
        ));
    }

    Ok(())
}

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
    /// Optional liveness challenge to validate (nonce + signed steps)
    #[serde(default)]
    pub liveness_challenge: Option<LivenessChallenge>,
    /// Require liveness validation for this verification
    #[serde(default)]
    pub require_liveness: bool,
    /// Preferred liveness mode (on-device vs network)
    #[serde(default)]
    pub preferred_liveness_mode: Option<LivenessMode>,
    /// Allow network fallback if preferred mode unavailable
    #[serde(default)]
    pub allow_network_fallback: Option<bool>,
    /// Accessibility adjustments (pose/blink only)
    #[serde(default)]
    pub accessibility_mode: Option<bool>,
    /// Request retention of a short audit clip
    #[serde(default)]
    pub retain_audit_clip: Option<bool>,
    /// TTL for audit clip retention (seconds)
    #[serde(default)]
    pub audit_clip_ttl_seconds: Option<u32>,
    /// Session identifier to bind challenge to caller
    #[serde(default)]
    pub session_id: Option<String>,
    /// Perform face match (optional)
    #[serde(default)]
    pub perform_face_match: bool,
    /// Reference image for face match (base64)
    #[serde(default)]
    pub reference_image: Option<String>,
    /// Probe image for face match (base64)
    #[serde(default)]
    pub probe_image: Option<String>,
    /// Optional threshold for face match
    #[serde(default)]
    pub face_threshold: Option<f32>,
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
    /// Liveness evaluation (if performed)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub liveness: Option<LivenessResultPayload>,
    /// Face match summary (if performed)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub face_match: Option<FaceMatchPayload>,
}

/// eMRTD verification details.
#[derive(Debug, Serialize)]
pub struct EmrtdDetails {
    pub dsc_chain_status: String,
    pub sod_signature_status: String,
    pub dg_hash_status: String,
    pub errors: Vec<String>,
}

/// Liveness result payload
#[derive(Debug, Serialize, Clone)]
pub struct LivenessResultPayload {
    pub passed: bool,
    pub fused_score: f32,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub mode_used: Option<String>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub errors: Vec<String>,
}

/// Face match payload (placeholder)
#[derive(Debug, Serialize, Clone)]
pub struct FaceMatchPayload {
    pub verified: bool,
    pub similarity: f32,
    pub threshold: f32,
    pub provider: String,
}

async fn run_face_match(request: &VerifyRequest) -> AppResult<FaceMatchPayload> {
    let threshold = request.face_threshold.unwrap_or(0.75);

    #[cfg(feature = "biometrics")]
    {
        use marty_biometrics::{BiometricProvider, FaceVerificationRequest};

        let reference_image = request.reference_image.clone().unwrap_or_default();
        let probe_image = request.probe_image.clone().unwrap_or_default();
        if reference_image.is_empty() || probe_image.is_empty() {
            return Err(AppError::Verification(
                "Face match requested but reference/probe images missing".to_string(),
            ));
        }

        let provider = BiometricProvider::mock();
        let result = provider
            .verify(FaceVerificationRequest {
                reference_image,
                probe_image,
                threshold: Some(threshold),
                liveness_challenge: None,
                preferred_liveness_mode: None,
                allow_network_fallback: false,
                accessibility_mode: false,
                retain_audit_clip: false,
                audit_clip_ttl_seconds: None,
            })
            .await
            .map_err(|e| AppError::Verification(e.to_string()))?;

        return Ok(FaceMatchPayload {
            verified: result.verified,
            similarity: result.similarity,
            threshold: result.threshold,
            provider: result.provider,
        });
    }

    #[cfg(not(feature = "biometrics"))]
    {
        // Placeholder when biometrics feature is disabled
        Ok(FaceMatchPayload {
            verified: true,
            similarity: 0.9,
            threshold,
            provider: "placeholder".to_string(),
        })
    }
}

async fn evaluate_pad(
    challenge: &LivenessChallenge,
    pad_config: &PadProviderConfig,
) -> AppResult<LivenessResultPayload> {
    match pad_config.provider {
        PadProviderType::Mock => Ok(LivenessResultPayload {
            passed: true,
            fused_score: 0.85,
            mode_used: Some(challenge.preferred_mode.as_str().to_string()),
            errors: vec!["PAD provider set to mock".to_string()],
        }),
        PadProviderType::SelfHosted => {
            if pad_config.endpoint.is_none() {
                return Err(AppError::Verification(
                    "PAD self-hosted endpoint not configured".to_string(),
                ));
            }
            // TODO: Implement HTTP call to self-hosted PAD endpoint with media + challenge metadata
            Ok(LivenessResultPayload {
                passed: true,
                fused_score: 0.82,
                mode_used: Some("self_hosted".to_string()),
                errors: vec!["Self-hosted PAD placeholder; implement HTTP adapter".to_string()],
            })
        }
        PadProviderType::Commercial => {
            // TODO: Implement commercial PAD adapter (e.g., Rekognition/iProov) using endpoint/api_key
            Ok(LivenessResultPayload {
                passed: true,
                fused_score: 0.88,
                mode_used: Some("commercial".to_string()),
                errors: vec!["Commercial PAD placeholder; implement API client".to_string()],
            })
        }
    }
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

    let mut liveness_result: Option<LivenessResultPayload> = None;
    if request.require_liveness || request.liveness_challenge.is_some() {
        let challenge = request.liveness_challenge.as_ref().ok_or_else(|| {
            AppError::Verification(
                "Liveness challenge required when liveness detection is requested".to_string(),
            )
        })?;

        validate_liveness_challenge(challenge, request.session_id.as_deref(), state.inner())
            .await?;

        tracing::info!(
            liveness_challenge_id = %challenge.challenge_id,
            session_id = %challenge.session_id,
            preferred_mode = %challenge.preferred_mode.as_str(),
            allow_network_fallback = challenge.allow_network_fallback,
            accessibility_mode = challenge.accessibility_mode,
            "Liveness challenge validated"
        );

        let pad_config = state.config.read().await.pad_config.clone();
        liveness_result = Some(
            evaluate_pad(challenge, &pad_config)
                .await
                .unwrap_or_else(|e| LivenessResultPayload {
                    passed: false,
                    fused_score: 0.0,
                    mode_used: Some(challenge.preferred_mode.as_str().to_string()),
                    errors: vec![format!("PAD unavailable: {}", e.to_string())],
                }),
        );
    }

    // Clamp audit clip TTL based on config
    let (audit_clip_ttl, liveness_retention_cfg) = {
        let cfg = state.config.read().await;
        let lr: LivenessRetentionConfig = cfg.liveness_retention.clone();
        let requested = request
            .audit_clip_ttl_seconds
            .unwrap_or(lr.default_audit_clip_ttl_seconds);
        (requested.min(lr.max_audit_clip_ttl_seconds), lr)
    };

    tracing::debug!(
        retain_audit_clip = request.retain_audit_clip,
        requested_ttl = request.audit_clip_ttl_seconds,
        applied_ttl = audit_clip_ttl,
        encrypt_temp_media = liveness_retention_cfg.encrypt_temp_media,
        "Liveness retention parameters applied"
    );

    // Generate verification ID
    let verification_id = uuid::Uuid::new_v4().to_string();

    // Check online status
    let is_online = *state.is_online.read().await;

    let mut result = if request.credential_type.to_lowercase() == "emrtd" {
        verify_emrtd_payload(&request, &state, is_online).await?
    } else {
        // TODO: extend for other credential types
        placeholder_success(&request, is_online)
    };

    // Face match (placeholder/mock)
    if request.perform_face_match {
        match run_face_match(&request).await {
            Ok(payload) => {
                if !payload.verified {
                    result.status = VerificationStatus::Invalid;
                    result
                        .warnings
                        .push("Face match failed (placeholder)".to_string());
                }
                result.face_match = Some(payload);
            }
            Err(e) => {
                result
                    .warnings
                    .push(format!("Face match unavailable: {}", e.to_string()));
            }
        }
    }

    // Attach liveness placeholder if evaluated
    if liveness_result.is_some() {
        if liveness_result
            .as_ref()
            .map(|lr| !lr.passed)
            .unwrap_or(false)
        {
            result.status = VerificationStatus::Invalid;
        }
        result.liveness = liveness_result;
        result.warnings.push(
            "Liveness evaluated via PAD adapter; replace mock when provider is ready".to_string(),
        );
    }

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
        liveness: None,
        face_match: None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample_challenge() -> LivenessChallenge {
        LivenessChallenge {
            challenge_id: "challenge-1".to_string(),
            nonce: "nonce-1".to_string(),
            session_id: "session-1".to_string(),
            steps: vec![LivenessStep {
                step_id: "step-1".to_string(),
                step_type: LivenessStepType::HeadPose,
                prompt: Some("Turn left".to_string()),
                pose_direction: Some("left".to_string()),
                time_limit_ms: Some(5000),
            }],
            issued_at: Utc::now().to_rfc3339(),
            expires_at: (Utc::now() + Duration::seconds(30)).to_rfc3339(),
            signature: String::new(),
            preferred_mode: LivenessMode::OnDevice,
            allow_network_fallback: true,
            accessibility_mode: false,
        }
    }

    #[test]
    fn sign_and_verify_round_trip() {
        let secret = b"secret";
        let mut challenge = sample_challenge();
        challenge.signature = sign_challenge(&challenge, secret);

        assert!(verify_challenge_signature(&challenge, secret));
    }

    #[test]
    fn tampered_challenge_fails_signature() {
        let secret = b"secret";
        let mut challenge = sample_challenge();
        challenge.signature = sign_challenge(&challenge, secret);

        // Tamper with nonce
        let mut tampered = challenge.clone();
        tampered.nonce = "wrong".to_string();

        assert!(!verify_challenge_signature(&tampered, secret));
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
    let security_object = SecurityObject::from_sod_der(&sod_bytes, payload.country.clone())
        .map_err(|e| {
            AppError::Verification(format!("Failed to parse SOD for verification: {}", e))
        })?;

    // Decode DGs
    let mut dg_map: HashMap<u8, Vec<u8>> = HashMap::new();
    for (dg_name, b64) in payload.data_groups {
        let num = dg_name
            .trim_start_matches("DG")
            .parse::<u8>()
            .map_err(|_| AppError::Verification(format!("Invalid data group name: {}", dg_name)))?;
        let dg_bytes = BASE64_STANDARD.decode(b64.as_bytes()).map_err(|e| {
            AppError::Verification(format!("Invalid base64 for {}: {}", dg_name, e))
        })?;
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
        let security_object = SecurityObject::from_sod_der(&sod_bytes, payload.country.clone())
            .map_err(|e| {
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
