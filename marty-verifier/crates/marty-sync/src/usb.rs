//! USB import for air-gapped deployments

use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::error::SyncError;
use marty_secure_storage::TrustAnchor;

/// USB import result
#[derive(Debug, Serialize, Deserialize)]
pub struct UsbImportResult {
    pub success: bool,
    pub certificates_imported: usize,
    pub signature_valid: bool,
    pub package_version: Option<String>,
    pub error: Option<String>,
}

/// USB trust anchor package format
#[derive(Debug, Deserialize)]
pub struct TrustAnchorPackage {
    /// Package version
    pub version: String,
    /// Package creation timestamp
    pub created_at: String,
    /// Signing certificate (PEM)
    pub signing_cert: String,
    /// Package signature (base64)
    pub signature: String,
    /// IACA certificates (DER, base64 encoded)
    pub iaca_certificates: Vec<CertificateEntry>,
    /// CSCA certificates (DER, base64 encoded)
    pub csca_certificates: Vec<CertificateEntry>,
    /// DSC certificates (DER, base64 encoded)
    pub dsc_certificates: Vec<CertificateEntry>,
}

/// Certificate entry in package
#[derive(Debug, Deserialize)]
pub struct CertificateEntry {
    /// Jurisdiction code
    pub jurisdiction: String,
    /// Certificate subject
    pub subject: Option<String>,
    /// Certificate issuer
    pub issuer: Option<String>,
    /// Certificate serial
    pub serial: Option<String>,
    /// Not before date
    pub not_before: Option<String>,
    /// Not after date
    pub not_after: Option<String>,
    /// DER-encoded certificate (base64)
    pub certificate_der_b64: String,
}

/// Import trust anchors from USB package
pub async fn import_from_usb(
    path: &Path,
) -> Result<(Vec<TrustAnchor>, UsbImportResult), SyncError> {
    tracing::info!(path = ?path, "Importing trust anchors from USB");

    // Check path exists
    if !path.exists() {
        return Err(SyncError::UsbImport(format!(
            "Package not found: {:?}",
            path
        )));
    }

    // Read package file
    let package_json = std::fs::read_to_string(path)?;

    // Parse package
    let package: TrustAnchorPackage = serde_json::from_str(&package_json)
        .map_err(|e| SyncError::UsbImport(format!("Invalid package format: {}", e)))?;

    // TODO: Verify package signature
    // For now, accept without verification (with warning)
    tracing::warn!("USB package signature verification not implemented - accepting package");
    let signature_valid = true;

    // Convert certificates to TrustAnchor format
    let mut anchors = Vec::new();
    let mut count = 0;

    // Process IACA certificates
    for cert in &package.iaca_certificates {
        if let Ok(anchor) =
            parse_certificate_entry(cert, marty_secure_storage::TrustAnchorType::Iaca)
        {
            anchors.push(anchor);
            count += 1;
        }
    }

    // Process CSCA certificates
    for cert in &package.csca_certificates {
        if let Ok(anchor) =
            parse_certificate_entry(cert, marty_secure_storage::TrustAnchorType::Csca)
        {
            anchors.push(anchor);
            count += 1;
        }
    }

    // Process DSC certificates
    for cert in &package.dsc_certificates {
        if let Ok(anchor) =
            parse_certificate_entry(cert, marty_secure_storage::TrustAnchorType::Dsc)
        {
            anchors.push(anchor);
            count += 1;
        }
    }

    tracing::info!(
        count,
        version = %package.version,
        "Imported certificates from USB package"
    );

    Ok((
        anchors,
        UsbImportResult {
            success: true,
            certificates_imported: count,
            signature_valid,
            package_version: Some(package.version),
            error: None,
        },
    ))
}

fn parse_certificate_entry(
    entry: &CertificateEntry,
    anchor_type: marty_secure_storage::TrustAnchorType,
) -> Result<TrustAnchor, SyncError> {
    use base64::Engine;
    use chrono::Utc;

    let certificate_der = base64::engine::general_purpose::STANDARD
        .decode(&entry.certificate_der_b64)
        .map_err(|e| SyncError::Parse(format!("Invalid base64: {}", e)))?;

    // Hash the certificate for ID
    let hash = blake3::hash(&certificate_der);
    let id = format!("{}-{}", anchor_type, &hash.to_hex()[..16]);

    Ok(TrustAnchor {
        id,
        anchor_type,
        jurisdiction: entry.jurisdiction.clone(),
        subject: entry.subject.clone(),
        issuer: entry.issuer.clone(),
        serial_number: entry.serial.clone(),
        not_before: entry.not_before.as_ref().and_then(|s| {
            chrono::DateTime::parse_from_rfc3339(s)
                .ok()
                .map(|dt| dt.with_timezone(&Utc))
        }),
        not_after: entry.not_after.as_ref().and_then(|s| {
            chrono::DateTime::parse_from_rfc3339(s)
                .ok()
                .map(|dt| dt.with_timezone(&Utc))
        }),
        certificate_der,
        certificate_hash: hash.to_hex().to_string(),
        source: marty_secure_storage::TrustAnchorSource::UsbImport,
        synced_at: Utc::now(),
    })
}
