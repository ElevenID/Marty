# BYOK (Bring Your Own Key) Implementation

## Overview

The BYOK implementation enables credential issuers to use externally managed signing keys
(e.g., via a KMS like OpenBao/Vault) instead of providing private keys directly to the
issuance service. This is a critical security requirement for production deployments where
private keys must never leave hardware security boundaries.

## Architecture: Prepare → Sign → Assemble

The core pattern splits credential signing into three phases:

```
┌──────────────┐     ┌─────────────┐     ┌──────────────┐
│   Prepare    │────▶│  KMS Sign   │────▶│  Assemble    │
│  (Rust FFI)  │     │ (External)  │     │  (Rust FFI)  │
└──────────────┘     └─────────────┘     └──────────────┘
 Creates unsigned      Signs bytes         Combines signed
 credential +          via KMS API         components into
 signing input                             final credential
```

1. **Prepare**: Rust builds the unsigned credential structure and returns the exact bytes
   that need to be signed (e.g., JWT header.payload for JWT-VC, IssuerAuth TBS for mDoc).
2. **Sign**: The KMS provider signs the raw bytes using the externally managed key.
3. **Assemble**: Rust combines the unsigned credential with the external signature to
   produce the final signed credential.

## Components

### Rust Layer (`marty-core/marty-oid4vci`)

- **`signer.rs`**: `CredentialSigner` trait — abstraction over signing backends.
  `IssuerKey` implements this trait for backward-compatible local signing.
- **`formats/jwt_vc.rs`**: `prepare_jwt_vc()` / `assemble_jwt_vc()` / `sign_jwt_vc_with_signer()`
- **`formats/mdoc.rs`**: `prepare_mdoc()` / `assemble_mdoc()` / `sign_mdoc_with_signer()`
- **`formats/mod.rs`**: `sign_credential_with_signer()` dispatch

### FFI Bindings (`marty-core/marty-bindings`)

- **`oid4vci_prepare_credential()`**: Returns `(signing_input_b64, credential_id, format_hint)`
- **`oid4vci_assemble_credential()`**: Returns `(credential_str, credential_id)`

### Python Layer (`Marty`)

- **`credential_issuance_service.py`**: Routes based on `template.key_access_mode`:
  - `"key_vault"` / `"hsm"` / `"local"`: existing direct-signing path
  - `"remote_signing"`: new prepare→KMS sign→assemble path via `_create_credential_remote()`
- **`kms_provider.py`**: `KMSProviderInterface` ABC, `KMSProvider` enum (includes `OPENBAO`)
- **`openbao_provider.py`**: `OpenBaoTransitProvider` — OpenBao Transit secrets engine integration
- **`sod_signer.py`**: Accepts optional `sign_fn` callback for external signing of SOD structures

### Configuration

- **`credential-template.json`** (protocol schema): `key_access_mode` enum includes `REMOTE_SIGNING`,
  `remote_signing_config` object with `provider`, `key_name`, `key_version`, `endpoint_url`
- **`crypto_boundaries.yaml`**: OpenBao provider config (addr, transit_mount, auth)
- **`docker-compose.yml`**: OpenBao service (dev mode, port 8200)
- **`config/openbao/init-transit.sh`**: Initializes Transit engine with dev signing keys

### Database Schema

- `credential_template` table: Added `key_access_mode`, `issuer_key_id`, `issuer_algorithm`,
  `remote_signing_config` columns
- Proto: Corresponding fields in `CreateTemplateRequest`, `TemplateResponse`, `UpdateTemplateRequest`

## Template Configuration Example

```json
{
  "key_access_mode": "REMOTE_SIGNING",
  "issuer_algorithm": "ES256",
  "remote_signing_config": {
    "provider": "openbao",
    "key_name": "org-issuer-es256",
    "key_version": 1,
    "endpoint_url": "http://openbao:8200",
    "transit_mount": "transit"
  }
}
```

## Supported Formats

| Format     | Prepare/Assemble | Status |
|------------|------------------|--------|
| JWT-VC     | ✅               | Implemented |
| mDoc       | ✅               | Implemented |
| SD-JWT     | ❌               | Deferred — sd-jwt-rs library does internal signing |

## Standards Alignment

- **CSC API v2.0**: Remote signing protocol for cloud-based key management
- **FIPS 140-3**: Hardware security module requirements
- **EN 419 241-2**: Protection profiles for QSCD (Qualified Signature Creation Device)

## Backward Compatibility

All existing signing paths are preserved:
- `sign_credential()` in Rust still works with `IssuerKey` directly
- `issue_credential()` in Python still accepts `signing_key_jwk` for local signing
- `IssuerKey` implements `CredentialSigner` trait, so existing code works unchanged
- All 18 existing Rust tests pass without modification
