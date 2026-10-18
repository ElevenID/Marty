# Retained certificate-validation fixture corpus

This directory contains data, not an executable certificate-validation suite.
The old runner, import hook and unittest compatibility/data helpers are retired:
their five test modules were absent, no current test consumed the helpers, and
the root compatibility package no longer needs the Python `certvalidator` engine.
Current certificate, CSCA and SOD adapters still delegate to Rust; their source
and tests remain intact.

All 212 existing fixture files are retained unchanged. The partial NIST PKITS
corpus contains CRLs, and the OpenSSL OCSP corpus contains responses. Provenance
links remain in their respective [NIST](fixtures/nist_pkits/readme.md) and
[OpenSSL](fixtures/openssl-ocsp/readme.md) readmes. The historical domain CSV is
also retained pending its own data/consumer audit; it is not a live-network test
target or an approved trust source.

The [Rust verification owner](https://github.com/ElevenID/marty-core/tree/main/marty-verification)
must reconcile applicable fixtures with current profiles and supply missing
certificates, trust anchors, evaluation times and expected outcomes before these
data can qualify behavior. Preserve positive and negative path building, policy,
issuer/signature, validity-period and revocation cases, including malformed or
unauthorized CRL/OCSP evidence and unavailable revocation sources. Wire actual
native tests into the owning gate before claiming coverage or conformance;
retaining fixture files alone provides neither. Do not replace this missing
qualification with another Python cryptographic implementation.
