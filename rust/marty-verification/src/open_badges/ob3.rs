use serde::Deserialize;
use serde_json::{json, Value};
use std::collections::HashMap;

use iref::{IriBuf, UriBuf};
use ssi::claims::data_integrity::{AnySuite, DataIntegrity, ProofOptions};
use ssi::claims::vc::syntax::AnyJsonCredential;
use ssi::claims::SignatureEnvironment;
use ssi::claims::VerificationParameters;
use ssi::prelude::CryptographicSuite;
use ssi::verification_methods::{
    AnyMethod, Ed25519VerificationKey2018, Ed25519VerificationKey2020, GenericVerificationMethod,
    JsonWebKey2020, ProofPurpose, ReferenceOrOwned, SingleSecretSigner,
};
use ssi::verification_methods::VerificationMethod;
use ssi::jwk::Params as JwkParams;
use ssi::JWK;
use ssi::json_ld::syntax::{Context, ContextEntry};

use crate::error::{VerificationError, VerificationResult};

use super::contexts::{ob3_context_uri, open_badges_context_loader, security_v2_context_uri};
use super::types::{DocumentStore, OpenBadgesIssueResult, OpenBadgesVerificationResult};

#[derive(Debug, Deserialize)]
struct IssueOb3Request {
    credential: Value,
    signing: Ob3SigningOptions,
}

#[derive(Debug, Deserialize)]
struct VerifyOb3Request {
    credential: Value,
    #[serde(default)]
    document_store: Option<DocumentStore>,
}

#[derive(Debug, Deserialize)]
struct Ob3SigningOptions {
    jwk: Value,
    verification_method: String,
    #[serde(default)]
    verification_method_type: Option<String>,
    #[serde(default)]
    controller: Option<String>,
    #[serde(default)]
    proof_purpose: Option<String>,
}

type AnyCredential = DataIntegrity<AnyJsonCredential, AnySuite>;

pub async fn issue_ob3_json_async(request_json: &str) -> VerificationResult<String> {
    let req: IssueOb3Request = serde_json::from_str(request_json)
        .map_err(|e| VerificationError::open_badges(format!("Invalid OB3 issue request: {}", e)))?;

    let credential: AnyJsonCredential = serde_json::from_value(req.credential.clone())
        .map_err(|e| VerificationError::open_badges(format!("Invalid OB3 credential: {}", e)))?;

    let jwk: JWK = serde_json::from_value(req.signing.jwk.clone())
        .map_err(|e| VerificationError::open_badges(format!("Invalid JWK: {}", e)))?;

    let verification_method_iri = IriBuf::new(req.signing.verification_method.clone())
        .map_err(|e| VerificationError::open_badges(format!("Invalid verification_method: {}", e)))?;

    let controller = req
        .signing
        .controller
        .clone()
        .or_else(|| credential_issuer(&req.credential))
        .ok_or_else(|| VerificationError::open_badges("Missing controller for verification method".to_string()))?;

    let controller_bytes = controller.clone().into_bytes();
    let controller_uri = UriBuf::new(controller_bytes).map_err(|e| {
        VerificationError::open_badges(format!("Invalid controller URI {}: {:?}", controller, e))
    })?;

    let method_type = req
        .signing
        .verification_method_type
        .clone()
        .unwrap_or_else(|| "JsonWebKey2020".to_string());
    let (method, suite) = build_verification_method(
        &jwk,
        &verification_method_iri,
        controller_uri,
        &method_type,
    )?;

    let mut resolver: HashMap<IriBuf, AnyMethod> = HashMap::new();
    resolver.insert(verification_method_iri.clone(), method);

    let signer = SingleSecretSigner::new(jwk.clone()).into_local();

    let mut proof_options = ProofOptions::from_method(ReferenceOrOwned::Reference(verification_method_iri));
    if method_type == "Ed25519VerificationKey2018" {
        let context_iri = IriBuf::new(security_v2_context_uri().to_string()).map_err(|e| {
            VerificationError::open_badges(format!("Invalid proof context URI: {}", e))
        })?;
        proof_options.context = Some(Context::One(ContextEntry::from(context_iri)));
    }
    if let Some(purpose) = req.signing.proof_purpose {
        proof_options.proof_purpose = parse_proof_purpose(&purpose)?;
    }

    let loader = open_badges_context_loader()?;
    let env = SignatureEnvironment {
        json_ld_loader: loader,
        eip712_loader: (),
    };

    let signed = suite
        .sign_with(env, credential, &resolver, &signer, proof_options, Default::default())
        .await
        .map_err(|e| VerificationError::open_badges(format!("OB3 signing failed: {}", e)))?;

    let result = OpenBadgesIssueResult {
        issued: true,
        version: "3.0".to_string(),
        credential: serde_json::to_value(&signed).map_err(|e| {
            VerificationError::open_badges(format!("Failed to serialize OB3 credential: {}", e))
        })?,
        warnings: Vec::new(),
    };

    serde_json::to_string(&result)
        .map_err(|e| VerificationError::open_badges(format!("Failed to serialize OB3 issue result: {}", e)))
}

