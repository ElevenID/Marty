//! Biometric types

use serde::{Deserialize, Serialize};

/// Face verification request
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FaceVerificationRequest {
    /// Reference image (from credential, base64 encoded)
    pub reference_image: String,
    /// Probe image (live capture, base64 encoded)
    pub probe_image: String,
    /// Minimum similarity threshold (0.0 - 1.0)
    pub threshold: Option<f32>,
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
