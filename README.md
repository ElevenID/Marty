# Marty shared Python infrastructure

This repository releases `marty-common` infrastructure utilities and retains
source protocol schemas, migration records and historical capability evidence.
The old Python identity implementation, its `marty-identity-compat` distribution,
and its Core 0.1 compatibility adapters are retired.

The supported identity stack is owned by
[`marty-core`](https://github.com/ElevenID/marty-core),
[`marty-credentials`](https://github.com/ElevenID/marty-credentials),
[`marty-microservices-framework`](https://github.com/ElevenID/marty-microservices-framework),
and the Rust services and deployment composition in
[`marty-ui`](https://github.com/ElevenID/marty-ui).

## Maintained scope

`packages/marty-common` supplies shared service setup, middleware, database,
messaging, Cedar authorization, TLS/mTLS, configuration, monitoring, logging,
resilience, DTO and source tooling utilities. Billing and commerce still use
these APIs. It does not supply credential issuance, identity verification,
chip cryptography, Python JWT authentication, or automatic ACME issuance.
Current Core 0.2 native SDK/conformance bindings remain owned by Core.

The former MMF plugin entry point, service image, chart, Kubernetes manifests
and image release workflow were already removed. There is no root identity
wheel or deployable Python service stack. Protocol types under `src/` remain
source-only schemas, not running endpoints. Migration/data records are retained
without executing or changing them.

See the [retirement boundary and consumer evidence](docs/features/python-identity-retirement.md)
for retained callers, Rust owners and unfinished DTC/ACME/chip requirements.
Deletion of the old implementation does not assert native product parity.

## Development

```sh
make install
make test
make package
```

Run `python src/compile_protos.py` to regenerate the retained schemas using the
pinned compiler installed by `make install`. CI validates source aliases and
public definitions, tests the common package without Core wheels, scans all
maintained Python sources, and checks wheel/sdist metadata.

## Releases

Only `marty-common` is released, under `marty-common-v*` tags. Its pipeline
publishes distributions, checksums, SBOM and provenance under the repository's
existing registry controls. Version 0.3 removes the obsolete identity/native
API surface; consumers pinned to 0.2 are not silently upgraded.

## License

AGPL-3.0-only. See [LICENSE](LICENSE).

Retained unfinished feature scope: [revocation and MRZ follow-ups](docs/features/revocation-and-mrz-follow-ups.md).
