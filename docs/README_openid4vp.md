# OpenID4VP mdoc/mDL interoperability requirements

The old setup script and its advertised integration test are retired or absent.
Its dependency installation, localhost port probes and fixture overwrites did
not provide a working presentation suite. The existing
`tests/fixtures/openid4vp` JSON files remain as historical inputs pending an
explicit current consumer; they are not deployed configuration or proof.

Qualify the current Rust and device owners through
[marty-integration-tests](https://github.com/ElevenID/marty-integration-tests)
and the [native interoperability requirements](features/native-interop-and-reliability-follow-ups.md).
Keep these acceptance requirements open:

- Actual signed issuance, presentation requests, holder consent and verifier
  processing for mdoc and mDL, using real JWT/JWK and CBOR/COSE operations.
- Requested-claim-only disclosure, age predicates, driving privileges,
  cross-border trust and minimal-disclosure identity scenarios. Prove any
  zero-knowledge or unlinkability claim independently.
- Credential status/revocation, expiry, unsigned/malformed requests, replay,
  mismatched holder/request context, consent denial and multiple credentials.
- Genuine service and wallet exchanges, not mocked positive cryptography.
  Use isolated ephemeral test data and approved key custody, sanitized logs and
  deterministic teardown.

Current protocol, configuration, fixture and test selection belong to those
owners. Do not restore retired Python engines, fixed local ports or dependency
mutation commands to reproduce an old completion claim.