pub async fn verify_ob3_json_async(request_json: &str) -> VerificationResult<String> {
    let req: VerifyOb3Request = serde_json::from_str(request_json)
        .map_err(|e| VerificationError::open_badges(format!("Invalid OB3 verify request: {}", e)))?;

    let credential: AnyCredential = serde_json::from_value(req.credential.clone())
        .map_err(|e| VerificationError::open_badges(format!("Invalid OB3 credential: {}", e)))?;

    let mut errors = Vec::new();
    let mut warnings = Vec::new();

    if !has_context(&req.credential, ob3_context_uri())
        && !has_context(&req.credential, "https://w3id.org/openbadges/v3")
    {
        errors.push("Missing Open Badges v3 context".to_string());
    }

    let store = req.document_store.unwrap_or_default();
    let resolver = collect_verification_methods(&store, &mut warnings);

    let loader = open_badges_context_loader()?;
    let params = VerificationParameters::from_resolver(resolver).with_json_ld_loader(loader);

    match credential.verify(params).await {
        Ok(Ok(())) => {}
        Ok(Err(invalid)) => errors.push(format!("Credential invalid: {}", invalid)),
        Err(err) => errors.push(format!("Credential verification error: {}", err)),
    }

    let normalized = normalize_ob3(&req.credential);

    let result = OpenBadgesVerificationResult {
        valid: errors.is_empty(),
        version: "3.0".to_string(),
        errors,
        warnings,
        normalized: Some(normalized),
    };

    serde_json::to_string(&result)
        .map_err(|e| VerificationError::open_badges(format!("Failed to serialize OB3 verify result: {}", e)))
}

#[cfg(not(target_arch = "wasm32"))]
pub fn issue_ob3_json(request_json: &str) -> VerificationResult<String> {
    futures::executor::block_on(issue_ob3_json_async(request_json))
}

#[cfg(not(target_arch = "wasm32"))]
pub fn verify_ob3_json(request_json: &str) -> VerificationResult<String> {
    futures::executor::block_on(verify_ob3_json_async(request_json))
}

fn parse_proof_purpose(value: &str) -> VerificationResult<ProofPurpose> {
    match value {
        "assertionMethod" => Ok(ProofPurpose::Assertion),
        "authentication" => Ok(ProofPurpose::Authentication),
        "capabilityInvocation" => Ok(ProofPurpose::CapabilityInvocation),
        "capabilityDelegation" => Ok(ProofPurpose::CapabilityDelegation),
        "keyAgreement" => Ok(ProofPurpose::KeyAgreement),
        _ => Err(VerificationError::open_badges(format!(
            "Unsupported proof purpose: {}",
            value
        ))),
    }
}

