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

- [Bandit pre-commit hook](../.pre-commit-config.yaml), pinned to
  [1.9.4](https://github.com/PyCQA/bandit/releases/tag/1.9.4), recursively scans
  current `src` and `packages/marty-common/marty_common` sources. Scanner
  exclusions live in [pyproject.toml](../pyproject.toml); tests and both generated
  protobuf namespaces are excluded. Existing rule selection remains explicit
  in the hook, with narrow reviewed annotations for false positives.
- The same pre-commit configuration retains detect-secrets, but its configured
  baseline is absent from this tree and needs explicit review/provisioning.
  The manual scanner can scan tracked files without approving a baseline.
  Running or installing hooks is distinct from CI enforcement.
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
Keep generated scan output in ignored directories or bounded CI artifacts.

The unconsumed security-automation and alternate Bandit YAML files are retired.
Their enabled flags did not configure current hooks or workflows.
[Crypto boundaries](../config/security/crypto_boundaries.yaml) and
[security policy](../config/security/security_policy.yaml) remain, along with
the [crypto-boundary validator](../scripts/validation/validate_crypto_boundaries.py).
Retained policies do not independently prove runtime enforcement.

The [manual security scanner](../scripts/security_scan.py) runs selected checks
and returns 0 for recognized clean results, 1 for findings, and 2 for unavailable,
failed, malformed or incomplete scans. The shell entry point forwards its exit
status. It reads Bandit's version and arguments from the maintained hook,
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
