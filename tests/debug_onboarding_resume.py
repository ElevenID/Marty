#!/usr/bin/env python3
"""
Quick debugging script to test onboarding resume scenario.

This simulates the exact flow that's failing:
1. User creates org at step 1
2. User logs out
3. User logs back in
4. User tries to continue onboarding -> gets 403

Run this with:
    python tests/debug_onboarding_resume.py
"""

import asyncio
import sys
import uuid
from datetime import datetime

import httpx


async def debug_onboarding_resume():
    """Debug the onboarding resume issue."""
    
    API_BASE = "http://localhost:8000"
    
    # Generate unique test data
    test_id = uuid.uuid4().hex[:8]
    test_email = f"debug-vendor-{test_id}@example.com"
    org_name = f"Debug Org {test_id}"
    
    print("=" * 80)
    print("ONBOARDING RESUME DEBUG SCRIPT")
    print("=" * 80)
    print(f"Test Email: {test_email}")
    print(f"Org Name: {org_name}")
    print(f"API Base: {API_BASE}")
    print()
    
    async with httpx.AsyncClient(base_url=API_BASE, timeout=30.0) as client:
        
        # Step 1: Register user
        print("[1/7] Registering new user...")
        try:
            register_resp = await client.post(
                "/auth/register",
                json={
                    "email": test_email,
                    "password": "Test123!@#",
                    "given_name": "Debug",
                    "family_name": "User",
                },
            )
            
            if register_resp.status_code != 200:
                print(f"❌ Registration failed: {register_resp.status_code}")
                print(f"   Response: {register_resp.text}")
                return False
            
            user_data = register_resp.json()
            user_id = user_data.get("user_id")
            
            # Extract session cookie
            session_cookie = register_resp.cookies.get("session_id")
            
            print(f"✓ User registered: {user_id}")
            print(f"✓ Session cookie: {session_cookie[:20]}..." if session_cookie else "✓ No session cookie")
            
        except Exception as e:
            print(f"❌ Exception during registration: {e}")
            return False
        
        # Step 2: Check onboarding status
        print("\n[2/7] Checking onboarding status...")
        try:
            status_resp = await client.get("/api/onboarding/status")
            
            if status_resp.status_code != 200:
                print(f"❌ Status check failed: {status_resp.status_code}")
                print(f"   Response: {status_resp.text}")
                return False
            
            status_data = status_resp.json()
            print(f"✓ Needs onboarding: {status_data.get('needs_onboarding')}")
            print(f"✓ Current user type: {status_data.get('user_type')}")
            print(f"✓ Has organization: {status_data.get('organization_id') is not None}")
            
        except Exception as e:
            print(f"❌ Exception checking status: {e}")
            return False
        
        # Step 3: Create organization (first onboarding step)
        print(f"\n[3/7] Creating organization '{org_name}'...")
        try:
            create_org_resp = await client.post(
                "/api/onboarding/complete",
                json={
                    "user_type": "vendor",
                    "organization_name": org_name,
                    "organization_description": "Debug test organization",
                    "is_discoverable": False,
                    "membership_mode": "invite_only",
                },
            )
            
            if create_org_resp.status_code != 200:
                print(f"❌ Organization creation failed: {create_org_resp.status_code}")
                print(f"   Response: {create_org_resp.text}")
                return False
            
            org_data = create_org_resp.json()
            org_id = org_data.get("organization_id")
            invite_code = org_data.get("invite_code")
            
            print(f"✓ Organization created: {org_id}")
            print(f"✓ Invite code: {invite_code}")
            print(f"✓ Organization name: {org_data.get('organization_name')}")
            
        except Exception as e:
            print(f"❌ Exception creating organization: {e}")
            return False
        
        # Step 4: Check status after org creation
        print("\n[4/7] Checking status after org creation...")
        try:
            status_resp2 = await client.get("/api/onboarding/status")
            
            if status_resp2.status_code != 200:
                print(f"❌ Status check failed: {status_resp2.status_code}")
                return False
            
            status_data2 = status_resp2.json()
            print(f"✓ Organization ID in session: {status_data2.get('organization_id')}")
            print(f"✓ Organization name in session: {status_data2.get('organization_name')}")
            print(f"✓ User type: {status_data2.get('user_type')}")
            print(f"✓ Onboarding completed: {status_data2.get('onboarding_completed')}")
            
        except Exception as e:
            print(f"❌ Exception checking status: {e}")
            return False
        
        # Step 5: Simulate logout by creating new HTTP client (clears cookies)
        print("\n[5/7] Simulating logout (clearing session)...")
        print("✓ Session cleared")
        
    # Step 6: Simulate login by creating new client and logging in
    print("\n[6/7] Simulating login (new session)...")
    async with httpx.AsyncClient(base_url=API_BASE, timeout=30.0) as client2:
        try:
            # Login with same credentials
            login_resp = await client2.post(
                "/auth/login",
                json={
                    "email": test_email,
                    "password": "Test123!@#",
                },
            )
            
            if login_resp.status_code not in [200, 302]:
                print(f"❌ Login failed: {login_resp.status_code}")
                print(f"   Response: {login_resp.text}")
                return False
            
            new_session_cookie = login_resp.cookies.get("session_id")
            print(f"✓ Logged in with new session")
            print(f"✓ New session cookie: {new_session_cookie[:20]}..." if new_session_cookie else "✓ No session cookie")
            
        except Exception as e:
            print(f"❌ Exception during login: {e}")
            return False
        
        # Check status in new session
        try:
            status_resp3 = await client2.get("/api/onboarding/status")
            
            if status_resp3.status_code != 200:
                print(f"❌ Status check failed: {status_resp3.status_code}")
                return False
            
            status_data3 = status_resp3.json()
            print(f"✓ Organization ID restored: {status_data3.get('organization_id')}")
            print(f"✓ Organization name restored: {status_data3.get('organization_name')}")
            print(f"✓ User type: {status_data3.get('user_type')}")
            
        except Exception as e:
            print(f"❌ Exception checking status: {e}")
            return False
        
        # Step 7: Try to continue onboarding (THIS IS WHERE IT FAILS)
        print(f"\n[7/7] Attempting to continue onboarding with org {org_id}...")
        print("      (This is where the 403 error occurs)")
        try:
            continue_resp = await client2.post(
                "/api/onboarding/complete",
                json={
                    "user_type": "vendor",
                    "organization_id": org_id,
                    "is_discoverable": True,
                    "membership_mode": "request_to_join",
                },
            )
            
            print(f"\n📊 Response Status: {continue_resp.status_code}")
            print(f"📊 Response Body: {continue_resp.text}")
            
            if continue_resp.status_code == 403:
                print("\n❌ GOT 403 FORBIDDEN - THIS IS THE BUG!")
                print("   The authorization check is incorrectly blocking resumed onboarding.")
                print("\n🔍 Debugging info:")
                print(f"   - Organization ID being accessed: {org_id}")
                print(f"   - User ID: {user_id}")
                print(f"   - This user SHOULD have access (they created the org)")
                return False
            elif continue_resp.status_code != 200:
                print(f"\n❌ Unexpected error: {continue_resp.status_code}")
                return False
            else:
                print("\n✅ SUCCESS! Onboarding continued without authorization error")
                continue_data = continue_resp.json()
                print(f"✓ Organization: {continue_data.get('organization_name')}")
                print(f"✓ Settings updated successfully")
                return True
            
        except Exception as e:
            print(f"❌ Exception continuing onboarding: {e}")
            import traceback
            traceback.print_exc()
            return False


async def main():
    """Run the debug script."""
    print(f"\nStarting debug at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    success = await debug_onboarding_resume()
    
    print("\n" + "=" * 80)
    if success:
        print("✅ TEST PASSED - Onboarding resume works correctly")
    else:
        print("❌ TEST FAILED - Onboarding resume is blocked (403 error)")
    print("=" * 80)
    print()
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
