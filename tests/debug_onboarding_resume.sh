#!/bin/bash
#
# Quick debugging script to test onboarding resume scenario using curl.
# This simulates the exact flow that's failing.
#

set -e

API_BASE="http://localhost:8000"
TEST_ID=$(uuidgen | cut -d'-' -f1 | tr '[:upper:]' '[:lower:]')
TEST_EMAIL="debug-vendor-${TEST_ID}@example.com"
ORG_NAME="Debug Org ${TEST_ID}"
COOKIE_JAR=$(mktemp)

echo "================================================================================"
echo "ONBOARDING RESUME DEBUG SCRIPT"
echo "================================================================================"
echo "Test Email: $TEST_EMAIL"
echo "Org Name: $ORG_NAME"
echo "API Base: $API_BASE"
echo "Cookie Jar: $COOKIE_JAR"
echo ""

# Step 1: Register user
echo "[1/7] Registering new user..."
REGISTER_RESP=$(curl -s -w "\n%{http_code}" -c "$COOKIE_JAR" -X POST "$API_BASE/auth/register" \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"$TEST_EMAIL\",
    \"password\": \"Test123!@#\",
    \"given_name\": \"Debug\",
    \"family_name\": \"User\"
  }")

HTTP_CODE=$(echo "$REGISTER_RESP" | tail -n1)
BODY=$(echo "$REGISTER_RESP" | sed '$d')

if [ "$HTTP_CODE" != "200" ]; then
  echo "❌ Registration failed: $HTTP_CODE"
  echo "   Response: $BODY"
  exit 1
fi

USER_ID=$(echo "$BODY" | jq -r '.user_id')
echo "✓ User registered: $USER_ID"

# Step 2: Check onboarding status
echo ""
echo "[2/7] Checking onboarding status..."
STATUS_RESP=$(curl -s -w "\n%{http_code}" -b "$COOKIE_JAR" "$API_BASE/api/onboarding/status")
HTTP_CODE=$(echo "$STATUS_RESP" | tail -n1)
BODY=$(echo "$STATUS_RESP" | sed '$d')

if [ "$HTTP_CODE" != "200" ]; then
  echo "❌ Status check failed: $HTTP_CODE"
  exit 1
fi

NEEDS_ONBOARDING=$(echo "$BODY" | jq -r '.needs_onboarding')
USER_TYPE=$(echo "$BODY" | jq -r '.user_type')
echo "✓ Needs onboarding: $NEEDS_ONBOARDING"
echo "✓ Current user type: $USER_TYPE"

# Step 3: Create organization
echo ""
echo "[3/7] Creating organization '$ORG_NAME'..."
CREATE_ORG_RESP=$(curl -s -w "\n%{http_code}" -b "$COOKIE_JAR" -c "$COOKIE_JAR" -X POST "$API_BASE/api/onboarding/complete" \
  -H "Content-Type: application/json" \
  -d "{
    \"user_type\": \"vendor\",
    \"organization_name\": \"$ORG_NAME\",
    \"organization_description\": \"Debug test organization\",
    \"is_discoverable\": false,
    \"membership_mode\": \"invite_only\"
  }")

HTTP_CODE=$(echo "$CREATE_ORG_RESP" | tail -n1)
BODY=$(echo "$CREATE_ORG_RESP" | sed '$d')

if [ "$HTTP_CODE" != "200" ]; then
  echo "❌ Organization creation failed: $HTTP_CODE"
  echo "   Response: $BODY"
  exit 1
fi

ORG_ID=$(echo "$BODY" | jq -r '.organization_id')
INVITE_CODE=$(echo "$BODY" | jq -r '.invite_code')
echo "✓ Organization created: $ORG_ID"
echo "✓ Invite code: $INVITE_CODE"

