# Python compatibility with public Rust bindings

The common crypto bridge and plugin startup loader share one required public
capability policy. Native public exports are explicitly listed; installing a
wheel with extra attributes cannot add signing or private-key custody to the
bridge. Private-key generation, import, export, local signing and certificate
or badge issuance helpers reject with `NativeOperationError`, including when
an older development wheel implements them. Credential issuance belongs to the
Rust managed-KMS workflow and format-specific preparation/assembly APIs.

Public MRZ, certificate, trust, signature, credential and DTC verification remain
native. Direct imports of reviewed public conversion, presentation and remote
prepare/assemble APIs remain available. Operations outside the required public
core are checked when called; a missing operation raises
`NativeBackendUnavailable`, without a Python cryptographic fallback.
`get_module_status()` reports the required public core, while
`get_available_functions()` lists only allowed operations actually supplied by
the installed native modules. Import-compatible error wrappers are not evidence
that an operation is supported.

The shared key-management compatibility service no longer creates software
private keys, writes `.key` files, retrieves software/provider private keys or exports private
PEM data. Existing key data are left untouched. Its provider path, public-key
export, metadata, audit and lifecycle methods remain. The legacy HSM/provider
interface still needs tenant, purpose, custody and lifecycle qualification; a
test double returning an opaque handle does not prove managed-KMS acceptance.

## Remaining migration work

This adapter change does not update the existing `0.1.56` wheel pins or claim
that all Python services can deploy with Core's `0.2.2` production profile.
Tests against genuine `0.2.2` wheels establish public startup, public signature
verification, DTC remote-signature verification and private-operation rejection.
The complete existing unit/common suite is checked with the pinned profile.

Core intentionally excludes generic random-secret/KDF helpers and chip-session
classes from its production Python profile. The existing Python password and
DTC access-key helpers, BAC/PACE/EAC journeys and opaque session ownership need
their Rust product contracts before upgrading their callers. Missing native
operations fail explicitly; compatibility must not recreate generic secret-byte
APIs in Rust bindings or implement them in Python to make tests pass.

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
