# Onboarding Resume Testing Guide

## Problem
Users get "Not authorized for this organization" error when resuming incomplete onboarding after logging out.

## Scenario to Test

### Step-by-Step Manual Test

1. **Initial Setup - Create Organization**
   - Log in to the application (http://localhost:3000)
   - Start vendor onboarding
   - At Step 1 (Organization Settings):
     - Choose "Create New Organization"
     - Enter organization name: "Test Resume Org"
     - Click "Create & Continue"
   - Observe: Organization is created, you move to Step 2 (Use Cases)
   - **Do NOT complete all steps**

2. **Logout**
   - Click logout button
   - Verify you're logged out

3. **Login Again**
   - Log back in with the same credentials
   - Observe: You should be redirected to continue onboarding

4. **Resume Onboarding**
   - At Step 1, your organization should already be selected
   - Try to click "Save & Continue" or proceed to next steps
   - **EXPECTED**: Should work without errors
   - **ACTUAL (BUG)**: Gets 403 "Not authorized for this organization"

## Technical Details

### What's Happening

1. **First Session (Org Creation)**:
   ```
   POST /api/onboarding/complete
   Body: {
     user_type: "vendor",
     organization_name: "Test Resume Org",
     ...
   }
   ```
   - Creates organization in Keycloak
   - Adds user to organization
   - Sets session: `organization_id`, `onboarding_completed`
   - Sets organization claim: `{org_id: {name: "..."}}`

2. **After Logout/Login**:
   - Session restored with user attributes
   - `organization_id` is in session
   - `organization` claim is in session
   - `onboarding_completed` timestamp exists

3. **Resume Attempt**:
   ```
   POST /api/onboarding/complete
   Body: {
     user_type: "vendor",
     organization_id: "existing-org-id",
     ...
   }
   ```
   - **Authorization Check** (in `onboarding.py` line ~800):
     ```python
     session_org_id = session.get("organization_id")
     if session_org_id and session_org_id != org_id:
         raise HTTPException(403, "Not authorized")
     
     # Check organization claim
     user_orgs = await keycloak.get_user_organizations(user_id)
     if org_id not in [o["id"] for o in user_orgs]:
         raise HTTPException(403, "Not authorized")
     ```

### Root Cause Hypotheses

1. **Hypothesis 1: Keycloak Membership Not Returning**
   - `keycloak.get_user_organizations(user_id)` returns empty list
   - User was added to org but Keycloak doesn't reflect it immediately
   - **Test**: Add logging to see what `get_user_organizations` returns

2. **Hypothesis 2: Session Organization ID Mismatch**
   - `session_org_id` and `org_id` from request don't match
   - Possibly due to UUID format differences or encoding
   - **Test**: Add logging to compare both values

3. **Hypothesis 3: Session Not Properly Restored**
   - After login, session doesn't have `organization_id` set
   - Authorization check fails because session is incomplete
   - **Test**: Check `/api/onboarding/status` response after login

## Debugging Steps

### 1. Add Logging to Authorization Check

Edit `marty-ui/src/auth/onboarding.py` around line 800:

```python
if request_data.organization_id:
    org_id = request_data.organization_id
    session_org_id = session.get("organization_id")
    
    # DEBUG LOGGING
    print(f"🔍 DEBUG: Authorization check")
    print(f"  - Requested org_id: {org_id}")
    print(f"  - Session org_id: {session_org_id}")
    print(f"  - User ID: {user_id}")
    print(f"  - Session keys: {list(session.keys())}")
    
    # Check Keycloak membership
    try:
        user_orgs = await keycloak.get_user_organizations(user_id)
        user_org_ids = [org["id"] for org in user_orgs if org.get("id")]
        
        print(f"  - Keycloak orgs: {user_org_ids}")
        print(f"  - Is member: {org_id in user_org_ids}")
        
    except Exception as e:
        print(f"  - Keycloak check failed: {e}")
```

### 2. Check Session Contents

After login, before attempting to resume:
- Open browser dev tools → Network tab
- Call: `GET http://localhost:8000/api/onboarding/status`
- Check response body for:
  - `organization_id`
  - `organization_name`
  - `onboarding_completed`

### 3. Check Keycloak Directly

1. Go to Keycloak admin console: http://localhost:8180
2. Login with admin credentials
3. Navigate to: Realm → marty → Users
4. Find your test user
5. Check "Organizations" tab
6. Verify user is member of the test organization

### 4. Check Docker Logs

```bash
cd /Volumes/Heart\ of\ Gold/Github/work/Marty
docker compose logs oid4vc-api --tail=100 -f
```

Watch for:
- Authorization check logs
- 403 errors
- Keycloak API calls

## Expected Behavior

After the fix in `onboarding.py`:
1. User creates org → gets added to Keycloak organization
2. User logs out → session cleared
3. User logs in → session restored with `organization_id`
4. User resumes → authorization check:
   - Checks `session_org_id` matches requested `org_id` ✓
   - Checks user is member via `keycloak.get_user_organizations()` ✓
   - Allows request ✓

## Testing the Fix

Run this manual test after backend restart:

```bash
# Restart backend to pick up code changes
cd /Volumes/Heart\ of\ Gold/Github/work/Marty
docker compose restart oid4vc-api

# Watch logs in one terminal
docker compose logs oid4vc-api -f

# In another terminal/browser:
# 1. Create new vendor account
# 2. Create organization at step 1
# 3. Logout
# 4. Login
# 5. Try to continue onboarding
# 6. Should NOT get 403 error
```

## Automated Test (When Python Environment Ready)

```bash
cd /Volumes/Heart\ of\ Gold/Github/work/Marty
python3 -m pytest tests/integration/test_onboarding_resume.py -v -s
```

## Quick Manual curl Test

```bash
# See tests/debug_onboarding_resume.sh for automated curl-based test
# Note: Requires proper authentication flow setup
```
