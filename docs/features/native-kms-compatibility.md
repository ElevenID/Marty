# Native identity implementation ownership

The Python identity implementation, crypto bridge, native startup loaders and
Core 0.1 adapters are retired. This repository no longer builds or installs
maintenance Core wheels and does not offer the `marty-common[ffi]` extra.
Its remaining infrastructure package needs no Core extension. Current Core 0.2
native SDK/conformance bindings remain supported by their owning repository.

Use Rust services and Core kernels for credential issuance, verification,
eMRTD/chip operations and managed signing. Do not reintroduce generic secret-byte
APIs, local-key fallbacks or a second Python identity kernel to keep removed
callers alive. [The retirement audit](python-identity-retirement.md) identifies
live infrastructure consumers and separates completed retirement from unfinished
product requirements.

Verified mTLS/context handling and externally provisioned TLS remain useful
infrastructure. Requests for the removed Python JWT or automatic ACME mode
fail closed before service startup or automatic key/file activity. The existing
Vault Transit client remains independent of Core, and file-backed private-key
custody continues to reject. Stored key/certificate data are untouched.

## Historical qualification and requirements to preserve

The records below describe the former adapter behavior. They remain requirement
evidence for the Rust owners, not supported Python APIs or claims of full native
lifecycle parity after removal.

Preserve ACME account registration, challenges, issuance/renewal and TLS identity
requirements. Its former key-generation call now rejects through the bridge;
this cleanup does not qualify its existing-key path or a managed TLS deployment.
TLS account/session identities need their own explicit Rust or platform owner,
separate from credential issuer signing. Do not delete existing certificates,
private-key files, non-key configuration or deployment intent during migration.

The retained DTC lifecycle still needs the durable authenticated Rust service
mapping described in [architecture](../architecture.md#dtc-signing-custody-and-migration).
Generic wallet offers do not replace create/get/sign/revoke/QR/verify behavior.

Legacy file-key-vault and document-signer certificate helpers also retain their
public/metadata interfaces but cannot use retired bridge private-key operations.
Preserve certificate policy, validity, issuer/subject, trust-chain and lifecycle
requirements with Rust signing-keys and the document-signing owner. Their old
local call paths are not managed-KMS feature parity. No file-key-vault records or
certificate material are deleted by this adapter change.

Public AA APDU framing, challenge parsing/recovery, ISO9796 verification and EAC
certificate checks load their own required operations. They do not require a
private signer merely to verify. Simulator private signing, mock terminal key
generation and application-held terminal-authentication signing reject; retain
real chip/terminal, trust, authorization and protocol-specific managed-key/session
requirements with the Rust product owner. Public signed test vectors preserve
verification coverage without shipping test signing helpers in the adapter.

Existing DSC records can still be retrieved and parsed. Missing-record DSC
provisioning rejects before key creation, private retrieval or certificate writes;
canonical certificate preparation and managed signing remain Rust owner work.