fn build_verification_method(
    jwk: &JWK,
    verification_method: &IriBuf,
    controller: UriBuf,
    method_type: &str,
) -> VerificationResult<(AnyMethod, AnySuite)> {
    match method_type {
        "JsonWebKey2020" => {
            let public_jwk = jwk.to_public();
            let method = JsonWebKey2020 {
                id: verification_method.clone(),
                controller,
                public_key: Box::new(public_jwk),
            };
            Ok((AnyMethod::JsonWebKey2020(method), AnySuite::JsonWebSignature2020))
        }
        "Ed25519VerificationKey2018" => {
            let public_key = ed25519_public_key_bytes(jwk)?;
            let public_key_base58 = bs58::encode(public_key).into_string();
            let method_value = json!({
                "id": verification_method.to_string(),
                "type": "Ed25519VerificationKey2018",
                "controller": controller.to_string(),
                "publicKeyBase58": public_key_base58
            });
            let method: Ed25519VerificationKey2018 = serde_json::from_value(method_value).map_err(|e| {
                VerificationError::open_badges(format!(
                    "Invalid Ed25519VerificationKey2018 method: {}",
                    e
                ))
            })?;
            Ok((AnyMethod::Ed25519VerificationKey2018(method), AnySuite::Ed25519Signature2018))
        }
        "Ed25519VerificationKey2020" => {
            let verifying_key = ed25519_verifying_key(jwk)?;
            let method =
                Ed25519VerificationKey2020::from_public_key(verification_method.clone(), controller, verifying_key);
            Ok((AnyMethod::Ed25519VerificationKey2020(method), AnySuite::Ed25519Signature2020))
        }
        _ => Err(VerificationError::open_badges(format!(
            "Unsupported verification method type: {}",
            method_type
        ))),
    }
}

fn ed25519_public_key_bytes(jwk: &JWK) -> VerificationResult<Vec<u8>> {
    match &jwk.params {
        JwkParams::OKP(params) if params.curve == "Ed25519" => Ok(params.public_key.0.clone()),
        _ => Err(VerificationError::open_badges(
            "Ed25519 verification methods require an Ed25519 OKP JWK".to_string(),
        )),
    }
}

fn ed25519_verifying_key(jwk: &JWK) -> VerificationResult<ed25519_dalek::VerifyingKey> {
    let public_key = ed25519_public_key_bytes(jwk)?;
    ed25519_dalek::VerifyingKey::try_from(public_key.as_slice()).map_err(|e| {
        VerificationError::open_badges(format!("Invalid Ed25519 public key: {}", e))
    })
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

fn collect_verification_methods(
    store: &DocumentStore,
    warnings: &mut Vec<String>,
) -> HashMap<IriBuf, AnyMethod> {
    let mut methods = HashMap::new();

    for (key, value) in store {
        if let Some(entries) = extract_method_entries(value) {
            for entry in entries {
                if let Some((iri, method)) = parse_verification_method(&entry, warnings, key) {
                    methods.insert(iri, method);
                }
            }
        } else if let Some((iri, method)) = parse_verification_method(value, warnings, key) {
            methods.insert(iri, method);
        }
    }

    methods
}

fn parse_verification_method(
    value: &Value,
    warnings: &mut Vec<String>,
    key: &str,
) -> Option<(IriBuf, AnyMethod)> {
    let method = if let Ok(generic) = serde_json::from_value::<GenericVerificationMethod>(value.clone()) {
        AnyMethod::try_from(generic).map_err(|e| e.to_string())
    } else {
        serde_json::from_value::<AnyMethod>(value.clone()).map_err(|e| e.to_string())
    };

    match method {
        Ok(method) => match IriBuf::new(method.id().to_string()) {
            Ok(iri) => Some((iri, method)),
            Err(_) => {
                warnings.push(format!("Invalid verification method id for document {}", key));
                None
            }
        },
        Err(err) => {
            warnings.push(format!("Failed to parse verification method {}: {}", key, err));
            None
        }
    }
}

fn extract_method_entries(value: &Value) -> Option<Vec<Value>> {
    if let Some(methods) = value.get("verificationMethod") {
        return methods.as_array().cloned();
    }
    None
}

fn credential_issuer(value: &Value) -> Option<String> {
    match value.get("issuer") {
        Some(Value::String(issuer)) => Some(issuer.clone()),
        Some(Value::Object(obj)) => obj.get("id").and_then(|v| v.as_str()).map(|s| s.to_string()),
        _ => None,
    }
}

fn normalize_ob3(value: &Value) -> Value {
    json!({
        "credential_id": value.get("id").cloned().unwrap_or(Value::Null),
        "issuer": value.get("issuer").cloned().unwrap_or(Value::Null),
        "credential_subject": value.get("credentialSubject").cloned().unwrap_or(Value::Null),
    })
}
