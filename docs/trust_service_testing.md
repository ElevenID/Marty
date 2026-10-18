# Trust Service Testing with Master Lists

This guide demonstrates how to generate master lists for testing the trust service without database insertion.

The generator produces offline synthetic fixtures, not trusted ingestion or
certificate/signature conformance evidence. Its old `--database-insert` mode is
unsupported and fails before generation; the retained import requirements and
current ownership are in [demo qualification](features/demo-data-qualification.md#synthetic-generator-integration-follow-up).

## Generating Master Lists for Testing

The `generate_synthetic_data.py` script now supports a `--master-list-only` mode that generates master lists specifically for trust service testing without inserting them into the database.

### Basic Usage

```bash
# Generate master lists for 10 countries
python3 scripts/generate_synthetic_data.py --master-list-only --countries 10

# Generate master lists for specific number of countries with custom output directory
python3 scripts/generate_synthetic_data.py --master-list-only --countries 5 --output-dir reports/generated/trust-test

# Use a specific seed for reproducible results
python3 scripts/generate_synthetic_data.py --master-list-only --countries 3 --seed 123
```

### Generated Files

When using `--master-list-only`, the script generates:

1. **`master_lists.json`** - Array of master lists with mock certificate references (JSON format)
2. **`master_list_<country>.ml`** - Individual master list files in binary `.ml` format
3. **`synthetic_test_data.json`** - Complete dataset structure for compatibility
4. **`data_summary.json`** - Summary statistics

### Master List Formats

The script generates master lists in two formats:

#### JSON Format (`master_lists.json`)

Human-readable JSON containing all master lists for easy inspection and debugging.

#### Binary ML Format (`master_list_<country>.ml`)

Binary files using a simplified ICAO-style format specifically for trust service testing. Each `.ml` file contains:

- Magic bytes: "ICAOML" (6 bytes)
- Version number (2 bytes)
- Country code (3 bytes)
- Sequence number (4 bytes)
- Issue and next update timestamps (16 bytes)
- Certificate count and certificate data
- Digital signature placeholder (32 bytes)

### Reading ML Files

Use the included reader tool to inspect `.ml` files:

```bash
python3 examples/read_ml_file.py reports/generated/trust-test/master_list_usa.ml
```

### JSON Structure

Each generated master list (in JSON format) contains:

```json
{
  "country": "USA",
  "sequenceNumber": 42,
  "version": "1.0.0",
  "issueDate": "2025-10-03T18:36:57.485698+00:00",
  "nextUpdate": "2025-11-03T18:36:57.485698+00:00",
  "certificates": [
    {
      "certificateId": "USA_CSCA_1",
      "thumbprint": "3bce999cd531b2c31131e1f1f796afb34ac3310d",
      "subject": "CN=USA CSCA 1, O=USA Government, C=USA",
      "validFrom": "2025-07-14T00:36:57.485281+00:00",
      "validTo": "2028-06-05T00:36:57.485281+00:00"
    }
  ],
  "signer": "USA CSCA",
  "signature": "base64-encoded-signature",
  "dataHash": "hex-encoded-hash",
  "metadata": {
    "generatedAt": "2025-10-03T18:36:57.485698+00:00",
    "certificateCount": 5,
    "testingOnly": true,
    "note": "Generated for trust service testing - no database insertion"
  }
}
```

### Key Features

- **No Database Insertion**: Master lists are generated but not inserted into the trust service database
- **Mock Certificates**: Each master list contains 3-8 mock certificate references
- **Testing Metadata**: Includes `testingOnly` flag and explanatory notes
- **Reproducible**: Use `--seed` parameter for consistent results
- **Validation**: Prevents accidental database insertion with mutual exclusivity checks

### Integration with Trust Service

To use these master lists for testing your trust service:

1. Generate the master lists using the script
2. Load the JSON files in your test suite
3. Use the master list data to test trust service validation logic
4. Verify that your service correctly processes master list structures

### Example Test Workflow

```bash
# Step 1: Generate test data
python3 scripts/generate_synthetic_data.py --master-list-only --countries 5 --output-dir reports/generated/trust-test

# Step 2: Use in your tests
# Load reports/generated/trust-test/master_lists.json in your test framework
# Test trust service validation against the master list data
```

This approach allows you to test your trust service with realistic master list data without affecting your database or requiring complex setup procedures.

## Retired comparison harness and remaining acceptance

The old comparison runner and enhanced-test guide are retired: both invoked
Python integration test files that are absent from this checkout. The synthetic
master-list generator and fixture loader remain available; the uncalled
print-only fallback debug probe did not provide an assertion or service test.

Real master-list and trust validation remain requirements. A replacement test
must exercise the current native trust/PKD owner and distinguish synthetic
fixtures from genuine read-only master-list inputs. Prove file discovery,
parsing, certificate extraction, signature and trust decisions, malformed-input
rejection, upload behavior and failure propagation. Do not copy, modify or log
sensitive real inputs; isolate generated artifacts in disposable test directories.
Mocked ASN.1 decoding or PKD responses and the simplified fixture format above
do not establish real ICAO CMS parsing, signature validation or end-to-end trust
qualification. Missing old tests and their claimed example passes close none
of these acceptance requirements. Current deployed interoperability qualification
belongs to [marty-integration-tests](https://github.com/ElevenID/marty-integration-tests).

## Generated output retention and fixture qualification

Seven unreferenced 2025 generator-run directories are retired from version
control. Summaries and repeated JSON payloads were run output; their simplified
ASN.1-like and proprietary `ICAOML` bytes were not exercised regression
fixtures. The generator and reader remain.

Put new output in ignored `reports/generated/` or an owned disposable
directory, for example:

```sh
python scripts/generate_synthetic_data.py --master-list-only --countries 3 --seed 123 --output-dir reports/generated/trust-test
```

A seed does not promise byte-identical timestamps or cryptographic randomness.
Random signatures, mock certificate references and summaries do not establish
authentic signed ICAO CMS/master-list support.

Preserve format/file discovery, JSON consistency, ASN.1 length/structure
handling, certificate extraction and malformed/truncated inputs as acceptance
requirements. Genuine signed-input, certificate-chain, revocation and trust
decisions need the current native owner and positive/negative tests. Retain
reviewed minimal byte fixtures with assertions and provenance when they expose
a real regression. Narrow ignores for retired run directories do not prohibit
source fixtures or baselines elsewhere. Deleting old runs closes no requirement.
