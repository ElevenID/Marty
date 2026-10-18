# Demo data and environment qualification requirements

The unconsumed legacy database initializers are retired. Their schemas and
sample records described intended demo coverage; they did not qualify current
Rust services. Existing demo state requires an explicit ownership and migration
decision before changing its storage model.

Runtime composition and service-owned migrations belong to
[marty-ui](https://github.com/ElevenID/marty-ui). Wallet journeys belong to
[marty-authenticator](https://github.com/ElevenID/marty-authenticator) and
[marty-integration-tests](https://github.com/ElevenID/marty-integration-tests).
The unconsumed Python `seed_demo_data.py` is also retired. It inserted into
uncreated legacy demo tables, used retired service endpoints, uploaded fake
PEM/credential artifacts and could report success after individual failures.
It never demonstrated schema, issuance or user-provisioning acceptance. The
synthetic certificate generator and OpenBao org-catalog seeder remain separate
capabilities. Current Rust vendor/Canvas/template seeders cover different
scenarios; their existence does not establish parity with this historical demo.

## Retained data and behavior requirements

Reconcile these scenarios with current owners and actual positive/negative
tests before claiming a supported demo environment:

- Representative passports, mDLs (including restrictions and endorsements),
  and mdoc scenarios for academic degrees, professional licenses, employment,
  insurance and certifications. Use synthetic identities and controlled
  validity/expiry dates rather than copying the old named records.
- Issued credentials with issuer and subject identifiers/DIDs, type, validity,
  lifecycle status, payload, proof and selective-disclosure data. Exercise
  issuance, holder presentation and verification through real service paths.
- Trust anchors and linked CSCA certificates with country/organization,
  issuer/subject, serial, validity, status and trust metadata. Validate the
  linkage and trust decisions with the canonical native verification owner.
- Revocation linked to issued credentials, with time, reason and actor; prove
  its effect on verification rather than relying on a stored status string.
- Synthetic document, public certificate, issued-credential and audit artifacts
  in object storage, linked to their current service-owned records. Qualify
  storage authorization, content/format integrity, retention, failure handling
  and cleanup. Historical bucket names and fake PEM/proof strings are not a
  supported storage contract or cryptographic fixture.
- Verification results and system/credential audit events with actor, service,
  resource or credential, action, outcome, time and appropriate request context.
  Qualify event correlation and access/retention policy without exposing secrets
  or unnecessary identity data.
- Unique identifiers, referential integrity, creation/update timestamps and
  bounded indexed lookups by relevant country, holder, credential/subject,
  service, event type and time. Choose storage and indexes from measured
  service requirements; the old physical table/database layout is not mandated.

## Environment and acceptance requirements

Preserve API/UI authentication and authorization journeys for admin, issuer,
verifier, vendor and applicant roles, service health/readiness, synthetic
seeding, logging and
supported notification paths. Browser coverage should distinguish its full
matrix from a fast subset. Wallet consent, presentation and rejection paths
need real exchanges; a simulator alone does not qualify device interoperability.

Provision API/database/object-storage credentials through the owning secret and
configuration boundary, with separate roles, scoped access, rotation and failure
reporting. These non-signing settings still need configuration; fixed demo/root
credentials are not defaults to restore. Signing keys must be managed by KMS;
do not upload private-key PEM/JWK material to an application KV store or add a
local signing fallback. Exercise authenticated real issuance, wallet proof,
holder presentation and verification through supported Rust services.

Provision disposable databases through their current service owners, with
least-privilege and tenant boundaries, repeatable seed/migration behavior,
failure handling and deterministic cleanup. Use the
[database migration requirements](../DATABASE_QUICK_START.md) and
[native interoperability follow-ups](native-interop-and-reliability-follow-ups.md).
These requirements remain open until current-source acceptance demonstrates
them; deleting historical bootstraps implements none of them.

## Synthetic generator integration follow-up

The redundant synthetic-demo wrapper is retired; the real
[synthetic generator](../../scripts/generate_synthetic_data.py) remains.
Preserve offline file generation and the intended isolated trust-store import
of CSCA/DS certificates, master lists and CRLs, with countries and bounded
passport/mDL/mdoc/DTC counts. Qualify referential/cryptographic consistency,
negative cases, repeatability, failure reporting and cleanup against current
owners. The wrapper's missing integration tester was not executable acceptance;
optional legacy trust imports do not establish a supported current database path.

The generator's duplicate database adapter is retired. It used the wrong import
namespace/configuration constructor and SQL columns incompatible with the retained
trust schema, and could print insertion success after skipping every write.
`--database-insert` now rejects before generating files or keys. Actual retained
trust-service APIs, database code and development jobs are unchanged. A future
Rust-owned import must distinguish synthetic seeding from trusted ingestion,
validate certificates/signatures and tenant/trust boundaries, and qualify
idempotence, rollback, failure reporting and observed writes before claiming
success. Offline fixture generation implements none of that acceptance.
