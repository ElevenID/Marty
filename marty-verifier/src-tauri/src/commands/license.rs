//! License management commands

use serde::{Deserialize, Serialize};
use tauri::State;

use crate::error::AppResult;
use crate::state::AppState;

/// License status response
#[derive(Debug, Serialize, Deserialize)]
pub struct LicenseStatus {
    /// License is valid
    pub valid: bool,
    /// Organization ID
    pub org_id: Option<String>,
    /// License expiration date (ISO 8601)
    pub expires_at: Option<String>,
    /// Days until expiration
    pub days_until_expiry: Option<i64>,
    /// Licensed features
    pub features: Vec<String>,
    /// Hardware binding status
    pub hardware_bound: bool,
    /// Grace period active (offline renewal needed)
    pub grace_period_active: bool,
    /// Grace period days remaining
    pub grace_period_days: Option<i64>,
    /// Deployment mode
    pub deployment_mode: Option<String>,
    /// Maximum daily verifications
    pub max_daily_verifications: Option<u32>,
    /// Verifications performed today
    pub verifications_today: u32,
}

/// Validate a license file
#[tauri::command]
pub async fn validate_license(
    license_data: String,
    state: State<'_, AppState>,
) -> AppResult<LicenseStatus> {
    tracing::info!("Validating license");

    let result = state.license.validate_license(&license_data).await?;

    Ok(LicenseStatus {
        valid: result.valid,
        org_id: result.org_id,
        expires_at: result.expires_at.map(|dt| dt.to_rfc3339()),
        days_until_expiry: result.days_until_expiry,
        features: result.features,
        hardware_bound: result.hardware_bound,
        grace_period_active: result.grace_period_active,
        grace_period_days: result.grace_period_days,
        deployment_mode: result.deployment_mode,
        max_daily_verifications: result.max_daily_verifications,
        verifications_today: result.verifications_today,
    })
}

/// Get current license status
#[tauri::command]
pub async fn get_license_status(state: State<'_, AppState>) -> AppResult<LicenseStatus> {
    let status = state.license.get_status().await?;

    Ok(LicenseStatus {
        valid: status.valid,
        org_id: status.org_id,
        expires_at: status.expires_at.map(|dt| dt.to_rfc3339()),
        days_until_expiry: status.days_until_expiry,
        features: status.features,
        hardware_bound: status.hardware_bound,
        grace_period_active: status.grace_period_active,
        grace_period_days: status.grace_period_days,
        deployment_mode: status.deployment_mode,
        max_daily_verifications: status.max_daily_verifications,
        verifications_today: status.verifications_today,
    })
}

/// Get list of licensed features
#[tauri::command]
pub async fn get_licensed_features(state: State<'_, AppState>) -> AppResult<Vec<String>> {
    let status = state.license.get_status().await?;
    Ok(status.features)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_license_status_serialization() {
        let status = LicenseStatus {
            valid: true,
            org_id: Some("test-org".to_string()),
            expires_at: Some("2025-12-31T00:00:00Z".to_string()),
            days_until_expiry: Some(30),
            features: vec!["mdl".to_string(), "oid4vp".to_string()],
            hardware_bound: false,
            grace_period_active: false,
            grace_period_days: None,
            deployment_mode: Some("production".to_string()),
            max_daily_verifications: Some(1000),
            verifications_today: 50,
        };

        let json = serde_json::to_string(&status).unwrap();
        let deserialized: LicenseStatus = serde_json::from_str(&json).unwrap();

        assert!(deserialized.valid);
        assert_eq!(deserialized.org_id.unwrap(), "test-org");
        assert_eq!(deserialized.features.len(), 2);
        assert_eq!(deserialized.verifications_today, 50);
    }

    #[test]
    fn test_license_status_invalid() {
        let status = LicenseStatus {
            valid: false,
            org_id: None,
            expires_at: None,
            days_until_expiry: None,
            features: vec![],
            hardware_bound: false,
            grace_period_active: false,
            grace_period_days: None,
            deployment_mode: None,
            max_daily_verifications: None,
            verifications_today: 0,
        };

        assert!(!status.valid);
        assert!(status.features.is_empty());
    }

    #[test]
    fn test_license_status_grace_period() {
        let status = LicenseStatus {
            valid: true,
            org_id: Some("test-org".to_string()),
            expires_at: Some("2025-01-01T00:00:00Z".to_string()),
            days_until_expiry: Some(-5),
            features: vec!["mdl".to_string()],
            hardware_bound: true,
            grace_period_active: true,
            grace_period_days: Some(7),
            deployment_mode: Some("production".to_string()),
            max_daily_verifications: Some(500),
            verifications_today: 100,
        };

        assert!(status.valid);
        assert!(status.grace_period_active);
        assert_eq!(status.grace_period_days.unwrap(), 7);
        assert!(status.hardware_bound);
    }
}
