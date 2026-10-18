# Compatibility consolidation and manual scanning

## Manual security scanner

Run from an environment with the current project and selected scanner dependencies
installed. Python 3.11 or newer is required; Bandit configuration loading uses
PyYAML from the development dependencies. The code scan uses uv to execute the
Bandit version and arguments declared in `.pre-commit-config.yaml`, including
the current source scope, exclusions and rule selection in `pyproject.toml`.

```sh
python scripts/security_scan.py code
python scripts/security_scan.py deps
python scripts/security_scan.py secrets
python scripts/security_scan.py containers --image REGISTRY/IMAGE@sha256:DIGEST
python scripts/security_scan.py containers --filesystem PATH
python scripts/security_scan.py code --tool semgrep
```

Actions select Bandit, pip-audit, detect-secrets, and Syft/Grype respectively.
`full` selects those automated checks; it requires an explicit container or
filesystem target too. `dependencies` remains an alias for `deps`. Optional
`--tool` adapters retain Safety, Semgrep, TruffleHog, git-secrets and hadolint;
hadolint requires explicit `--dockerfile` paths. No scanner is installed globally,
no arbitrary local images are selected, and no Compose build is attempted.

Results are isolated in a new ignored `reports/generated/security/` run directory,
or a new explicit `--output-dir`. Existing directories are rejected so stale
reports cannot become new acceptance. `summary.json` names the selected checks;
raw tool output stays in that directory and may contain sensitive findings.
Use bounded private retention and do not commit these reports.

- Exit 0: selected tools returned recognized clean results.
- Exit 1: recognized results contain findings, regardless of a tool's own zero
  exit status (for example detect-secrets or Grype).
- Exit 2: missing tools/targets, timeouts, scanner errors, invalid/empty evidence
  or manual-only qualification. An unclassified git-secrets failure is an error,
  not an inferred finding count. `compliance` deliberately returns manual/incomplete;
  source counts and grep matches are not compliance proof.

Dependency auditing uses the active interpreter with an installed Marty project,
not a fresh tool-only environment. Partial/skipped package audits are incomplete.
Secret scanning neither creates nor approves a baseline and disables external
credential verification. The pre-commit detect-secrets baseline referenced in
this tree is absent; it still needs reviewed provisioning before that separate
hook can be claimed operational. Optional tools may require their own policy,
authentication, rules or vulnerability databases; installing an adapter does
not establish successful execution or equivalent detection coverage.
The git-secrets adapter requires nonempty `secrets.patterns` configuration;
an allowlist or provider-only configuration does not qualify this adapter.
It does not register patterns or print their values into the summary.

The removed shell report generators, custom keyword dumps, source-count compliance
scores and arbitrary image inventory did not qualify security behavior. Current
[security requirements](../SECURITY.md) remain open under their owning services.
The scanner does not add a CI/release gate or replace those requirements.

## Monitoring namespaces

`marty_common.monitoring` remains the health-monitoring package. Its existing
`HealthCheck`, `Metric`, `Alert`, `MetricsCollector`, `HealthMonitor` and
`create_default_monitor` exports retain their constructors and behavior.

The formerly shadowed sibling `monitoring.py` implementation now lives at
`marty_common.monitoring.service_monitor`. Its distinct callback-based health
checks and typed service metrics remain there; they are not replacements for
the package's object model. Nonconflicting service factories, `ServiceMonitor`,
`ServiceInfo`, `MetricType`, `MetricsInterceptor` and `monitor_operation` are
available lazily through the package. Health-status and alert-severity enums
are shared. Trust monitoring remains untouched. No service/thread starts merely
by importing the package, and no runtime readiness is claimed by this move.

## Retry compatibility

`resilience.retry` owns the common Tenacity policy and retry configuration/metric
types. `resilience.retry_enhanced` retains its public names as a thin facade.
Old import paths and pickled class references resolve; the basic and enhanced
metric registries remain separate, including same-name operation histories.
Each facade retains its logger and configured exception selection. In particular,
the default exception tuple still takes precedence over the broader classifier.

The combined attempt/deadline stop policy is fixed to use Tenacity's stop
composition rather than a raw list, so the default timeout configuration can
actually retry. Backoff selection and decorator signatures are otherwise retained.

`AdvancedRetryManager` and `AdvancedRetryConfig` remain distinct: their abort
exceptions, circuit breaker, adaptive strategies and statistics are not equivalent
to the simple decorators. Their current implementation is not deleted or silently
mapped to a weaker policy. Broader scheduling/metrics/API changes require their
own compatibility decisions and tests.
