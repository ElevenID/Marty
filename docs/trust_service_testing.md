# Trust and master-list qualification

The unconsumed synthetic dataset generator and heuristic `.ml` reader are
retired. They produced placeholder data and approximate ASN.1 sequences;
printing a SEQUENCE tag, guessed certificate count or success summary did not
prove ICAO CMS decoding, signature validation or a trust decision. Their old
commands are no longer supported. The generator-mode tests only exercised
that removed tool, not a deployed service.

Preserve offline dataset generation, master-list-only selection, file discovery,
JSON consistency, summary counts, bounded countries and document counts,
repeatability, failure reporting and cleanup. Detailed document and import
requirements remain in
[demo data qualification](features/demo-data-qualification.md#synthetic-generator-integration-follow-up).
Existing `PassportGenerator`, fixture loader, native trust/PKD APIs and tests
remain; none is declared a complete replacement for this tool.

Real master-list qualification must exercise the current native trust/PKD owner
and distinguish synthetic fixtures from genuine read-only signed inputs. Prove:

- File discovery, complete ASN.1/CMS length and structure handling, certificate
  extraction and malformed, truncated and unsupported-input rejection.
- Positive and negative signature, certificate-chain, validity, revocation and
  trust decisions, including the selected tenant and trust profile.
- Authenticated upload/import, observed writes, idempotence, rollback, failure
  propagation and no-write offline behavior through supported service APIs.

Deployed interoperability qualification belongs to
[marty-integration-tests](https://github.com/ElevenID/marty-integration-tests).
Use current Rust service contracts and managed KMS for signing. This cleanup
implements none of the remaining generator or import requirements and changes
no retained trust-service database/development API.

Seven unreferenced 2025 generator-run directories were previously removed from
version control. Their repeated JSON, summaries, proprietary `ICAOML` and
simplified ASN.1-like bytes were not exercised regression fixtures. Do not
restore those outputs as conformance evidence. Put future run output in ignored
`reports/generated/` or owned disposable directories. Retain minimal reviewed
regression fixtures with assertions and provenance when they expose a real bug.
Do not copy, modify or log sensitive real inputs. A seed alone does not control
timestamps or cryptographic randomness.
