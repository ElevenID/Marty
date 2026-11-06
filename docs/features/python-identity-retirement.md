# Python identity implementation retirement

## Decision and evidence

Retire the nondeployable `marty-identity-compat` implementation and its Core 0.1
adapters. Do not upgrade that compatibility runtime or add replacement crypto
APIs to keep it alive. The supported identity implementation is Rust-owned.

This decision follows the November 2026 consumer audit of Marty main
`01c47bbb79699348776b5cd1474974c688fcf1de` and draft #148
`e0cd9c1ffc867c8351ce74b9c499e7b9062b4acc`:

- The root MMF plugin, Python service image, Helm chart, Kubernetes manifests,
  and release workflow were already retired. The remaining root distribution
  was a compatibility harness, not a deployed service.
- Organization-wide code searches found no outside executable import of
  `marty_plugin` and no outside consumer of `marty-identity-compat`.
- Current `marty-ui` releases reject `marty-common` runtime artifacts. UI's
  `services/common` retirement record assigns its former behavior to Rust
  services and excludes that Python tree from runtime and migration images.
- Current Core 0.2 Python bindings are supported native SDK/conformance tooling;
  they are distinct from this obsolete Core 0.1 compatibility layer and remain
  outside this retirement.

The audit does **not** establish that all historical product requirements have
been implemented in Rust. The outstanding requirements below remain explicit.

## Retained consumers and source boundary

`marty-common` remains a separately released infrastructure package. At
`marty-subscriptions` commit `2d5a29c0fbee34e4ce39763d3dff207410f8bf3e`, the live
imports are:

| Consumer | Retained common API |
| --- | --- |
| `services/billing/main.py` | `service_setup.create_service_app`, `database.DatabaseManager`, `database.DatabaseConfig` |
| `services/billing/domain/events.py` | `events.DomainEvent` |
| `packages/marty_commerce/billing_engine.py` | `cedar_engine.CedarEngine`, `cedar_engine.AuthzDecision` |

Preserve these APIs and their transitive imports. Preserve the independent
configuration, database, messaging, middleware, Cedar authorization, monitoring,
logging, resilience, DTO, migration-profile, pairwise-ID, and source tooling
utilities. Generic TLS/mTLS and managed-provider clients do not need the old
Core wheels. Mixed modules must be separated at that boundary rather than
deleted wholesale.

Preserve public protobuf definitions and generated source schemas, SQL and
Alembic migration records, schema/model fields, fixtures, certificate material,
data, and historical release evidence. This retirement never runs a migration,
deletes stored keys or records, changes a license, or rewrites tags/history.
The integration-test repository's handling of old three-image release manifests
is historical evidence support, not a current Python service consumer.

Remove the old executable identity services and orchestration adapters, their
Core-native crypto/eMRTD/chip/credential adapters, and tests whose subject is
solely that removed implementation. Remove Core 0.1 wheel pins, native-wheel
builders/downloaders, and the CI jobs and private-fork reader setup needed only
to build them. Keep security, infrastructure, protocol, and package-release
checks for the maintained sources; change their targets instead of bypassing
required checks.

## Rust ownership and unfinished requirements

| Retired Python responsibility | Current owner / qualification boundary |
| --- | --- |
| Crypto, credential/protocol verification, eMRTD/CSCA primitives | `marty-core` and its current native bindings |
| Credential issuance and managed signing | `marty-credentials`; UI `issuance` and `signing-keys` services |
| Verification and presentation policy | UI `verification` and `presentation-policy`; `marty-core` |
| Trust profiles and registry synchronization | UI `trust-profile`; Core trust-registry contracts |
| Service transport, telemetry, policy, and runtime | `marty-microservices-framework` and UI Rust service binaries |
| Deployment and bootstrap | `marty-ui` deployment catalog, Rust images and migration/bootstrap tools |
| DTC create/get/sign/revoke/QR/verify lifecycle | Intended Rust-owned capability; Core signing/assembly kernels alone do not establish a durable lifecycle service |
| Automatic ACME certificate lifecycle | UI managed-signing owner; deletion of Python local-key issuance does not qualify provisioning/renewal parity |
| BAC/PACE/EAC chip journeys and terminal authentication | Core native session/transport owners; no generic secret-byte Python API or software-key fallback is introduced |
| VDS-NC and document-signer certificate lifecycle | Core format primitives plus managed signing/trust owners; unfinished lifecycle work remains tracked by the existing migration records |

Keep the DTC/VDS decision and managed-KMS qualification records in `marty-ui`
as the product requirement record. Source schemas preserve wire semantics;
their presence does not advertise a running Python endpoint.

## Validation before merge

Exercise the installed infrastructure package without any `_marty_rs`,
`marty_rs`, `marty_verification`, or `marty_iso18013` module available. Verify the
billing service factory, database configuration/session factory, domain event,
and real Cedar allow/deny paths. Run the remaining infrastructure and protocol
tests, build/check the common wheel and sdist, and scan all maintained Python
sources. Check that no active metadata or workflow still builds or installs
the retired Core 0.1 compatibility stack. Obtain two independent audits of the
final change before merging through the required checks.
