# ISO 18013 native build ownership

Native extension builds and releases belong to
[Marty Core](https://github.com/ElevenID/marty-core). The compatibility repository
retains its [ISO bridge](../../src/marty_plugin/iso18013_bridge.py), example and
native packaging checks. The uncalled macOS-specific bridge launcher is retired;
its absolute checkout paths, masked failures and old test counts were not a
supported build procedure.

Use [scripts/build-native-wheels.sh](../../scripts/build-native-wheels.sh) with
a Core checkout at the immutable revision selected by
[CI](../../.github/workflows/ci.yml). It builds the three native distributions,
including ISO 18013, using pinned maturin and fails on build or wheel-count errors.
For released dependencies use
[download-native-wheels.sh](../../scripts/download-native-wheels.sh), which
checks release asset digests. Follow the current Core owner for toolchain,
platform prerequisites, features, local development, Rust tests and publishing.

The former `tests/test_iso18013_bridge.py` is absent. Use the current root
`make test` selection and actual Core tests; the
[packaging checks](../../tests/unit/test_native_packaging_contract.py) verify
delivery configuration, not device interoperability. The retained example
contains placeholders and is not end-to-end acceptance.

## Retained build and interoperability requirements

Qualify supported Python/platform wheels, import/API and error compatibility,
native availability and fail-closed behavior using actual bindings. Compare
measured performance on declared workloads; historical speedup tables and
"drop-in" claims are not current evidence.

Keep engagement/CBOR/COSE, ECDH/session encryption, selective disclosure,
BLE/NFC/HTTPS transport, recovery and positive/negative real-device exchanges
as requirements of the current native owner. Preserve existing Python adapters;
do not recreate a second protocol kernel or delete incomplete transports based
on the retired launcher's failures. Use
[native interoperability requirements](../features/native-interop-and-reliability-follow-ups.md).
