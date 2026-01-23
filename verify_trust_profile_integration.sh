#!/bin/bash
#
# Trust Profile Onboarding Verification Script
# 
# This script helps verify that the trust profile onboarding integration
# is working correctly by running tests and checking the implementation.

set -e

echo "======================================"
echo "Trust Profile Onboarding Verification"
echo "======================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Get the workspace root (Marty directory)
MARTY_DIR="$(cd "$(dirname "$0")" && pwd)"
MARTY_UI_DIR="${MARTY_DIR}/marty-ui"

echo "Marty directory: ${MARTY_DIR}"
echo ""

# Check if we're in the right directory
if [ ! -f "verify_trust_profile_integration.sh" ]; then
    echo -e "${RED}Error: Please run this script from the Marty directory${NC}"
    exit 1
fi

echo "Step 1: Checking frontend changes..."
echo "-------------------------------------"

# Check OnboardingPage.js has trust profile step
if grep -q "Trust Profile" "${MARTY_UI_DIR}/ui/src/components/OnboardingPage.js"; then
    echo -e "${GREEN}✓${NC} Trust Profile step found in STEPS_VENDOR"
else
    echo -e "${RED}✗${NC} Trust Profile step not found in STEPS_VENDOR"
    exit 1
fi

# Check trust_framework_code in payload
if grep -q "trust_framework_code: trustProfile" "${MARTY_UI_DIR}/ui/src/components/OnboardingPage.js"; then
    echo -e "${GREEN}✓${NC} trust_framework_code added to API payload"
else
    echo -e "${RED}✗${NC} trust_framework_code not found in API payload"
    exit 1
fi

# Check TrustProfileStep rendering
if grep -q "<TrustProfileStep" "${MARTY_UI_DIR}/ui/src/components/OnboardingPage.js"; then
    echo -e "${GREEN}✓${NC} TrustProfileStep component rendered"
else
    echo -e "${RED}✗${NC} TrustProfileStep not rendered"
    exit 1
fi

echo ""
echo "Step 2: Checking backend changes..."
echo "-------------------------------------"

# Check onboarding.py has trust_framework_code field
if grep -q "trust_framework_code" "${MARTY_UI_DIR}/src/auth/onboarding.py"; then
    echo -e "${GREEN}✓${NC} trust_framework_code field in CompleteOnboardingRequest"
else
    echo -e "${RED}✗${NC} trust_framework_code field not found"
    exit 1
fi

# Check _create_organization_trust_profile function exists
if grep -q "_create_organization_trust_profile" "${MARTY_UI_DIR}/src/auth/onboarding.py"; then
    echo -e "${GREEN}✓${NC} _create_organization_trust_profile helper function exists"
else
    echo -e "${RED}✗${NC} _create_organization_trust_profile not found"
    exit 1
fi

# Check function is called in vendor flow
if grep -q "await _create_organization_trust_profile" "${MARTY_UI_DIR}/src/auth/onboarding.py"; then
    echo -e "${GREEN}✓${NC} Trust profile creation integrated into vendor flow"
else
    echo -e "${RED}✗${NC} Trust profile creation not called"
    exit 1
fi

echo ""
echo "Step 3: Checking test updates..."
echo "-------------------------------------"

# Check selectTrustProfile helper
if grep -q "async selectTrustProfile" "${MARTY_UI_DIR}/tests/e2e/e2e-flows/onboarding.spec.js"; then
    echo -e "${GREEN}✓${NC} selectTrustProfile test helper added"
else
    echo -e "${RED}✗${NC} selectTrustProfile helper not found"
    exit 1
fi

# Check new test suite
if grep -q "Vendor Trust Profile Selection Step" "${MARTY_UI_DIR}/tests/e2e/e2e-flows/onboarding.spec.js"; then
    echo -e "${GREEN}✓${NC} Trust Profile test suite added"
else
    echo -e "${RED}✗${NC} Trust Profile tests not found"
    exit 1
fi

echo ""
echo "Step 4: Checking database models..."
echo "-------------------------------------"

# Check TrustFrameworkModel
if grep -q "class TrustFrameworkModel" "${MARTY_DIR}/src/digital_identity/infrastructure/persistence/models.py"; then
    echo -e "${GREEN}✓${NC} TrustFrameworkModel exists"
else
    echo -e "${RED}✗${NC} TrustFrameworkModel not found"
    exit 1
fi

# Check OrganizationTrustProfileModel
if grep -q "class OrganizationTrustProfileModel" "${MARTY_DIR}/src/digital_identity/infrastructure/persistence/models.py"; then
    echo -e "${GREEN}✓${NC} OrganizationTrustProfileModel exists"
else
    echo -e "${RED}✗${NC} OrganizationTrustProfileModel not found"
    exit 1
fi

echo ""
echo "======================================"
echo -e "${GREEN}All verification checks passed!${NC}"
echo "======================================"
echo ""
echo "Next steps:"
echo "1. Run Playwright tests:"
echo "   cd marty-ui && npm run test:e2e -- onboarding.spec.js"
echo ""
echo "2. Test manually:"
echo "   - Start the app: npm run dev"
echo "   - Go to /onboarding"
echo "   - Select Vendor role"
echo "   - Fill organization form"
echo "   - Verify trust profile step appears"
echo "   - Select a framework (ICAO/EUDI/AAMVA/CUSTOM)"
echo "   - Complete onboarding"
echo "   - Check database for organization_trust_profiles entry"
echo ""
echo "3. Verify database query:"
echo "   SELECT otp.*, tf.code, tf.display_name"
echo "   FROM organization_trust_profiles otp"
echo "   JOIN trust_frameworks tf ON otp.framework_id = tf.id"
echo "   WHERE otp.organization_id = '<your-org-id>';"
echo ""
