# Retired shadowed input validators

Python imports the `marty_common.validation` package, which exports the active
gRPC `RequestValidationError` and `validate_request` helpers. The sibling
`validation.py` file was shadowed and had no direct loader or function consumer;
its four helpers are retired without adding them to the active package API.
The package, request schemas and native-backed MRZ parser remain unchanged.

Preserve the dormant helpers' intent when reconciling input policy with current
Rust service/domain owners:

- Passport data required document number, issuing country, surname, given names,
  nationality, date of birth, gender and expiry. Its proposed format checks were
  5–15 uppercase alphanumeric document-number characters, a three-letter uppercase
  issuing country, 1–40-character uppercase names with spaces/hyphens/apostrophes,
  `M`/`F`/`X` gender and `YYYY-MM-DD` dates with no future birth or past expiry.
- Certificate metadata required ID, subject, issuer, validity start/end,
  certificate data and status. It checked `ACTIVE`/`EXPIRED`/`REVOKED` status and
  ISO datetime parsing; it did not establish certificate authenticity, ordering
  of validity bounds or current lifecycle state.
- MRZ input delegated TD3 parsing and error conversion to the shared parser.
  Keep real format/check-digit/date and malformed-input coverage with the native
  MRZ owner; the removed wrapper supplied no independent qualification.
- Distinguished-name input had a restrictive CN-first regular expression.
  Reconcile supported DN syntax with the current parser rather than adopting
  that expression as an authority.

These are historical input-policy requirements, not newly enforced rules or
proof of conformance. Resolve document/profile differences, Unicode, missing
values, wrong types and error contracts with the owning service before claiming
parity. This cleanup changes no active validation, certificate, key-custody or
signing implementation.
