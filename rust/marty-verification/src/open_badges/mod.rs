//! Open Badges verification and issuance helpers.

mod contexts;
mod ob2;
mod ob3;
mod types;

use serde_json::Value;

pub use contexts::{ob2_context_uri, ob3_context_uri, open_badges_context_loader};
pub use ob2::{issue_ob2_json, verify_ob2_json};
#[cfg(not(target_arch = "wasm32"))]
pub use ob3::{issue_ob3_json, verify_ob3_json};
pub use ob3::{issue_ob3_json_async, verify_ob3_json_async};
pub use types::{DocumentStore, OpenBadgesIssueResult, OpenBadgesVerificationResult, OpenBadgesVersion};

pub fn detect_version(value: &Value) -> OpenBadgesVersion {
    if has_context(value, ob2_context_uri()) {
        return OpenBadgesVersion::V2;
    }
    if has_context(value, ob3_context_uri()) || has_context(value, "https://w3id.org/openbadges/v3")
    {
        return OpenBadgesVersion::V3;
    }
    OpenBadgesVersion::Unknown
}

fn has_context(value: &Value, context_uri: &str) -> bool {
    match value.get("@context") {
        Some(Value::String(ctx)) => ctx == context_uri,
        Some(Value::Array(contexts)) => contexts
            .iter()
            .any(|ctx| ctx.as_str().map(|s| s == context_uri).unwrap_or(false)),
        _ => false,
    }
}
