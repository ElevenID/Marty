# Marty compatibility source

This repository owns the released `marty-common` Python package and retained
identity compatibility modules that are still being audited for Rust ownership.
It no longer publishes or deploys the retired Python Marty MMF plugin.

## Canonical runtime ownership

- [`marty-core`](https://github.com/ElevenID/marty-core) owns shared Rust
  security, credential, protocol, and verification primitives.
- [`marty-microservices-framework`](https://github.com/ElevenID/marty-microservices-framework)
  owns the reusable Rust microservice crates and language-neutral behavior
  contracts.
- [`marty-ui`](https://github.com/ElevenID/marty-ui) owns the Rust production
  service binaries and deployment composition.

The old `mmf.plugins` entry point, health-only container, Helm chart,
Kubernetes manifests, and `ghcr.io/elevenid/marty` release workflow were
retired after an organization-wide consumer audit. The container never mounted
the four services advertised by the Python plugin metadata. Their supported
behavior is owned by the Rust trust-profile, signing-keys, and related platform
services.

## Released package

`packages/marty-common` is versioned and released independently with
`marty-common-v*` tags. Its release workflow builds distributions, an SBOM,
checksums, and provenance attestations.

The root project is a compatibility test and packaging harness. A root build is
not a deployable service.

## Development

```shell
python -m pip install -e . pytest ruff build
python -m pytest tests/unit packages/marty-common/tests -q
python -m ruff check src tests
python -m build
```

Native Python extensions are built from pinned `marty-core` revisions in CI.
Compatibility code must not be deleted until consumer evidence and
language-neutral Rust parity tests demonstrate that its supported behavior has
moved. Production deployment changes are intentionally outside this
repository.

## License

AGPL-3.0-only. See [LICENSE](LICENSE).
