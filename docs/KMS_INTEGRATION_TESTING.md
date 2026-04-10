# KMS Integration Testing Guide

## Overview

This guide covers running integration tests for the KMS Remote Signing functionality using:

1. **SoftwareHSM** - File-based local HSM (no external dependencies)
2. **LocalStack** - AWS KMS emulation (no AWS account needed)

## Quick Start

```bash
# 1. Start required services
docker-compose up -d postgres localstack

# 2. Run all KMS integration tests
./scripts/run_kms_integration_tests.sh

# Or run specific test suites:

# SoftwareHSM tests only (no external dependencies)
pytest tests/integration/test_kms_integration.py::TestSoftwareHSMIntegration -v -m integration

# LocalStack KMS tests (requires LocalStack running)
pytest tests/integration/test_kms_integration.py::TestLocalStackKMSIntegration -v -m "integration and localstack"

# Comparison tests (both providers)
pytest tests/integration/test_kms_integration.py::TestKMSProviderComparison -v -m integration
```

## Test Coverage

### SoftwareHSM Tests
✅ Configure SoftwareHSM provider  
✅ Real signing operations  
✅ Public key retrieval  
✅ Complete sign-and-verify cycle  
✅ Timeout protection  
✅ Provider caching  

### LocalStack KMS Tests
✅ Create KMS keys in LocalStack  
✅ Real AWS KMS API signing  
✅ Public key retrieval  
✅ Complete sign-and-verify with LocalStack  

### Comparative Tests
✅ Verify both providers produce valid signatures  
✅ Cryptographic verification across providers  

## What These Tests Prove

### ✅ Actual Cryptographic Operations
- **Not mocked** - Real signature generation
- **Real verification** - Signatures cryptographically verified
- **Public key extraction** - Actual PEM-formatted keys
- **End-to-end flow** - Complete signing workflow

### ✅ Security Controls
- Timeout protection (30s default)
- Retry logic (3 attempts, exponential backoff)
- Provider caching (1-hour TTL)
- Cache invalidation on config changes

### ✅ Provider Compatibility
- SoftwareHSM works for development
- LocalStack validates AWS KMS integration
- Both produce cryptographically valid signatures

## Running Tests

### Prerequisites

```bash
# Start database
docker-compose up -d postgres

# Create test database
docker-compose exec postgres psql -U marty -c "CREATE DATABASE marty_test;"

# (Optional) Start LocalStack for AWS KMS tests
docker-compose up -d localstack

# Wait for LocalStack to be ready
curl http://localhost:4566/_localstack/health
```

### Run All Tests

```bash
./scripts/run_kms_integration_tests.sh
```

### Run Specific Tests

```bash
# Single test
pytest tests/integration/test_kms_integration.py::TestSoftwareHSMIntegration::test_real_software_hsm_signing -v

# All SoftwareHSM tests
pytest tests/integration/test_kms_integration.py::TestSoftwareHSMIntegration -v

# All LocalStack tests
pytest tests/integration/test_kms_integration.py::TestLocalStackKMSIntegration -v

# With coverage
pytest tests/integration/test_kms_integration.py -v --cov=src.subscription --cov-report=html
```

### Test Markers

```bash
# Run all integration tests
pytest -v -m integration

# Run only LocalStack tests
pytest -v -m localstack

# Run only SoftwareHSM tests
pytest -v -m softwarehsm

# Run all except LocalStack tests
pytest -v -m "integration and not localstack"
```

## Test Output Examples

### SoftwareHSM Success
```
✅ SoftwareHSM signed successfully!
   Payload: b'This is real test data to sign'
   Signature length: 71 bytes
   Signature (hex): 3045022100a1b2c3d4e5f678901234567890abcdef...

✅ Retrieved public key from SoftwareHSM
   Key length: 178 bytes
   Key (first 100 chars): b'-----BEGIN PUBLIC KEY-----\nMFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE...'

✅ Complete sign-and-verify cycle successful!
   Data signed: b'Integration test: sign and verify'
   Signature verified with public key
```

### LocalStack Success
```
✅ Created KMS key in LocalStack: a1b2c3d4-5678-90ab-cdef-1234567890ab

✅ LocalStack KMS signed successfully!
   Key ID: a1b2c3d4-5678-90ab-cdef-1234567890ab
   Payload: b'LocalStack KMS integration test payload'
   Signature length: 71 bytes
   Signature (hex): 3046022100f1e2d3c4b5a6978801234567890abcdef...

✅ Complete LocalStack KMS sign-and-verify successful!
   Data: b'LocalStack integration test: complete cycle'
   Signature verified cryptographically
```

### Comparative Test Success
```
✅ SoftwareHSM signature verified
✅ LocalStack KMS signature verified
✅ BOTH providers produce cryptographically valid signatures!
```

## Troubleshooting

### Database Connection Error
```bash
# Start postgres
docker-compose up -d postgres

# Check it's running
docker-compose ps postgres

# Create test database
docker-compose exec postgres psql -U marty -c "CREATE DATABASE marty_test;"
```

### LocalStack Not Running
```bash
# Start LocalStack
docker-compose up -d localstack

# Check health
curl http://localhost:4566/_localstack/health

# Check logs if unhealthy
docker-compose logs localstack
```

### Import Errors
```bash
# Install test dependencies
pip install -r requirements_kms_security.txt
pip install pytest pytest-asyncio boto3

# Install Marty packages
pip install -e packages/marty-common
pip install -e .
```

### Signature Verification Fails
This indicates a real bug - the signatures should verify! Check:
- Algorithm mismatch (ES256 vs RS256)
- Key type mismatch (EC vs RSA)
- Hash algorithm mismatch (SHA256 vs SHA512)

## Next Steps

After integration tests pass:

1. **Production Testing** (optional)
   - Test with real AWS KMS using test account
   - Verify with actual AWS API rate limits
   - Test in production-like environment

2. **Load Testing**
   ```bash
   # Test concurrent signing operations
   pytest tests/performance/test_kms_load.py -v
   ```

3. **Security Testing**
   ```bash
   # Run security test suite
   pytest tests/security/test_kms_security.py -v
   ```

4. **End-to-End Testing**
   ```bash
   # Test complete credential issuance flow
   pytest tests/integration/test_credential_issuance_with_kms.py -v
   ```

## CI/CD Integration

Add to your CI pipeline:

```yaml
# .github/workflows/test.yml
jobs:
  kms-integration-tests:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15-alpine
        env:
          POSTGRES_USER: marty
          POSTGRES_PASSWORD: marty
          POSTGRES_DB: marty_test
      localstack:
        image: localstack/localstack:latest
        ports:
          - 4566:4566
        env:
          SERVICES: kms
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -r requirements_kms_security.txt
      - run: pytest tests/integration/test_kms_integration.py -v
```

## Confidence Level

After these tests pass, you have **high confidence** that:

✅ Real signing operations work (not mocks)  
✅ Signatures are cryptographically valid  
✅ Both SoftwareHSM and AWS KMS integration work  
✅ Timeout and retry protection functions  
✅ Provider caching operates correctly  
✅ Public key retrieval works  
✅ Complete end-to-end flow functional  

This provides the confidence needed to deploy the KMS remote signing feature to production.
