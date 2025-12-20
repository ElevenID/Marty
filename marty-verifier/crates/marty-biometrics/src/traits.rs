//! Face verification trait

use crate::error::BiometricError;
use crate::types::*;

/// Face verification provider trait
#[allow(async_fn_in_trait)]
pub trait FaceVerifier: Send + Sync {
    /// Get provider capabilities
    fn capabilities(&self) -> ProviderCapabilities;

    /// Verify that probe image matches reference image
    async fn verify(
        &self,
        request: FaceVerificationRequest,
    ) -> Result<FaceVerificationResult, BiometricError>;

    /// Assess image quality for face verification
    async fn assess_quality(&self, image: &str) -> Result<FaceQualityAssessment, BiometricError>;

    /// Extract face template for offline matching
    async fn extract_template(&self, image: &str) -> Result<FaceTemplate, BiometricError>;

    /// Compare two templates (for offline matching)
    async fn compare_templates(
        &self,
        reference: &FaceTemplate,
        probe: &FaceTemplate,
    ) -> Result<f32, BiometricError>;
}
