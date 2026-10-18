# Container workflows and release ownership

This repository retains identity compatibility modules and publishes
`marty-common`. The retired root service-image release model and parallel demo
Compose stack are no longer current deployment entry points.

## Supported development and deployment owners

For this repository, `make test` runs root and shared-package Python tests;
`make package` builds the root compatibility package. `make install` and
`make lint` are also available. Follow the [root README](../../README.md)
for dependencies and native-backend requirements.

Service images, stack startup, migrations and runtime operations belong to
[marty-ui development setup](https://github.com/ElevenID/marty-ui/blob/main/DEVELOPMENT_SETUP.md)
and its [release workflow](https://github.com/ElevenID/marty-ui/blob/main/.github/workflows/cd.yml).
Wallet and browser interoperability qualification belongs to
[marty-authenticator](https://github.com/ElevenID/marty-authenticator) and
[marty-integration-tests](https://github.com/ElevenID/marty-integration-tests).
Use the selected release's configuration and commands. The former root
`dev`, `test-local`, `build-wallet`, `down` and volume-reset recipes are retired.

Keep the intended demo journeys and data coverage in
[demo data qualification requirements](../features/demo-data-qualification.md).
The old fixed ports, example accounts and simulator image name do not establish
current configuration or completed end-to-end acceptance.

## Independent release ownership

The [marty-common publishing workflow](../../.github/workflows/publish-pypi.yml)
accepts `marty-common-v*` tags and validates the tag version against
`packages/marty-common/pyproject.toml`. It builds the package, SBOM, checksums
and provenance, and verifies the immutable GitHub release and asset digests.
PyPI publication remains subject to its configured repository variable and
environment controls.

Release `marty-common` through that workflow after its normal review and
validation. The root harness version and the versions in sibling repositories
are independent. Native kernel releases belong to
[Marty Core](https://github.com/ElevenID/marty-core), and production image
releases belong to the UI stack's release workflow. A root tag does not
rebuild or publish those services.

## Container registry authentication

Use Docker's registry login or the configured credential helper when the
owning deployment workflow requires local registry access:

```sh
docker login ghcr.io --username YOUR_GITHUB_LOGIN
```

Supply the registry credential through Docker's prompt. For noninteractive
use, Docker supports `--password-stdin`; use the owning workflow's configured
credentials and registry permissions. The UI release workflow configures its
own registry authentication. Authentication and permission to publish a
particular package are separate checks.

The retired helper's root build commands are not replacement publication
procedures. Consult the image owner's current release and pull instructions
rather than creating a parallel image publication path.

## TLS and ACME qualification

The uncalled `scripts/acme_bootstrap.sh` wrapper is retired. It generated a
parallel Pebble Compose stack and an unconsumed `config/acme.yaml`; its smoke
check initialized an ACME directory/account but did not request a certificate.
Unpinned fixture images, always-valid domain checks and a TLS-verification bypass
did not qualify a deployment or the Let's Encrypt staging route.

The retained [ACME client](../../packages/marty-common/marty_common/acme_client.py)
and [gRPC TLS adapter](../../packages/marty-common/marty_common/grpc_tls.py) still
provide compatibility interfaces for initial issuance and renewal. Their removal
requires a separate consumer and Rust replacement audit. TLS identities and ACME
account keys have a distinct capability boundary from long-term credential issuer
keys; retiring the wrapper does not remove those features or change their keys.

Preserve these requirements under the current Rust runtime/deployment owners:

- A governed disposable Pebble fixture with pinned images, deliberate port/data
  ownership, trusted CA configuration and actual HTTP-01/domain validation;
  explicit account creation, order, challenge, finalization and certificate retrieval.
- Verified certificate chain, subject/domain, expiry and TLS/mTLS loading; renewal
  policy and positive/negative failure checks for unavailable ACME, invalid challenge,
  rejected order and expired or mismatched certificates. Let's Encrypt staging
  interoperability remains an unqualified requirement until separately exercised.
- Defined account and TLS key custody, file/storage permissions, rotation and cleanup
  appropriate to their owner. Do not treat local fixture directories or generated
  YAML as managed issuer KMS custody or current runtime configuration.

These are retained acceptance requirements, not a claim that removing the wrapper
implements Rust ACME support or completes certificate/transport qualification.
No running container, certificate storage directory or external ACME account is
changed by this source cleanup.