# Step 4: Check status after org creation
echo ""
echo "[4/7] Checking status after org creation..."
STATUS_RESP2=$(curl -s -w "\n%{http_code}" -b "$COOKIE_JAR" "$API_BASE/api/onboarding/status")
HTTP_CODE=$(echo "$STATUS_RESP2" | tail -n1)
BODY=$(echo "$STATUS_RESP2" | sed '$d')

if [ "$HTTP_CODE" != "200" ]; then
  echo "❌ Status check failed: $HTTP_CODE"
  exit 1
fi

echo "✓ Organization ID in session: $(echo "$BODY" | jq -r '.organization_id')"
echo "✓ Organization name in session: $(echo "$BODY" | jq -r '.organization_name')"
echo "✓ User type: $(echo "$BODY" | jq -r '.user_type')"

# Step 5: Simulate logout
echo ""
echo "[5/7] Simulating logout (clearing session cookies)..."
rm -f "$COOKIE_JAR"
COOKIE_JAR=$(mktemp)
echo "✓ Session cleared"

# Step 6: Simulate login
echo ""
echo "[6/7] Simulating login (new session)..."
LOGIN_RESP=$(curl -s -w "\n%{http_code}" -c "$COOKIE_JAR" -X POST "$API_BASE/auth/login" \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"$TEST_EMAIL\",
    \"password\": \"Test123!@#\"
  }")

HTTP_CODE=$(echo "$LOGIN_RESP" | tail -n1)

if [ "$HTTP_CODE" != "200" ] && [ "$HTTP_CODE" != "302" ]; then
  echo "❌ Login failed: $HTTP_CODE"
  exit 1
fi

echo "✓ Logged in with new session"

# Check status in new session
STATUS_RESP3=$(curl -s -w "\n%{http_code}" -b "$COOKIE_JAR" "$API_BASE/api/onboarding/status")
HTTP_CODE=$(echo "$STATUS_RESP3" | tail -n1)
BODY=$(echo "$STATUS_RESP3" | sed '$d')

if [ "$HTTP_CODE" != "200" ]; then
  echo "❌ Status check failed: $HTTP_CODE"
  exit 1
fi

echo "✓ Organization ID restored: $(echo "$BODY" | jq -r '.organization_id')"
echo "✓ Organization name restored: $(echo "$BODY" | jq -r '.organization_name')"

# Step 7: Try to continue onboarding (THIS IS WHERE IT FAILS)
echo ""
echo "[7/7] Attempting to continue onboarding with org $ORG_ID..."
echo "      (This is where the 403 error occurs)"

CONTINUE_RESP=$(curl -s -w "\n%{http_code}" -b "$COOKIE_JAR" -X POST "$API_BASE/api/onboarding/complete" \
  -H "Content-Type: application/json" \
  -d "{
    \"user_type\": \"vendor\",
    \"organization_id\": \"$ORG_ID\",
    \"is_discoverable\": true,
    \"membership_mode\": \"request_to_join\"
  }")

HTTP_CODE=$(echo "$CONTINUE_RESP" | tail -n1)
BODY=$(echo "$CONTINUE_RESP" | sed '$d')

echo ""
echo "📊 Response Status: $HTTP_CODE"
echo "📊 Response Body: $BODY"

# Cleanup
rm -f "$COOKIE_JAR"

echo ""
echo "================================================================================"
if [ "$HTTP_CODE" == "403" ]; then
  echo "❌ TEST FAILED - GOT 403 FORBIDDEN"
  echo "   The authorization check is incorrectly blocking resumed onboarding."
  echo ""
  echo "🔍 Debugging info:"
  echo "   - Organization ID being accessed: $ORG_ID"
  echo "   - User ID: $USER_ID"
  echo "   - This user SHOULD have access (they created the org)"
  echo "================================================================================"
  exit 1
elif [ "$HTTP_CODE" != "200" ]; then
  echo "❌ TEST FAILED - Unexpected error: $HTTP_CODE"
  echo "================================================================================"
  exit 1
else
  echo "✅ TEST PASSED - Onboarding resume works correctly"
  echo "================================================================================"
  exit 0
fi
