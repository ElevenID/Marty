# Deployment Boundary

This repository does not provide a deployable Python microservice stack. Its
released Python package contains retained identity compatibility modules backed
by the canonical Rust security and protocol kernels.

Do not build service images from paths under `src/` or invoke a generic Python
service launcher. Those placeholder image contexts and the retired launcher
referenced service modules that had already been removed; the remaining image
contexts were therefore unbuildable and have now been removed as well.

Supported runtime services are built and deployed from
[marty-ui](https://github.com/ElevenID/marty-ui). Shared framework behavior is
owned by the Rust crates in
[marty-microservices-framework](https://github.com/ElevenID/marty-microservices-framework).
Credential issuance, document signing, passport personalization, and
verification are owned by the shared Rust crates in
[marty-credentials](https://github.com/ElevenID/marty-credentials) and
[marty-core](https://github.com/ElevenID/marty-core).

Use the immutable release artifacts, deployment manifests, SBOMs, and
attestations published by those repositories. This compatibility repository is
not an alternate deployment source.
