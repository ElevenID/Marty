#!/usr/bin/env python3
"""
Simple API Verification Script for Document Processing API
"""

import sys

import requests

BASE_URL = "http://localhost:8080"
TIMEOUT = 10


def test_health() -> bool:
    """Test health endpoints"""
    try:
        # Test ping
        response = requests.get(f"{BASE_URL}/api/ping", timeout=TIMEOUT)
        if response.status_code != 200 or response.text.strip() != "OK":
            print("❌ Ping endpoint failed")
            return False
        print("✅ Ping endpoint working")

        # Test health
        response = requests.get(f"{BASE_URL}/api/health", timeout=TIMEOUT)
        if response.status_code != 200:
            print("❌ Health endpoint failed")
            return False

        health_data = response.json()
        if health_data.get("status") != "ready":
            print("❌ Service not ready")
            return False
        print("✅ Health endpoint working")

    except requests.RequestException as e:
        print(f"❌ Health test failed: {e}")
        return False
    else:
        return True


def test_api() -> bool:
    """Test main API endpoint"""
    try:
        payload = {
            "processParam": {"scenario": "Mrz"},
            "List": [{"ImageData": "dGVzdA=="}],
            "tag": "verification-test",
        }

        response = requests.post(f"{BASE_URL}/api/process", json=payload, timeout=TIMEOUT)

        if response.status_code != 200:
            print(f"❌ API endpoint failed: {response.status_code}")
            return False

        result = response.json()

        # Basic structure validation
        if "transactionInfo" not in result or "containerList" not in result:
            print("❌ Invalid response structure")
            return False

        print("✅ API endpoint working")

    except requests.RequestException as e:
        print(f"❌ API test failed: {e}")
        return False
    else:
        return True


def main() -> int:
    """Run verification tests"""
    print("🔍 Document Processing API Verification")
    print("=" * 40)

    all_passed = True

    if not test_health():
        all_passed = False

    if not test_api():
        all_passed = False

    print("\n" + "=" * 40)
    if all_passed:
        print("🎉 All verification tests passed!")
        return 0
    print("❌ Some verification tests failed!")
    return 1


if __name__ == "__main__":
    sys.exit(main())
