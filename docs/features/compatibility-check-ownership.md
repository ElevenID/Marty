# Compatibility check ownership

The retained pre-commit configuration provides format/lint, secret detection,
protobuf generation and security checks. Bandit uses one fail-closed runner,
`scripts/security_scan.py code`, in the local hook, manual scans and the required
`Bandit security scan` CI lane. The existing CI Gate requires that lane on pull
requests and merge groups.

`[tool.security_scan.bandit]` in `pyproject.toml` owns the exact scanner pin
(1.9.4) and source targets: `src`, `packages/marty-common/marty_common`, and
`scripts`. `[tool.bandit]` owns recursive test/generated-protobuf exclusions.
All plugins are enabled. Reviewed rule-specific `nosec` annotations explain
individual exceptions; there is no global skipped-rule list or findings baseline.
See [remaining runtime qualification](../SECURITY.md#bandit-exceptions-and-runtime-qualification).

```sh
uv run --no-project --python 3.11 --with pre-commit==4.3.0 pre-commit run bandit --all-files
python scripts/security_scan.py code --ephemeral
```

Python 3.11+ and uv are required. No application/native dependencies are needed
for the code scan. Missing or empty source roots, omitted files, scanner errors,
malformed reports and findings cannot pass. Raw Bandit may exit zero for syntax
errors; the shared runner inspects its report and rejects those incomplete scans.
Config-file changes trigger the hook too. Local and CI checks use ephemeral
reports, print rule/file diagnostics without source or secret literals, and
remove temporary output on exit. Manual retained reports must stay private and
ignored. Real positive/negative probes, including actual hook execution, live in
`tests/unit/bandit_gate_test.py` and run in the required CI lane.

CodeQL, dependency review and secret scanning remain distinct controls. Bandit
analyzes Python; Rust runtime and managed-key qualification remain with their
native owners.

## Typing and documentation coverage

The old mypy and interrogate hooks matched only removed source paths and
provided no current-file coverage. The mypy hook also required an unresolvable
`grpcio-stubs` dependency. These inert hook blocks are retired, along with
absent default paths and retired service overrides in the mypy configuration.

Manual mypy diagnostics retain strict defaults, existing compatibility-module
exceptions, and proper generated-module overrides. A misplaced global
`ignore_errors` setting is removed rather than copied to current sources.
Use an environment containing the selected source's runtime and type dependencies
and pass actual paths explicitly, for example:

```sh
python -m mypy --config-file pyproject.toml packages/marty-common/marty_common/grpc_types.py
```

Current-source typing has substantial existing diagnostics; this command is
not claimed to pass or constitute CI coverage. Qualify module discovery,
dependencies and positive/negative checks on reviewed current modules before
introducing a new gate. Documentation coverage likewise needs a reviewed source
scope and baseline before re-enabling it. Do not hide existing errors, lower
thresholds, or claim coverage from hooks that select zero files.

The unused alternate security YAML is retired; it was not loaded by this hook.
See [security controls and open requirements](../SECURITY.md) for current
workflow ownership and remaining security-automation qualification.

## Coverage and complexity configuration

Coverage configuration lives only in `pyproject.toml`. The duplicate
`.coveragerc` is retired after preserving source/omit scope, report precision,
missing-line display and HTML/XML output settings. Default coverage discovery
now selects the project configuration, as does an explicit
`--rcfile=pyproject.toml` invocation. Keep generated coverage output ignored.

The orphan `.radon.cfg` used TOML-like syntax in an INI file and was not a
project configuration name loaded by the retained Radon CLI. No tracked
`RADONCFG` override selected it. The Radon tool remains available, and the
existing Xenon B thresholds remain in their current configuration. This
removal introduces no new complexity gate or performance claim. Qualifying
current-source metrics and resolving tool/configuration compatibility remain
separate work; obsolete display filters were not enforced limits.
