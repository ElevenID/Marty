//! Biometric types

use serde::{Deserialize, Serialize};

/// Face verification request
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct FaceVerificationRequest {
    /// Reference image (from credential, base64 encoded)
    pub reference_image: String,
    /// Probe image (live capture, base64 encoded)
    pub probe_image: String,
    /// Minimum similarity threshold (0.0 - 1.0)
    pub threshold: Option<f32>,
    /// Optional liveness challenge metadata (nonce, steps, signature)
    #[serde(default)]
    pub liveness_challenge: Option<LivenessChallenge>,
    /// Preferred liveness mode (on-device vs network)
    #[serde(default)]
    pub preferred_liveness_mode: Option<LivenessMode>,
    /// Allow fallback to alternate mode if preferred mode unavailable
    #[serde(default)]
    pub allow_network_fallback: bool,
    /// Enable accessibility adjustments (e.g., pose-only challenges)
    #[serde(default)]
    pub accessibility_mode: bool,
    /// Request retention of a short audit clip
    #[serde(default)]
    pub retain_audit_clip: bool,
    /// Optional TTL for audit clip retention (seconds)
    #[serde(default)]
    pub audit_clip_ttl_seconds: Option<u32>,
}

/// Face verification result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FaceVerificationResult {
    /// Verification passed
    pub verified: bool,
    /// Similarity score (0.0 - 1.0)
    pub similarity: f32,
    /// Threshold used
    pub threshold: f32,
    /// Reference face quality score (0.0 - 1.0)
    pub reference_quality: Option<f32>,
    /// Probe face quality score (0.0 - 1.0)
    pub probe_quality: Option<f32>,
    /// Processing time in milliseconds
    pub processing_time_ms: u64,
    /// Provider used
    pub provider: String,
    /// Liveness decision and component scores (if evaluated)
    pub liveness: Option<LivenessResult>,
}

/// Face quality assessment
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FaceQualityAssessment {
    /// Overall quality score (0.0 - 1.0)
    pub overall_score: f32,
    /// Face detected
    pub face_detected: bool,
    /// Number of faces detected
    pub face_count: u32,
    /// Face position (normalized bounding box)
    pub face_bounds: Option<FaceBounds>,
    /// Individual quality factors
    pub factors: FaceQualityFactors,
}

/// Face bounding box (normalized 0.0 - 1.0)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FaceBounds {
    pub x: f32,
    pub y: f32,
    pub width: f32,
    pub height: f32,
}

/// Face quality factors
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FaceQualityFactors {
    /// Sharpness/blur (0.0 - 1.0)
    pub sharpness: f32,
    /// Brightness (0.0 - 1.0, 0.5 = ideal)
    pub brightness: f32,
    /// Contrast (0.0 - 1.0)
    pub contrast: f32,
    /// Face size relative to image (0.0 - 1.0)
    pub face_size: f32,
    /// Head pose quality (0.0 - 1.0, 1.0 = frontal)
    pub pose: f32,
}

/// Face template (for offline matching)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FaceTemplate {
    /// Template data (provider-specific, base64 encoded)
    pub data: String,
    /// Template version/format
    pub version: String,
    /// Provider that created the template
    pub provider: String,
    /// Quality score of the source image
    pub quality_score: f32,
}

/// Biometric provider capabilities
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProviderCapabilities {
    /// Provider name
    pub name: String,
    /// Provider version
    pub version: String,
    /// Supports 1:1 verification
    pub supports_verification: bool,
    /// Supports quality assessment
    pub supports_quality: bool,
    /// Supports template extraction
    pub supports_templates: bool,
    /// Supports liveness detection
    pub supports_liveness: bool,
    /// Works offline
    pub offline_capable: bool,
}

/// Supported liveness execution modes
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum LivenessMode {
    Unknown,
    OnDevice,
    Network,
}

/// Component scores for liveness
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LivenessScores {
    pub pad_score: f32,
    pub pose_score: f32,
    pub speech_score: f32,
    pub voice_spoof_score: f32,
    pub av_sync_score: f32,
}

/// Thresholds applied to each component and fused decision
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LivenessThresholds {
    pub min_pad_score: f32,
    pub min_pose_score: f32,
    pub min_speech_score: f32,
    pub min_voice_spoof_score: f32,
    pub min_av_sync_score: f32,
    pub fused_threshold: f32,
}

/// Result from a liveness evaluation
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LivenessResult {
    pub passed: bool,
    pub fused_score: f32,
    pub scores: Option<LivenessScores>,
    pub thresholds: Option<LivenessThresholds>,
    pub mode_used: Option<LivenessMode>,
    pub errors: Vec<String>,
    pub decision: Option<String>,
    pub audit_clip_ttl_seconds: Option<u32>,
}

/// Types of liveness challenge steps
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum LivenessStepType {
    Unknown,
    HeadPose,
    Blink,
    Phrase,
}

/// Individual liveness step definition
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LivenessStep {
    pub step_id: String,
    pub step_type: LivenessStepType,
    pub prompt: Option<String>,
    pub pose_direction: Option<String>,
    pub time_limit_ms: Option<u32>,
}

/// Signed liveness challenge metadata passed from the caller
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LivenessChallenge {
    pub challenge_id: String,
    pub nonce: String,
    pub session_id: String,
    pub steps: Vec<LivenessStep>,
    pub issued_at: String,
    pub expires_at: String,
    pub signature: String,
    pub preferred_mode: Option<LivenessMode>,
    pub allow_network_fallback: bool,
    pub accessibility_mode: bool,
}
