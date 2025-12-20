//! Marty Biometrics
//!
//! Biometric verification for the Marty Verifier application.
//! Supports facial verification with pluggable provider architecture.

mod error;
mod provider;
mod traits;
mod types;

pub use error::BiometricError;
pub use provider::BiometricProvider;
pub use traits::FaceVerifier;
pub use types::*;
