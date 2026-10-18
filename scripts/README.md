# Compatibility repository scripts

This repository retains identity compatibility code. Current deployment and
service startup procedures belong to
[the UI stack](https://github.com/ElevenID/marty-ui/blob/main/DEVELOPMENT_SETUP.md),
native kernel releases belong to
[Marty Core](https://github.com/ElevenID/marty-core), and official interoperability
qualification belongs to
[the integration repository](https://github.com/ElevenID/marty-integration-tests).
Use the owning repository's current workflow rather than a parallel local stack.

The Microsoft demo launchers and their old setup tutorial referenced retired
Compose/Kubernetes resources. Their removal leaves
[wallet interoperability requirements](../docs/demos/microsoft_authenticator.md)
open. The remaining source-level, native-wheel and maintenance scripts are not
a claim that a retired Python service deployment is supported.

The orphan Python service generator and retired development/database/image
launchers have also been removed. Their retained requirements and public
compatibility APIs are documented in
[shared service infrastructure ownership](../docs/DRY_IMPLEMENTATION_GUIDE.md)
and [database migration requirements](../docs/DATABASE_QUICK_START.md).

Use the root Makefile for this repository's `install`, `test`, `lint` and
`package` tasks. Regenerate protocol bindings from a checkout with:

```sh
python -m pip install grpcio-tools==1.76.0
python src/compile_protos.py
```

See [compatibility tooling ownership](../docs/features/compatibility-tooling-ownership.md)
for the canonical namespace and import aliases.

The unused release/registry wrappers and legacy database initializer files
are retired. Current package/image release ownership and registry login are
described in [container workflows](../docs/guides/DOCKER.md). Retained unique
demo data and acceptance requirements are in
[demo data qualification](../docs/features/demo-data-qualification.md).

The unconsumed Helm-values, logging/OpenXPKI setup, synthetic-demo and OBv3
wrappers are retired. Actual logging/certificate APIs, the synthetic generator
and the compliance-profile seeder remain. Retained requirements are described in
[logging ownership](../docs/CENTRALIZED_LOGGING.md),
[OpenXPKI integration](../docs/DEVELOPER_GUIDE.md#openxpki-integration-ownership),
[demo qualification](../docs/features/demo-data-qualification.md) and
[OBv3 readiness](../src/digital_identity/docs/OBV3_READINESS.md).

Performance execution belongs to
[marty-performance](https://github.com/ElevenID/marty-performance); the former
Python runner and reporting wrappers are retired. See
[performance requirements](../docs/PERFORMANCE_TESTING.md) for their unclosed
workload and observability intent.

Helm/deployment configuration must come from the current UI stack owner.
Preserve per-service identity and secret references, least-privilege pod/service
accounts, verified TLS/mTLS, database isolation/pools and migrations, optional
object-storage/KMS/event-bus integration, ingress, resource bounds/autoscaling,
scheduling and monitoring/mesh requirements where supported. The removed
values writer did not provide chart templates or qualify those integrations;
its fixed ports, images and credentials are not defaults to restore.

## Checkout environment

The former uncalled environment bootstrap is retired. With Python 3.11 or
newer and uv installed, create an isolated environment and install the
compatibility checkout:

```sh
uv venv
uv pip install -e .
```

Use `uv run --no-sync` to execute in that environment, or activate
`.venv/bin/activate` on POSIX / `.venv\Scripts\Activate.ps1` in PowerShell.
For repository test/build tools, run the root `make install` inside the
activated environment. Service data directories are provisioned by their owning
services; creating empty historical directories does not initialize a stack.

Protocol generation is optional for ordinary package use. When changing
schemas, install the pinned compiler into the same environment:

```sh
uv pip install grpcio-tools==1.76.0
uv run --no-sync python src/compile_protos.py
```

See [check ownership](../docs/features/compatibility-check-ownership.md) for
current security scans and the limits of manual typing/coverage diagnostics.

The old root bridge-build, API-test and trust-onboarding verification wrappers
are retired. Native build ownership is in
[the ISO build guide](../docs/iso18013/BUILD_GUIDE.md); intended API and onboarding
coverage is retained in
[API and onboarding qualification](../docs/features/api-onboarding-qualification.md).
Use actual pytest/Make selections and current UI/integration owners rather
than source-text matches or an empty API test tree.

The dev-container definition tied to the absent legacy Compose development
service is retired too. The checkout environment above remains available.
A future container must qualify Python/uv and native build prerequisites,
current editor/lint/type-check tooling, pre-commit installation (including
commit-message hooks), optional browser tooling, controlled output directories,
non-root permissions, deliberate Docker access and only current service ports.
No replacement container is delivered or claimed by removing the broken files.

Use `python scripts/security_scan.py --help` for the portable manual scanner;
`security_scan.sh` remains a thin compatibility entry point. Bandit shares the
maintained hook configuration, failures propagate, and reports go to ignored
`reports/generated/security/`. See
[scanner and compatibility behavior](../docs/features/compatibility-consolidation.md).
