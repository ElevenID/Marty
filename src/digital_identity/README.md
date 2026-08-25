# Digital Identity compatibility package

This directory contains a retained Python compatibility implementation of the
Digital Identity domain and a FastAPI registration adapter. It is not an MMF
plugin and is not a production deployment owner.

Canonical production behavior belongs to the Rust services in
[`marty-ui`](https://github.com/ElevenID/marty-ui) and shared crates in
[`marty-core`](https://github.com/ElevenID/marty-core) and
[`marty-microservices-framework`](https://github.com/ElevenID/marty-microservices-framework).

The compatibility package remains temporarily because some passport-chip and
identity behavior is still under consumer and parity audit. Remove a module
only after a language-neutral contract proves equivalent Rust behavior or an
organization-wide search proves that the module has no supported consumer.

The `digital_identity.plugin` module keeps its historical Python class names,
but only registers routes and lifecycle hooks on a supplied FastAPI
application. It has no framework dependency.
