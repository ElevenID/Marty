# ISO 18013 native build ownership

Native builds, bindings and releases belong to
[Marty Core](https://github.com/ElevenID/marty-core). The obsolete Python ISO
bridge and this repository's Core 0.1 wheel builders/downloaders are removed.
Use Core's current README, features, toolchain and release instructions for its
native SDK/conformance bindings. `make test` here checks retained infrastructure
and source schemas; it does not qualify device interoperability.

## Retained interoperability requirements

Keep engagement/CBOR/COSE, ECDH/session encryption, selective disclosure,
BLE/NFC/HTTPS transport, recovery and positive/negative real-device exchanges as
requirements of the current native owners. Removing the old adapter is not
evidence that every transport or device journey is complete. Compare measured
performance on declared workloads; historical speedup and "drop-in" claims are
not current evidence.

Do not recreate a Python protocol kernel, generic secret-byte API or software
signer to replace the retired compatibility path. See
[native interoperability requirements](../features/native-interop-and-reliability-follow-ups.md)
and [the audited retirement boundary](../features/python-identity-retirement.md).
