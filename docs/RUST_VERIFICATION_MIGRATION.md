# Rust Verification and Protocol Migration

## Runtime boundary

Rust is authoritative for ISO 18013 protocol state and cryptography, MRZ and
eMRTD verification, certificate-chain validation, ICAO master lists, CRLs,
OCSP payloads, and credential cryptography. Python is limited to API and policy
orchestration, persistence, OCR, network I/O, and external-provider adapters.

The required production modules are `marty_iso18013`, `marty_verification`,
and `_marty_rs`. Startup calls `require_native_backends()` and fails with
`NativeBackendUnavailable` if a module or required capability is absent.
Native call failures are normalized as `NativeOperationError`; there is no
Python cryptographic fallback.

## Implemented migration

- ISO 18013 engagement, CBOR, QR generation, two-peer session establishment,
  ECDH-derived directional keys, encrypted messages, counters, state limits,
  selective disclosure, and BLE/NFC/HTTPS transports are native.
- The former Python ISO protocol, cryptography, online-flow, and simulated
  transport modules are compatibility boundaries. Supported names delegate to
  Rust; retired direct-crypto and Python state-machine APIs fail closed.
- TD1/TD2/TD3 MRZ parsing and check digits, SOD parsing and signature checks,
  data-group hashes, CSCA/DSC chains, master lists, CRLs, and OCSP structures
  route through `marty_verification`.
- JWT, SD-JWT, mDoc, signing, key generation, and presentation verification in
  credential services route through `_marty_rs`. Provider/KMS detached
  signatures and ECDSA signature normalization also cross this native boundary.
- IETF Token Status Lists and W3C Bitstring Status Lists are encoded, decoded,
  bounded, and mutated by `_marty_rs`; unknown mappings and unavailable shards
  fail closed. Unsigned Python status-list credentials are disabled.
- `marty_common.crypto_bridge` imports only the canonical module names and
  shares the startup exception hierarchy. Retired BBS, legacy credential, and
  Python certificate/key-construction paths raise `NativeOperationError`.
- The former permissive test signature verifier and structure-only VDS-NC
  verification path have been removed. Invalid keys, missing PKD trust, and
  legacy password hashes are rejected.
- PKD certificate ingestion and trust-anchor metadata extraction use
  `marty_verification`. The standalone synchronization adapter refuses to
  report non-empty certificate batches as stored until persistence is
  configured.
- Shared Rust/Python vectors cover valid and malformed MRZ, SOD/data-group
  alteration, trust chains, and native ISO request/session behavior. Criterion
  benchmarks cover MRZ, SOD, chain validation, and encrypted session handling.

## Packaging and rollout

Marty pins the canonical core native v0.1.46 release built from merged core
commit `2a1e2743ff0499adbe473ea242e179681f874b3c` for `marty_iso18013`,
`marty_verification`, and `_marty_rs`. CI and release jobs download the exact
GitHub release wheels, require GitHub-provided SHA-256 asset digests to match,
and install only those wheels. Production images verify all native backends
during the image build. Linux x86_64 and aarch64 wheels are required for the
multi-architecture image.

Before merging a Marty release, publish the matching immutable native release
from the pinned core commit. A missing release is an expected hard failure in
Marty CI, not a reason to restore a fallback.

Monitor `NativeBackendUnavailable` and `NativeOperationError` rates,
verification failures by normalized error code, certificate/trust-anchor
failures, and p50/p95/p99 verification latency during deployment. Roll back the
application release if needed; do not bypass the native startup requirement.
