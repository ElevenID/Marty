# Document Processing compatibility API

`POST /api/process` uses `DocumentProcessingCoordinator` for image decoding,
optional OpenCV deskew and region estimation, Tesseract OCR, and Rust MRZ parsing
and checksum validation. TD1, TD2 and TD3 parsing are delegated to the native
backend; they are not passport-authenticity, document-expiry or holder checks.
The separate [pretravel wallet flow](../../../docs/features/pretravel-wallet-flow.md)
retains evidence checks and delegates issuance and KMS signing to Rust.

## Runtime and requests

Install the root package and common package with the exact native wheels built
by CI, then this directory's `requirements.txt`. OCR also needs the Tesseract
executable and the configured language data. The Python `pytesseract` package
alone does not provide them. `ImageProcessor.tess_lang` selects a language pack;
otherwise OCR requests `eng`.

From the repository root, start the app with:

```sh
python -m uvicorn app.main:app --app-dir src/marty_plugin/document_processing --host localhost --port 8080
```

Set `USE_REAL_SERVICES=true` for the native inspection client; the compatibility
mock clients fail closed. Configure `USE_API_KEY=true` and `API_KEY` for processing
route authentication. Pretravel requires its own configured authentication even
in development; see its flow documentation for Rust issuer/template binding.

The supported processing scenario is `Mrz`. Send base64 image data (`ImageData`);
`ImageUri` fetching remains unimplemented. `images` and the older `List` input
alias are accepted. For example:

```json
{
  "processParam": {"scenario": "Mrz"},
  "images": [{"ImageData": "<base64 image bytes>", "pageIdx": 0}]
}
```

The response uses the compatibility aliases `TransactionInfo` and
`ContainerList`; inspect `ContainerList.List[].Status` and `mrzResult`.
A missing OCR executable, OCR failure, no text, or invalid MRZ cannot produce a
fabricated identity or positive MRZ result. An empty region can retry OCR on the
full image. Native dates remain YYMMDD; no century is guessed. Field confidence
and line/start/length metadata are `null` until supplied by a measured source;
the former fixed scores and TD3-only positions were not OCR measurements.

The uncalled parallel `MRZProcessingService.process_request` pipeline and
`get_mrz_service` dependency are retired. Python callers should use the
coordinator for request processing; its OCR adapter and native MRZ projection
remain shared with pretravel. Process/MRZ models and the HTTP response envelope
are retained.

## Qualification and unfinished features

Layout crops and texture/watermark checks are heuristics. Calibrated OCR
confidence/coordinates, region detection, strict image-quality enforcement,
portrait/liveness, full authenticity validation, URI fetching and broad
format/device acceptance remain feature work. The current MRZ field list is
partial. Do not interpret health/license placeholders as license validation or
an MRZ checksum result as verification of a physical document. Separate CMC
routes remain delegated to their service client and need their own qualification.
The unused local Dockerfile, Makefile, Docker runner, API verifier and orphan
local test fixtures are retired. The unused duplicate
`tests/document_processing` fixtures/config and `tests/fixtures/fastapi_fixtures.py`
also retire; root behavior tests and shared vectors/data loaders remain. They referenced missing Compose/test files;
the image recipe did not install its project/native wheels/Tesseract, and the
verifier posted non-image bytes while expecting obsolete response aliases.
Use the root checks and Uvicorn command above for the retained compatibility app.
Supported container packaging remains unfinished: install matching native
wheels, Tesseract and language data, define real readiness/health semantics,
configure credentials, and qualify authenticated real-image smoke/E2E tests.
Removing these recipes does not migrate the complete OCR API to Rust or declare
its unfinished packaging and device acceptance complete.

## Checks

From the repository root with matching native backends installed:

```sh
python -m pytest tests/unit/document_mrz_pipeline_test.py tests/unit/pretravel_wallet_offer_test.py tests/unit/test_document_native_boundary.py -q
```

The pipeline checks run real image decoding/layout, native TD1/TD2/TD3 parsing,
and FastAPI request/response handling, with a controlled OCR boundary. They cover
positive results, altered checksums, empty/failed OCR, full-image retry and
language selection. They do not establish OCR accuracy on device captures or
qualification of an installed Tesseract/model/provider environment.

See the repository license and root setup documentation for shared dependencies.
