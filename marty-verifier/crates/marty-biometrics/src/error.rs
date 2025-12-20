//! Biometric error types

use thiserror::Error;

#[derive(Error, Debug)]
pub enum BiometricError {
    #[error("Face not detected in image")]
    FaceNotDetected,

    #[error("Multiple faces detected")]
    MultipleFacesDetected,

    #[error("Image quality too low: {0}")]
    LowQuality(String),

    #[error("Verification failed: similarity {similarity:.2} below threshold {threshold:.2}")]
    VerificationFailed { similarity: f32, threshold: f32 },

    #[error("Provider not available: {0}")]
    ProviderUnavailable(String),

    #[error("Provider error: {0}")]
    ProviderError(String),

    #[error("Image processing error: {0}")]
    ImageProcessing(String),

    #[error("Template extraction failed: {0}")]
    TemplateExtraction(String),

    #[error("Configuration error: {0}")]
    Configuration(String),
}

impl serde::Serialize for BiometricError {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: serde::Serializer,
    {
        serializer.serialize_str(&self.to_string())
    }
}
