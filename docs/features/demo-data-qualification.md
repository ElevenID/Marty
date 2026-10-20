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
OpenBao org-catalog seeder remains a separate capability; the unconsumed
synthetic dataset generator and its heuristic reader are retired. Current
Rust vendor/Canvas/template seeders cover different scenarios; their existence does not establish parity with this historical demo.

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

The unconsumed `scripts/generate_synthetic_data.py`, its self-tests and
`examples/read_ml_file.py` are retired. Repository code, CI and deployed
qualification did not consume their generated datasets. The separate
`tests.generators.passport_generator.PassportGenerator` and fixture loader
remain for their existing consumers; neither is a signed-passport replacement.

The removed generator supplied random passport/security bytes, fake PEM text,
CSCA/DS metadata, CRL and master-list references, mDL driving privileges and
personal fields, PID/eID/degree/insurance mdoc fields, and visa/permit/travel
authorization DTC scenarios. Preserve travel purpose, duration, allowed entry
counts and territories; CRL revocation reasons/times; and master-list sequence,
issue and next-update dates. Those scenario requirements remain open. Its
ASN.1 branch wrapped generated certificates in a sequence without a signed CMS
master list, and its fallback could emit placeholder bytes. The reader only
printed heuristic tag/length/certificate estimates, accepted unexpected input
and swallowed errors. Neither established parsing, signature or trust acceptance.

Preserve offline file generation and intended isolated trust-store import of
CSCA/DS certificates, master lists and CRLs, with controlled countries, bounded
passport/mDL/mdoc/DTC counts, validity and revocation scenarios, linked issuer
and holder records, JSON export and summary counts. Full-dataset and
master-list-only selection remain useful requirements, not supported commands.
A replacement needs explicit time and randomness control; the old seed did not
control timestamps, secret randomness, RSA keys or Python hash randomization.
Qualify referential and cryptographic consistency, malformed and truncated
inputs, repeatability, failure propagation, cleanup and no-write offline mode.
Do not retain the old filenames or proprietary bytes as a protocol contract.

The generator's duplicate database adapter was already retired: it used the
wrong namespace/configuration and incompatible SQL columns, and could report
success after skipping every write. Removing the remaining script does not
restore its `--database-insert` mode. Actual retained trust-service APIs,
database code and development jobs are unchanged. A future Rust-owned import
must distinguish synthetic seeding from trusted ingestion, validate
certificates/signatures and tenant/trust boundaries, and qualify idempotence,
rollback, failure reporting and observed writes before claiming success.

Use the current native trust/PKD and credential service owners with
[marty-integration-tests](https://github.com/ElevenID/marty-integration-tests)
for deployed qualification. This cleanup delivers no replacement generator or
complete format coverage. Signing must follow the managed-KMS boundary;
non-key configuration and public fixture material still need their own
provisioning and retention policy. Preserve genuine signed CMS inputs and
reviewed minimal regression bytes with provenance and positive/negative
assertions; random signatures and generated summaries are not such evidence.
