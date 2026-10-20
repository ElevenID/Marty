# Security Policy

## Reporting Security Vulnerabilities

The Marty Platform team takes security seriously. If you discover a security vulnerability, please follow our responsible disclosure process:

### How to Report

1. **DO NOT** create a public GitHub issue for security vulnerabilities
2. Send details to: <security@marty-platform.com>
3. Include as much information as possible:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested mitigation (if any)

### What to Expect

- **Acknowledgment**: We will acknowledge receipt within 24 hours
- **Initial Assessment**: We will provide an initial assessment within 72 hours
- **Updates**: We will keep you informed of our progress
- **Resolution**: We aim to resolve critical issues within 7 days

### Scope

This security policy applies to:

- All Marty Platform services and components
- Associated infrastructure and deployment configurations
- Third-party dependencies and integrations

## Current repository checks

The compatibility repository retains these configured controls:

- [Bandit local hook](../.pre-commit-config.yaml), manual code scan and required
  [CI lane](../.github/workflows/ci.yml) use one fail-closed runner. The exact
  [1.9.4](https://github.com/PyCQA/bandit/releases/tag/1.9.4) pin and `src`,
  `packages/marty-common/marty_common`, `scripts` targets live in
  [pyproject.toml](../pyproject.toml). Tests and both generated protobuf
  namespaces are excluded recursively. All plugins are enabled; exceptions
  are specific reviewed source lines, not global skips or a report baseline.
- The same pre-commit configuration retains detect-secrets, but its configured
  baseline is absent from this tree and needs explicit review/provisioning.
  The manual scanner can scan tracked files without approving a baseline.
  That separate hook is not established as a required CI control.
- [CodeQL](../.github/workflows/codeql.yml) runs Python analysis through the
  organization workflow. [Organization quality](../.github/workflows/organization-quality.yml)
  configures workflow validation and dependency review.
- [License compliance](../.github/workflows/license-compliance.yml) configures
  metadata checks, dependency inventory and SBOM generation under its declared
  triggers. An SBOM is an inventory, not a vulnerability or compliance verdict.
- [Dependabot](../.github/dependabot.yml) schedules dependency updates. Review,
  CI and merge protections still govern landing changes; this is not a promise
  of automatic remediation or deployment.

Run the current Bandit hook with:

```sh
uv run --no-project --with pre-commit==4.3.0 pre-commit run bandit --all-files
```

See [check ownership](features/compatibility-check-ownership.md) for execution
and coverage limits. A finding, failed scanner or skipped check is not a pass.
The local hook and CI remove temporary output with `--ephemeral`. Retained
manual reports belong in ignored private directories with bounded retention.
See the real scope/finding/syntax-error/hook probes in
[bandit_gate_test.py](../tests/unit/bandit_gate_test.py).

### Bandit exceptions and runtime qualification

Each `nosec` annotation names its rule and rationale, so changes require normal
source review. Public protocol/error identifiers, invalid test inputs, retry
jitter, synthetic chaos, packaged pytest assertions, representation detection
and validated shell-free tool invocations are distinguished from security
credentials, trust decisions and executable shell input. New occurrences of
these rules remain enabled and are exercised by negative probes.

Some retained compatibility behavior is explicitly unqualified, rather than a
false positive or a completed security feature:

- Legacy authorization identity extraction is not authentication. The Rust
  authentication/authorization owner must qualify verified JWT signatures,
  issuer/audience/expiry and trusted transport-derived mTLS identity before
  claims or roles reach authorization. Unverified decoded claims and caller
  metadata do not satisfy that boundary. The local B110 exception preserves an
  unresolved compatibility path, not an authentication assurance claim.
- Metrics/trust-service all-interface listener defaults require the deployment
  owner to qualify private-network exposure, access control and explicit bind
  configuration. These annotations do not claim an authenticated public endpoint.
- The explicit development configuration factory contains disposable development
  credentials and a temporary trust-cache example. The production factory is an
  unresolved template, not secret provisioning. Deployment must supply managed
  credentials and an owned, access-controlled cache directory; neither factory
  qualifies production operation.
- The legacy PKD OpenXPKI configuration dictionary is not a qualified credential
  or TLS policy. Its compatibility template remains pending reconciliation with
  the maintained provider/deployment owner; do not deploy it as a security baseline.
- The legacy Python mDoc signature-recording fallback remains pending the Rust
  Signing Keys/issuance owner's qualification. That owner must reject absent or
  invalid signatures and recording/provider failures before successful issuance
  or an ACTIVE transition, and prove actual signature/key identity with negative
  tests. The scoped B110 exception records this unresolved obligation; it does
  not certify signing or managed custody. This scanner change does not alter that
  other worker's runtime path.

Bandit passing means the declared static-analysis policy completed. It does not
resolve these runtime/deployment obligations, prove Rust parity, or establish
managed KMS custody.

The unconsumed security-automation and alternate Bandit YAML files are retired.
Their enabled flags did not configure current hooks or workflows.
[Crypto boundaries](../config/security/crypto_boundaries.yaml) and
[security policy](../config/security/security_policy.yaml) remain. Retained
policies do not independently prove runtime enforcement.

The standalone Python crypto-boundary validator and demonstration are retired.
They generated in-process software keys (including explicit CSCA/DSC HSM-policy
overrides), counted in-memory audit entries and checked configuration sections.
The demonstration printed verification/tamper results without making a negative
result fail the run. These scripts did not qualify managed KMS custody or durable
audit behavior. The underlying role-separation, provider and evidence APIs remain
pending a separate consumer and Rust replacement audit.

Preserve their unique acceptance intent under the Rust owners:

- Distinct CSCA, document-signer, wallet/device, verifier, evidence and ephemeral
  session roles and purposes. Deny cross-role/purpose/tenant signing and private
  key sharing while permitting authorized public verification. Holder/device and
  ephemeral session capabilities remain separate from long-term issuer custody.
  Qualify how role/purpose policy reaches actual Rust handlers, including defaults
  and invalid-policy rejection; YAML section presence is not enforcement.
- Managed signing success, unavailable-provider failure and no local/private-key
  fallback. Validate actual returned signatures and key identity/version; provider
  names or successful key construction are insufficient.
- Signed verification and audit evidence with stable subject, actor, operation,
  outcome and timestamp semantics; verifiable individual signatures, chain links
  and public evidence export. Reject modified details/outcomes, invalid signatures
  and broken chains. Define durable retention and failure/concurrency behavior;
  an in-memory entry count is not an audit acceptance test.

Managed-key and grant authorization qualification belongs to the Rust
[Signing Keys owner](https://github.com/ElevenID/marty-ui/tree/main/rust/services/signing-keys).
Its `scripts/probe_signing_keys_openbao_policy.py --rust-adapter` and
`--grant-verifier` modes run the governed disposable-provider checks. Those checks
are not a claim that every role/evidence requirement above has been implemented
or qualified; keep remaining evidence and operational work open with its owner.

The [manual security scanner](../scripts/security_scan.py) runs selected checks
and returns 0 for recognized clean results, 1 for findings, and 2 for unavailable,
failed, malformed or incomplete scans. The shell entry point forwards its exit
status. It reads Bandit's version, source scope and exclusions from `pyproject.toml`,
requires explicit container/filesystem targets, and never builds the retired
Compose stack or globally installs scanners. See
[scanner usage and limits](features/compatibility-consolidation.md).
These outcomes cover selected automated checks, not compliance or release
qualification; optional scanner adapters still need their tools and valid output.

## Open security automation and acceptance requirements

Current runtime security belongs to the
[Marty UI stack](https://github.com/ElevenID/marty-ui),
[Marty Core](https://github.com/ElevenID/marty-core) and
[shared native framework](https://github.com/ElevenID/marty-microservices-framework).
Reconcile these inherited requirements with owners and executed positive/negative
tests. The retired YAML did not implement them:

- SAST, dependency auditing, secrets, container/image and infrastructure-as-code
  analysis with deliberate scope, pinned tools, freshness, failure propagation,
  reports and reviewed triage. Semgrep, Safety/pip-audit, TruffleHog/git-secrets,
  Trivy/Grype/Syft, Docker Scout, Snyk, Clair, Checkov/Terrascan and kube-score
  were named tools or proposals, not all demonstrated current CI controls.
- Authenticated dynamic testing and penetration/vulnerability assessment in
  isolated authorized environments; ZAP/Burp and optional IAST need qualification.
  Define schedules, review/approval boundaries and pre-/post-deployment behavior
  rather than restoring arbitrary enabled flags or automatic policy changes.
- Authentication/MFA/session lifecycle, role/tenant access control, credential/key
  custody and rotation through managed secrets and KMS/HSM, parameterized queries,
  input/URL validation, encryption, transport verification, network isolation,
  secure headers and rate limits. Algorithm names/config presence are not proof.
- Sanitized access, privilege-escalation, configuration-change, suspicious-activity
  and possible-exfiltration events; tested dashboards, alert delivery/routing/
  escalation and incident runbooks. ELK deployment, anomaly detection, continuous
  staffing and response SLAs need separate operational qualification. See
  [observability requirements](CENTRALIZED_LOGGING.md).
- Reviewed severity thresholds, exceptions and remediation policy, with explicit
  behavior on missing tools, invalid results and failed scans. Qualify updates
  before auto-applying security-sensitive configuration changes.
- Control mapping and evidence for applicable OWASP/NIST/ISO/SOC and privacy
  obligations. Retain access logs, approved configuration/policies, training
  records and audit trails with reviewed access, encryption, retention/deletion,
  integrity and independent verification. Seven-year retention and immutable/
  third-party audit flags were proposals, not verified compliance or storage.
- Secure coding, awareness, incident-response and privacy training; vulnerability
  remediation, scan coverage, incident, training and audit metrics; access reviews,
  response exercises and runbook updates. Establish owners and evidence before
  claiming these are operational.

## Developer and operator practices

Use least privilege, synthetic test identities, data minimization, authorization
and validated input. Keep production credentials out of source and reports.
Supply secrets through the selected deployment owner's managed configuration;
rotate them using reviewed procedures. Use supported service-owned KMS/HSM
boundaries for cryptographic operations.

Review dependencies, run applicable scans, investigate findings and check actual
coverage and failures. Review access, recovery, network and incident handling
with deployed owners; example configuration does not establish these controls.

## Contact information

- **Security Team**: <security@marty-platform.com>
- **Emergency Contact**: <security-emergency@marty-platform.com>
- **Compliance Team**: <compliance@marty-platform.com>

## Legal

This security policy is subject to change. Refer to the repository for the
current version. All reports should follow responsible disclosure practices.
