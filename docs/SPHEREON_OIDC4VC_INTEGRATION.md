# Sphereon wallet interoperability requirements

The former setup script generated a runner for an integration test absent from
this checkout. Its dependency checks and simulated-wallet descriptions are not
current Sphereon qualification. Product runtime belongs to
[marty-ui](https://github.com/ElevenID/marty-ui); genuine external testing belongs
to [marty-integration-tests](https://github.com/ElevenID/marty-integration-tests).

Keep the following requirements open until exact wallet/service releases and
executed positive/negative results establish them:

- Issuer metadata discovery and credential offers, including QR/deep-link
  processing, pre-authorized code and supported authentication/credential
  retrieval journeys.
- Single-use, time-limited codes and cryptographic proof-of-possession/holder
  binding. Validate proof signatures, algorithm/key suitability, audience,
  issuer, nonce and expiry, and reject replay and malformed inputs.
- Advertised SD-JWT and mdoc/mDL formats, passport and custom credential
  configurations, minimal/selective disclosure and issuer/verifier metadata
  and error compatibility.
- Actual Sphereon wallet exchanges and supported presentation flows. A wallet
  simulation or mocked response is a separate test layer, not independent
  interoperability evidence.
- HTTPS, approved managed key/secret custody, privacy-safe diagnostics,
  isolated ephemeral test data and deterministic cleanup.

Select current native configuration, dependencies, protocols and tests from
their owners. The retired Python UI/session-store paths, blanket setup installs,
old environment examples and missing test commands are not a supported lane.
See the [native interoperability follow-ups](features/native-interop-and-reliability-follow-ups.md)
for the wider device and reliability requirements.
