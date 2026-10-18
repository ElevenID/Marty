# Pretravel wallet-offer migration

Pretravel now adopts the canonical Rust wallet flow. A successful
`POST /api/pre-travel/verify` returns `wallet_offer` with status `pending` and
`credential: null`. It does not return an SD-JWT, disclosures or a presentation
definition. Clients must open the offer in their wallet and complete Rust's
token/nonce/holder-proof flow. Rust owns credential assembly, one-use signing
grants, fresh issuer/lifecycle resolution and managed KMS signing. An API key
authorizes initiation, not credential signing.

Python retains evidence checks and allowlisted request/result translation. MRZ
checksums must pass the native parser; this establishes consistency, not passport
authenticity, document expiry or live-holder identity. Native MRZ dates remain
YYMMDD strings, without guessing a century. VDS-NC needs a trusted signer and
signature; NFC/SOD evidence must pass the retained native trust validation.
Raw barcode/NFC payloads are not forwarded as credential claims. Stronger
evidence, date/century policy, holder-to-document binding and real device/trust
acceptance remain explicit qualification work.

## Server configuration and access

- `PRETRAVEL_ISSUANCE_URL`: trusted HTTPS origin for the Rust issuance service.
- `PRETRAVEL_CREDENTIAL_ISSUER_URL`: optional exact public credential issuer URL
  when it differs from `<PRETRAVEL_ISSUANCE_URL>/org/<organization_id>`.
- `PRETRAVEL_ORGANIZATION_ID`, `PRETRAVEL_ISSUER_DID`, `PRETRAVEL_TEMPLATE_ID`:
  server-owned tenant, issuer and explicit template. No default template is used.
- `PRETRAVEL_ISSUANCE_API_KEY_FILE`: mounted management-credential file, read on
  each initiation to honor rotation. It contains no issuer private key.
- `USE_API_KEY=true` and a nonempty `API_KEY`: required for the pretravel route,
  including development. The general development test key bypass does not apply.

Configure the template for `PreTravelCredential`, SD-JWT payloads and the intended
selective disclosures (`barcodeDataPresent`, `nfcPayloadPresent`, plus any approved
MRZ claims). Template format, disclosure policy and expiry are owned by Rust;
operator/template qualification must precede deployment. Request-level issuer,
tenant, template and signing-key overrides are not accepted. Audience and nonce
inputs are rejected here; the wallet must use the Rust-issued proof challenge.
mDoc pretravel remains unqualified and fails explicitly.

Offers and preauthorization codes are bearer capabilities. Responses use
`Cache-Control: no-store` and `Pragma: no-cache`; callers must not log, persist
indefinitely or share them. The adapter never follows redirects, bounds response
size/time and does not return upstream diagnostics. It checks that the canonical
embedded offer names the configured public credential issuer and matches the
returned preauthorization code. Optional wallet-specific links remain trusted
Rust template output; configure and qualify their deep-link schemes in Rust. It makes no automatic retry
or local-signing fallback. A service timeout must not be treated as successful
issuance or proof that no Rust transaction was created.

## Compatibility and unfinished migration

The pretravel adapter no longer provisions or loads a filesystem signing key.
Existing local key data are not deleted by this code change. The obsolete `TokenizedCredential` model and Python `marty_common.vc.sd_jwt`
issuer are retired after moving their last tracked runtime caller to Rust.
This removes the Python public exports `SdJwtConfig`, `SdJwtDisclosure`,
`SdJwtIssuanceInput`, `SdJwtIssuanceResult` and `SdJwtIssuer`; downstream callers
must migrate to Rust initiation and wallet proof rather than importing them.
The `marty_common.vc` package remains importable, and its separate
`sd_jwt_verifier` module retains native public-JWK verification.

The retired issuer's positive local-file-key test is removed with its owner.
Replacement ownership is exercised by pretravel transport/evidence/API tests
and Rust `initiation_http_behavior`/`credential_signing_behavior` tests. Those
checks do not establish deployed managed-provider or wallet qualification.
Disclosure selection, credential format/expiry and any future audience/nonce or
certificate-chain policy must be qualified in the owning Rust workflow. No
Python private-JWK construction or direct-signing fallback remains here.
Compatibility verification still requires native wheels matching the checkout's
API surface. Use the exact Core revision/features selected by CI; a same-version
historical release wheel can lack those APIs. This migration does not qualify
every shared Python compatibility module or retire its remaining native profiles.
