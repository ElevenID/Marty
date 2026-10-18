# Synthetic passport fixtures

`PassportGenerator` remains a compatibility utility for
`tests.fixtures.data_loader.TestDataLoader` and a local debug consumer. Its
output is synthetic development data. It does not establish ICAO 9303
conformance, a valid signed passport or successful passive authentication.

The implementation currently provides:

- MRZ formatting using the shared native check-digit adapter. The fixed default
  dates and permissive input handling are not a validity or conformance check.
- DG1 byte wrapping and optional simplified DG2 image wrapping. DG2 does not
  implement the complete facial-image format.
- SHA-256 data-group hashes and placeholder SOD bytes when image, certificate
  and key paths exist. The signing method does not read the private key or
  produce a cryptographic signature. A declared algorithm is not a signature.
- Optional JSON output, with binary fields encoded as hexadecimal strings.

For in-memory synthetic data, from the repository root with the project's
common package and native bindings available:

```python
from tests.generators.passport_generator import PassportGenerator

passport = PassportGenerator().generate_passport(
    issuing_country="USA",
    name="SMITH",
    surname="JOHN",
    nationality="USA",
    passport_num="123456789",
    birth_date="850531",
    expiry_date="300531",
)
```

Without image/certificate/key inputs, this example supplies MRZ/DG1 data and
does not produce DG2 or SOD. Its dates and identity are test inputs, not an
issued credential. Do not supply production private keys to this fixture API.

## Remaining qualification

There is no `tests.generators.test_passport_generator` module in this checkout;
the former command and completed-validation checklist were unsupported claims.
Preserve real image/PDF vectors and the
[native interoperability requirements](../../docs/features/native-interop-and-reliability-follow-ups.md).
Any replacement should use the Rust owner, genuine data-group/SOD encoding,
managed KMS signing, and positive/negative signature, digest, trust-chain,
expiry and malformed-input cases. Synthetic output from this utility is not
acceptance evidence for those features.

The source records historical inspiration from the LGPL-3.0 pypassport project
and claims a rewrite without copied code. This cleanup does not verify those
claims or resolve provenance and licensing review. Retain that review before
claiming compatibility or removing attribution.
