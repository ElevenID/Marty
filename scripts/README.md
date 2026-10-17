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
