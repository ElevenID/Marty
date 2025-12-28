use std::fs;
use std::path::PathBuf;

use marty_verification::crypto::ed25519::Ed25519KeyPair;
use marty_verification::jwk::base64url_encode;
use marty_verification::open_badges::{issue_ob2_json, issue_ob3_json, ob2_context_uri, ob3_context_uri};
use serde_json::{json, Value};

const FIXTURE_ROOT: &str = "tests/fixtures/open_badges";
const ISSUER_ID: &str = "did:example:issuer";
const VERIFICATION_METHOD: &str = "did:example:issuer#key-1";

fn write_fixture(path: &PathBuf, value: &Value) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    let data = serde_json::to_string_pretty(value).map_err(|e| e.to_string())?;
    fs::write(path, data).map_err(|e| e.to_string())
}

fn fixed_ed25519_jwk() -> Result<(Value, Value), String> {
    let secret: [u8; 32] = [
        1, 2, 3, 4, 5, 6, 7, 8,
        9, 10, 11, 12, 13, 14, 15, 16,
        17, 18, 19, 20, 21, 22, 23, 24,
        25, 26, 27, 28, 29, 30, 31, 32,
    ];
    let keypair = Ed25519KeyPair::from_secret_key(&secret).map_err(|e| e.to_string())?;
    let public = keypair.public_key();

    let public_b64 = base64url_encode(&public);
    let secret_b64 = base64url_encode(&secret);

    let private_jwk = json!({
        "kty": "OKP",
        "crv": "Ed25519",
        "x": public_b64,
        "d": secret_b64
    });
    let public_jwk = json!({
        "kty": "OKP",
        "crv": "Ed25519",
        "x": public_b64
    });

    Ok((private_jwk, public_jwk))
}

fn build_ob2_fixture() -> Result<Value, String> {
    let (private_jwk, public_jwk) = fixed_ed25519_jwk()?;
    let assertion = json!({
        "@context": ob2_context_uri(),
        "type": "Assertion",
        "id": "urn:uuid:assertion-1",
        "badge": "urn:uuid:badge-1"
    });
    let issue_request = json!({
        "assertion": assertion,
        "recipient": {
            "identity": "user@example.org",
            "type": "email",
            "hashed": true,
            "salt": "pepper",
            "hash_alg": "sha256"
        },
        "signing": {
            "jwk": private_jwk,
            "creator": VERIFICATION_METHOD
        }
    });

    let issue_result = issue_ob2_json(&issue_request.to_string()).map_err(|e| e.to_string())?;
    let issue_value: Value = serde_json::from_str(&issue_result).map_err(|e| e.to_string())?;
    let credential = issue_value
        .get("credential")
        .cloned()
        .ok_or_else(|| "Missing OB2 credential".to_string())?;

    let store = json!({
        "urn:uuid:badge-1": {
            "id": "urn:uuid:badge-1",
            "issuer": ISSUER_ID
        },
        ISSUER_ID: {
            "id": ISSUER_ID,
            "name": "Example Issuer"
        },
        VERIFICATION_METHOD: {
            "publicKeyJwk": public_jwk
        }
    });

    Ok(json!({
        "assertion": credential,
        "document_store": store,
        "recipient_identity": "user@example.org"
    }))
}

fn build_ob3_fixture() -> Result<Value, String> {
    let (private_jwk, public_jwk) = fixed_ed25519_jwk()?;
    let credential = json!({
        "@context": [
            "https://www.w3.org/ns/credentials/v2",
            ob3_context_uri()
        ],
        "type": [
            "VerifiableCredential",
            "OpenBadgeCredential",
            "AchievementCredential"
        ],
        "id": "urn:uuid:ob3-credential-1",
        "issuer": ISSUER_ID,
        "credentialSubject": {
            "id": "did:example:subject",
            "type": "AchievementSubject",
            "achievement": {
                "id": "urn:uuid:achievement-1",
                "type": "Achievement",
                "name": "Example Badge",
                "description": "Example achievement description"
            }
        }
    });

    let issue_request = json!({
        "credential": credential,
        "signing": {
            "jwk": private_jwk,
            "verification_method": VERIFICATION_METHOD,
            "verification_method_type": "JsonWebKey2020",
            "controller": ISSUER_ID,
            "proof_purpose": "assertionMethod"
        }
    });

    let issue_result = issue_ob3_json(&issue_request.to_string()).map_err(|e| e.to_string())?;
    let issue_value: Value = serde_json::from_str(&issue_result).map_err(|e| e.to_string())?;
    let issued_credential = issue_value
        .get("credential")
        .cloned()
        .ok_or_else(|| "Missing OB3 credential".to_string())?;

    let method = json!({
        "id": VERIFICATION_METHOD,
        "type": "JsonWebKey2020",
        "controller": ISSUER_ID,
        "publicKeyJwk": public_jwk
    });

    Ok(json!({
        "credential": issued_credential,
        "document_store": {
            VERIFICATION_METHOD: method
        }
    }))
}

fn main() -> Result<(), String> {
    let ob2_request = build_ob2_fixture()?;
    let ob3_request = build_ob3_fixture()?;

    let ob2_path = PathBuf::from(FIXTURE_ROOT).join("ob2_verify_request.json");
    let ob3_path = PathBuf::from(FIXTURE_ROOT).join("ob3_verify_request.json");

    write_fixture(&ob2_path, &ob2_request)?;
    write_fixture(&ob3_path, &ob3_request)?;

    println!("Wrote fixtures to {}", FIXTURE_ROOT);
    Ok(())
}
