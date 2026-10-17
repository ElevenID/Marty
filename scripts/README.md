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
