#!/bin/bash
# KMS Integration Test Runner
# 
# Runs comprehensive KMS integration tests with both:
# 1. SoftwareHSM (always available)
# 2. LocalStack AWS KMS (if LocalStack is running)

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  KMS Integration Test Suite${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo

# Check if database is running
echo -e "${YELLOW}▶ Checking prerequisites...${NC}"

if ! docker ps | grep -q postgres; then
    echo -e "${YELLOW}  Starting PostgreSQL...${NC}"
    docker-compose up -d postgres
    sleep 3
fi

# Create test database if it doesn't exist
echo -e "${YELLOW}  Setting up test database...${NC}"
docker-compose exec -T postgres psql -U marty -c "CREATE DATABASE marty_test;" 2>/dev/null || true

# Check if LocalStack is running
LOCALSTACK_RUNNING=false
if docker ps | grep -q localstack; then
    LOCALSTACK_RUNNING=true
    echo -e "${GREEN}  ✓ LocalStack is running${NC}"
else
    echo -e "${YELLOW}  ℹ LocalStack not running - will skip LocalStack tests${NC}"
    echo -e "${YELLOW}    To run LocalStack tests: docker-compose up -d localstack${NC}"
fi

echo

# Run SoftwareHSM tests (always available)
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Running SoftwareHSM Integration Tests${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo

pytest tests/integration/test_kms_integration.py::TestSoftwareHSMIntegration \
    -v \
    -m integration \
    --tb=short \
    --color=yes

echo

# Run LocalStack tests if available
if [ "$LOCALSTACK_RUNNING" = true ]; then
    echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  Running LocalStack KMS Integration Tests${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
    echo
    
    # Wait for LocalStack to be healthy
    echo -e "${YELLOW}  Waiting for LocalStack health check...${NC}"
    for i in {1..30}; do
        if curl -sf http://localhost:4566/_localstack/health > /dev/null 2>&1; then
            echo -e "${GREEN}  ✓ LocalStack is healthy${NC}"
            break
        fi
        if [ $i -eq 30 ]; then
            echo -e "${RED}  ✗ LocalStack health check timeout${NC}"
            exit 1
        fi
        sleep 1
    done
    
    echo
    
    pytest tests/integration/test_kms_integration.py::TestLocalStackKMSIntegration \
        -v \
        -m "integration and localstack" \
        --tb=short \
        --color=yes
    
    echo
    
    # Run comparative tests
    echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  Running Provider Comparison Tests${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
    echo
    
    pytest tests/integration/test_kms_integration.py::TestKMSProviderComparison \
        -v \
        -m integration \
        --tb=short \
        --color=yes
fi

echo
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  ✓ KMS Integration Tests Complete${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo

# Summary
echo -e "${YELLOW}Test Coverage Summary:${NC}"
echo "  ✓ SoftwareHSM - File-based local HSM (development)"
if [ "$LOCALSTACK_RUNNING" = true ]; then
    echo "  ✓ LocalStack KMS - Simulated AWS KMS (no AWS account)"
    echo "  ✓ Provider comparison - Both providers tested"
else
    echo "  ○ LocalStack KMS - Skipped (not running)"
fi
echo

echo -e "${YELLOW}Next Steps:${NC}"
echo "  • Review test output above for any failures"
echo "  • For production, test with real AWS KMS using test credentials"
echo "  • Run security tests: pytest tests/security/ -v"
echo "  • Run full test suite: pytest tests/ -v"
