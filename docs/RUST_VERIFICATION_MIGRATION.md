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
- BER/DER TLV, EF.COM, EF.DG1, EF.DG2, generic elementary-file dispatch,
  facial/fingerprint/iris records and quality policy, and DG15 RSA/SPKI parsing
  and fingerprinting route through one bounded `marty_verification` kernel.
  Python retains the existing result DTOs and chip-reader choreography only.
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

Marty pins the canonical core native v0.1.56 release and the immutable core
revision declared by its workflows for `marty_iso18013`, `marty_verification`,
and `_marty_rs`. CI and release jobs download or build the exact
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

## Wave-two deletion roadmap

Wave two is ordered by the amount of non-Rust implementation that can be
deleted without removing a public behavior. Each item lands native behavioral
fixtures first, exercises those fixtures through Rust and Python bindings, and
then deletes the replaced implementation in the same pre-v1 change.

1. Credential policy, evidence reconciliation, and key-attestation decisions:
   native kernels and thin Python orchestration adapters are implemented; core
   and credential-service pull requests are in the merge train.
2. Passport chip protocols and integrity reporting: in progress. The native
   data-group comparison, validity, mismatch-risk, and recommendation kernel
   replaces the former 703-line Python implementation. BAC derivation, mutual
   authentication, session establishment, and protected APDU exchange now use
   a stateful native binding verified against ICAO Annex D. PACE, the remaining
   APDU compatibility codecs, Active Authentication/ISO 9796, and EAC are the
   remaining parts of this item. Hardware transport callbacks remain Python;
   protocol state and cryptography do not.
3. Subscription entitlement and webhook decision code: consolidate duplicate
   service/UI policy kernels in Rust, preserving persistence and network I/O as
   orchestration.
4. Trust synchronization normalization: move certificate/master-list/CRL/OCSP
   transformation and comparison into the existing Rust trust implementation;
   retain scheduling, downloads, and storage in Python.
5. Authenticator presentation and enrollment decisions: move Dart decision and
   protocol kernels behind generated Rust mobile bindings while retaining
   platform UI and secure-hardware adapters.

No intermediate beta deployment is made while these changes are landing. The
completed aggregate is tested across repositories and deployed to beta once.
