//! Application state management

use std::sync::Arc;
use tokio::sync::RwLock;

use marty_license::LicenseManager;
use marty_secure_storage::SecureStorage;
use marty_sync::SyncEngine;

use crate::config::AppConfig;
use crate::error::AppResult;
use crate::hardware::{HardwareDetector, HardwareTier};

/// Shared application state managed by Tauri
pub struct AppState {
    /// Application configuration
    pub config: RwLock<AppConfig>,

    /// Secure storage for credentials, events, and trust anchors
    pub storage: Arc<SecureStorage>,

    /// License manager for feature validation
    pub license: Arc<LicenseManager>,

    /// Sync engine for trust anchor updates
    pub sync_engine: Arc<SyncEngine>,

    /// Hardware detection and tier management
    pub hardware: Arc<HardwareDetector>,

    /// Current hardware tier (cached)
    pub hardware_tier: RwLock<HardwareTier>,

    /// Network connectivity status
    pub is_online: RwLock<bool>,
}

impl AppState {
    /// Initialize application state
    pub fn new() -> AppResult<Self> {
        let config = AppConfig::load()?;

        // Initialize secure storage
        let storage = Arc::new(SecureStorage::new(&config.data_dir)?);

        // Initialize license manager
        let license = Arc::new(LicenseManager::new(
            storage.clone(),
            config.license_public_key.clone(),
        )?);

        // Initialize sync engine
        let sync_engine = Arc::new(SyncEngine::new(
            storage.clone(),
            config.sync_config.clone(),
        )?);

        // Detect hardware
        let hardware = Arc::new(HardwareDetector::new());
        let hardware_tier = hardware.detect_tier();

        tracing::info!(?hardware_tier, "Detected hardware tier");

        let state = Self {
            config: RwLock::new(config),
            storage,
            license,
            sync_engine,
            hardware,
            hardware_tier: RwLock::new(hardware_tier),
            is_online: RwLock::new(false), // Assume offline until proven otherwise
        };

        Ok(state)
    }

    /// Check if a feature is licensed and hardware supports it
    pub async fn check_feature(&self, feature: &str) -> AppResult<()> {
        // Check license
        if !self.license.is_feature_licensed(feature).await? {
            return Err(crate::error::AppError::FeatureNotLicensed(
                feature.to_string(),
            ));
        }

        // Check hardware tier requirements
        let tier = self.hardware_tier.read().await;
        if !tier.supports_feature(feature) {
            return Err(crate::error::AppError::InsufficientHardware {
                required: feature.to_string(),
                available: format!("{:?}", *tier),
            });
        }

        Ok(())
    }

    /// Update online status
    pub async fn set_online(&self, online: bool) {
        let mut is_online = self.is_online.write().await;
        if *is_online != online {
            tracing::info!(online, "Network status changed");
            *is_online = online;
        }
    }
}
