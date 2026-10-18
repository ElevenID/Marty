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

The Python `biometric` extra retains OpenCV for document rectification and image
quality callers. Unused `face-recognition` and `scikit-image` dependencies are
retired; installing them did not provide a connected face-matching or OCR feature.
OCR test selection no longer depends on those unrelated packages. Preserve
biometric matching, liveness, template parsing and quality requirements with the
Rust biometric owner; qualify actual models, thresholds, spoof rejection and
device/image inputs before claiming support. Retained Python image processing
and template APIs remain compatibility work and are not removed by this trim.

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

## Retired shared test scaffolds

The unconsumed root/unit fixture factories, integration conftest and isolation
helper are retired. Actual pytest hooks and the root autouse test environment
remain. Test-specific native/API fixtures, real test modules and shared vectors
remain; this does not remove active behavior tests. The old isolation helper's
transaction context did not roll back anything, and its hardcoded database reset
and recursive cache deletion were not qualified isolation controls.

The passport data loader/generator remain available for a separate local debug
consumer; removing their eager import from conftest does not retire that API.
Their placeholder signatures/images and fixed sample data do not establish
passport/SOD conformance. Preserve their own consumer/data audit separately.

Reconcile the removed scaffolds' intent with the current Rust and integration
owners before claiming acceptance:

- Controlled synthetic primary/secondary mDL holders, namespace/document type,
  driving privileges, portrait and identifying attributes; expired/malformed
  inputs and selective versus age-only disclosure, with explicit consent and
  bounded validity. Use current issuer/verifier formats and template contracts,
  not fixed legacy HTTP/gRPC endpoints, ports, DIDs or expired sample dates.
- Real issuer/holder/verifier exchanges, certificate lifecycle and trust/SOD
  validation, negative cryptographic cases and replay/context rejection. Mock
  gRPC messages and successful stub status strings do not qualify these flows;
  long-term signing stays managed by KMS.
- Genuine image/PDF decoding, document extraction and render/error behavior.
  A 1px image or empty PDF body does not prove a document-processing feature.
- Notification delivery, email content/verification links and failure/retry
  behavior using an isolated approved test mailbox. Preserve configuration,
  access boundaries and safe redacted diagnostics; an in-memory outbox is only
  a test double, not proof of delivery or authentication.
- Service-owned disposable database/schema setup, observed transaction rollback,
  temporary-resource ownership, bounded failure recovery and deterministic
  cleanup. Do not execute generic shell database drops or delete a checkout's
  caches as a substitute for per-test resource isolation. Existing user data and
  untracked local workflows are outside this cleanup.
