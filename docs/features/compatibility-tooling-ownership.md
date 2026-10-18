# Compatibility tooling ownership

## Deployment generation retirement

The published `marty_common.config.dry_env_generator` module and
`EnvironmentConfigGenerator` class remain importable, but generation now raises
`EnvironmentGenerationRetiredError` (a `RuntimeError`) immediately. The retained
`generate_service_env_vars`, `generate_docker_compose_config`,
`generate_k8s_service_manifests`, and `write_env_file` signatures reject all
requests. The former CLI exits nonzero without writing output. This is an
intentional behavior change; it does not silently produce a different format.

The old generator had no working tracked consumer. It emitted retired
`docker/{service}.Dockerfile` paths, old service dependencies, Python mock/runtime
environment settings, and permissive security templates. Those outputs and
unused template constants are retired. The separate
[`marty_common.service_registry`](../../packages/marty-common/marty_common/service_registry.py)
API is unchanged. Local untracked launcher files are not removed by this change.

Use the Rust-owned deployment catalog in `marty-ui`:

- [Deployment guide](https://github.com/ElevenID/marty-ui/blob/main/deploy-config/README.md)
- [Catalog implementation](https://github.com/ElevenID/marty-ui/tree/main/rust/crates/deployment-catalog)
- [Service metadata](https://github.com/ElevenID/marty-ui/blob/main/deploy-config/catalog/services.json)

In that checkout, `sh scripts/marty-deploy.sh validate` validates the catalog;
`sh scripts/marty-deploy.sh plan <stack>` inspects a selected stack. Choose an
existing supported stack from its guide. These commands are not replacements
for the old generated `.env`, Compose dictionary, or Kubernetes Service APIs.
No automatic Rust subprocess, file conversion, or deployment is performed by
the compatibility shim. Retire old callers explicitly and use the deployment
owner's existing manifests and configuration procedures.

Any future generation feature must derive service/port/endpoint/dependency
mappings from the current service owner, preserve environment-specific overrides
and health/metrics wiring, keep secrets external, use fail-closed TLS/authz
policy, and validate reproducible Compose/Kubernetes outputs against actual
Rust deployment schemas. Kubernetes namespace/selector/port mappings and env
file rendering still require explicit qualification; this retirement does not
claim those features have migrated or approve the old defaults for production.

## Protocol generation

Protobuf Python implementations are generated once into `marty_plugin.proto.v1`
from `proto/v1`. Both installed `proto.v1` and checkout `src.proto.v1` imports
remain module aliases. Run `python src/compile_protos.py` with
`grpcio-tools==1.76.0`; generation requires both message and RPC outputs and
fails if either cannot be generated. The former system-protoc fallback could
report success with missing RPC bindings and is retired.
Generation is a checkout development command: the wheel does not ship protocol
sources or `src.compile_protos`. Its broken `compile-protos` console entry point
is removed; it never provided an installed generation command.

The pinned compiler belongs to the root checkout's `proto` extra, installed by
`make install` (or `python -m pip install -e ".[proto]"`). This also supplies the
system-language protobuf pre-commit hook. Ordinary `marty-common` installations
no longer install a compiler; gRPC, protobuf messages, reflection and health
checking remain runtime dependencies. Protocol CI keeps its explicit pinned
compiler installation and checks generated bindings and compatibility imports.

The DTC source already contains Type 1, 2 and 3 profiles. Regeneration reconciles
the stale implementation with those additive schema definitions; it does not
establish that each profile has a completed runtime issuance feature.
The public root protocol sources are retained and validated separately.
The older dynamic root imports in the common gRPC factory/runner remain a
separate integration issue: changing them can activate previously unused
registration paths and requires service-specific qualification.
