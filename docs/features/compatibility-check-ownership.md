# Compatibility check ownership

The retained pre-commit configuration provides format/lint, secret detection,
protobuf generation and security checks. Bandit scans actual `src` and
`packages/marty-common/marty_common` sources recursively using
`pyproject.toml`; tests and both generated protobuf namespaces are excluded
by the scanner itself. The hook uses Bandit 1.9.4; the development dependency
requires at least that version. Existing hook rule selection is preserved.
Run it with:

```sh
uv run --no-project --with pre-commit==4.3.0 pre-commit run bandit --all-files
```

An unsuccessful scan or finding is not a passing result. Keep generated reports
in ignored output or CI artifacts. CodeQL, dependency review and secret scanning
remain distinct controls; this cleanup does not establish equivalence for every
capability in the separate manual security scanner.

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
