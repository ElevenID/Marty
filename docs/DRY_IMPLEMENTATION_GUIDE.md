# Shared service infrastructure and scaffolding ownership

The former Python service generator required a missing `templates/` tree, and
its Docker build launchers required missing Dockerfiles. The generator, build
launchers and duplicate service-template/refactoring guides are retired.
Historical completion claims and code-reduction percentages do not qualify
the current service stack.

Current Rust service infrastructure belongs to
[Marty Microservices Framework](https://github.com/ElevenID/marty-microservices-framework);
runtime composition, service images and deployment belong to
[marty-ui](https://github.com/ElevenID/marty-ui). Follow their current source
and workflows when adding or changing a service.

## Published Python compatibility infrastructure

The `marty-common` package retains its existing public interfaces. Removing
the orphan generator does not remove or migrate these APIs:

- [Base configuration classes](../packages/marty-common/marty_common/base_config.py)
  and [configuration manager](../packages/marty-common/marty_common/config_manager.py).
- [gRPC service factory](../packages/marty-common/marty_common/grpc_service_factory.py)
  and [server framework](../packages/marty-common/marty_common/grpc_server.py).

Use the actual package signatures rather than the retired generated examples.
Consumers, registration behavior and configuration policy require qualification
before replacing these interfaces. See
[compatibility tooling ownership](features/compatibility-tooling-ownership.md).

Deterministic document verification and protocol cryptography remain Rust
owned. Python maps requests and typed results and fails closed when required
native capabilities are unavailable; see
[Rust verification and protocol migration](RUST_VERIFICATION_MIGRATION.md).

## Service scaffolding requirements

A replacement scaffold is future work unless the current owner demonstrates
it. Retiring the old generator does not deliver a Rust scaffolder or prove
parity with its advertised gRPC, HTTP, hybrid and minimal service variants.
A reviewed scaffold should provide:

- Service identity and validated environment configuration, with deliberate
  dependency selection and compatibility with its owning workspace.
- Protocol definitions or HTTP routes, typed business boundaries and explicit
  errors, health/readiness, graceful shutdown and approved transport security.
- Shared logging, metrics and tracing with service discovery/registration
  tested against the real runtime.
- Meaningful positive/negative service tests, reusable fixtures, a reproducible
  container build and CI checks for the generated service.

The old plans for automated migration, dependency analysis, enhanced templates
and experimental pattern detection remain unqualified proposals. Likewise,
shared monitoring, gateway integration and service-mesh traffic/security
requirements belong with their current owners and need actual qualification;
they are not completed by this documentation cleanup.

## Shared testing requirements

The former `marty_common.testing` scaffold imported a `test_utilities` module
that is absent from this repository. Its example tests and the unused PKD
`conftest_dry_example.py` depended on that missing API; they are retired.
The actual PKD `tests/conftest.py`, application modules and existing tests remain.
The retained configuration and gRPC interfaces above are unaffected.

Shared test infrastructure remains unfinished work. Implement it with the
owning service/test workspace before advertising the old fixture API:

- Reusable mocks, explicit sync/async test clients, service-specific dependency
  overrides and authentication fixtures, with deterministic cleanup.
- Temporary resources, representative certificate/image/MRZ/masterlist data,
  and asynchronous wait/timeout helpers. Sample dictionaries are not valid
  cryptographic fixtures or evidence of integration coverage.
- Service health/readiness checks and deliberately selected mock, partial and
  integration modes. Missing dependencies must not silently turn an intended
  integration check into a passing mock run.
- PKD and document-processing scenarios with real owning-service tests; define
  package exports and fixture discovery before migrating consumers.

No replacement testing package or `MARTY_TEST_MODE` behavior is delivered by
retiring this scaffold. Current repository checks remain the commands below.

## Development commands

For this compatibility repository, the root Makefile exposes `install`,
`test`, `lint` and `package`. The test target includes both root unit tests and
`packages/marty-common/tests`, matching CI. Dependency and native-backend requirements
still apply. Current stack startup and service image workflows belong to
[marty-ui development setup](https://github.com/ElevenID/marty-ui/blob/main/DEVELOPMENT_SETUP.md).

Protocol regeneration remains a working checkout command:

```sh
python -m pip install grpcio-tools==1.76.0
python src/compile_protos.py
```

The canonical generated namespace and retained import aliases are described
in [compatibility tooling ownership](features/compatibility-tooling-ownership.md).
Use [database ownership and migration requirements](DATABASE_QUICK_START.md)
for database changes.
