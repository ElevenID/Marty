# Native interoperability and reliability follow-ups

The old ISO implementation and quality-gate completion reports are retired.
They named absent Python protocol, transport, application and test modules and
missing workflow/container resources. Their checked boxes, sample performance
figures and claimed compliance do not qualify the current Rust stack. The
requirements below remain open until reconciled with current owners and actual
positive/negative evidence. This cleanup removes no current native capability.

## Device and wallet interoperability

The unreferenced `examples/iso18013_integration_example.py` is also retired.
It constructed engagement/session objects but returned hardcoded reader data
and echoed requested element names as holder success without an encrypted
exchange or consent decision. Its BLE proximity and HTTPS age-only walkthroughs
did not prove transport operation, validated credentials or selective disclosure;
its Python-fallback and performance claims were not qualification evidence.
Keep those journeys as requirements below. The actual `iso18013_bridge.py`,
native adapters, device handlers and tests remain; this deletion does not remove
their implementations or deliver the missing holder/reader application behavior.

Use the native cryptographic owner in [Marty Core](https://github.com/ElevenID/marty-core),
the current [UI service stack](https://github.com/ElevenID/marty-ui), the
[Authenticator](https://github.com/ElevenID/marty-authenticator) and
[Verifier](https://github.com/ElevenID/marty-verifier) device owners, and the
[integration repository](https://github.com/ElevenID/marty-integration-tests)
for actual external qualification. A simulator, fixture or mocked wallet is not
independent device interoperability or standards compliance.

- Reconcile ISO 18013-5 offline and ISO 18013-7/OpenID4VP online requirements
  with the advertised product scope: document structure/mandatory elements,
  engagement QR and capabilities, discovery, session establishment/termination,
  request/response processing, authenticated encryption and error recovery.
- Prove real BLE, NFC/APDU and HTTPS journeys for whichever transports are
  supported. Holder storage, consent, presentation history, passive BLE/NFC
  operation and reader discovery/configuration remain device feature work;
  deleting old reference-app commands implements none of it.
- Qualify issuer and device signatures, trust anchors/chains, reader and holder
  binding, expiry and revocation. Review key agreement, derivation, nonces,
  message authentication and forward secrecy against the applicable native
  profile. Keep approved managed long-term key custody and isolated ephemeral
  session keys, rather than recreating a Python cryptographic implementation.
- Prove minimal/selective disclosure, granular consent, privacy-safe audit and
  session isolation. Claims of cryptographic unlinkability or zero-knowledge
  age predicates need their own positive/negative proof; a reduced claim set
  or simulator does not establish those properties.
- Preserve real mdoc/mDL scenarios for age-restricted access, driving privileges,
  cross-border authority recognition and minimal-disclosure identity/KYC.
  Validate multiple-credential requests, malformed/unsigned/expired/revoked
  inputs, consent denial, replay and mismatched request/response context.
- Treat HSM and biometric integration, broader OCSP/distributed revocation,
  multi-issuer credentials and zero-knowledge proofs as separately qualified
  feature proposals. Reconcile future ISO 18013-8, ARF/eIDAS, W3C VC, DID and
  post-quantum evolution with current standards and owners before advertising
  support. Historical version lists do not establish current conformance.
- Maintain deterministic native test vectors, transport simulation and genuine
  cross-platform/external tests. Qualify latency, throughput, concurrency,
  memory and storage behavior on actual supported devices and releases; the
  report's unmeasured millisecond/session figures are not approved targets.

## Cross-service reliability and release quality

- Exercise real authenticated REST/gRPC contracts, service discovery,
  dependency health/readiness and metrics endpoints against owned disposable
  deployments. A missing contract-test file is not a passing service matrix.
- Exercise timeout/abort and connection failure, circuit-breaker recovery,
  resource exhaustion, concurrency and bounded failure injection against the
  current resilience owner. Prove both rejection and recovery behavior.
- Establish source-bound performance baselines and approved service-specific
  thresholds for success/error rate, latency distributions, throughput and
  resource use. Preserve CI smoke and representative load coverage, raw
  results, trend comparisons and failure diagnostics with finite retention.
- Verify actual release containers: least privilege, non-root execution,
  capability dropping, no privilege escalation, minimal runtime, read-only
  filesystems with explicit writable volumes, pinned inputs, health checks and
  appropriate build isolation. Old Dockerfile examples supply no assurance.
- Keep current license/SBOM, dependency and vulnerability checks, machine-readable
  results and reviewed policy enforcement. Existing performance/security scripts
  and the license-compliance workflow remain; this cleanup does not change
  their behavior or make the old vulnerability-count policy authoritative.
- Bind contract, resilience, performance, container and security results to the
  exact release and current CI owners. Upload appropriate sanitized diagnostics
  and make failures visible. Reconcile alerting, scheduling, artifact retention
  and gate aggregation before claiming complete quality-gate coverage.
