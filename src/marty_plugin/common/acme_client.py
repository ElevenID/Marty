"""
ACME client implementation for automated certificate management.

Supports Let's Encrypt staging and Pebble (for development) for internal TLS certificates.

This module uses Rust implementations from marty-verification for key
generation, providing better performance.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urljoin

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat
from cryptography.x509.oid import NameOID

from marty_plugin.common.crypto_bridge import (
    certificate_pem_to_der,
    get_certificate_info,
    rsa_generate as rust_rsa_generate,
)

logger = logging.getLogger(__name__)


class ACMEError(Exception):
    """Base exception for ACME-related errors."""

    pass


class ACMEClient:
    """
    ACME client for automated certificate management.

    Supports both Let's Encrypt staging and Pebble for development environments.
    """

    def __init__(
        self,
        directory_url: str,
        account_key_path: str | None = None,
        cert_storage_dir: str = "data/acme_certs",
        contact_email: str | None = None,
    ) -> None:
        """
        Initialize the ACME client.

        Args:
            directory_url: ACME directory URL (e.g., Let's Encrypt staging or Pebble)
            account_key_path: Path to account private key (will be generated if not exists)
            cert_storage_dir: Directory to store certificates and keys
            contact_email: Contact email for ACME account registration
        """
        self.directory_url = directory_url
        self.cert_storage_dir = Path(cert_storage_dir)
        self.cert_storage_dir.mkdir(parents=True, exist_ok=True)

        self.contact_email = contact_email
        self.account_key_path = Path(account_key_path or self.cert_storage_dir / "account.key")

        # ACME client state
        self.directory: dict[str, Any] = {}
        self.account_key: rsa.RSAPrivateKey | None = None
        self.account_url: str | None = None
        self.nonce: str | None = None

        # HTTP client
        self.client = httpx.AsyncClient(timeout=30.0)

    async def __aenter__(self) -> ACMEClient:
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.client.aclose()

    async def initialize(self) -> None:
        """Initialize the ACME client by loading directory and account."""
        await self._load_directory()
        await self._load_or_create_account_key()
        await self._get_account()

    async def _load_directory(self) -> None:
        """Load the ACME directory from the server."""
        try:
            response = await self.client.get(self.directory_url)
            response.raise_for_status()
            self.directory = response.json()
            logger.info("Loaded ACME directory from %s", self.directory_url)
        except Exception as e:
            raise ACMEError(f"Failed to load ACME directory: {e}") from e

    async def _load_or_create_account_key(self) -> None:
        """Load existing account key or create a new one."""
        if self.account_key_path.exists():
            # Load existing key
            key_data = self.account_key_path.read_bytes()
            self.account_key = serialization.load_pem_private_key(key_data, password=None)
            logger.info("Loaded existing account key from %s", self.account_key_path)
        else:
            # Generate new key using Rust
            private_key_pem, _ = rust_rsa_generate(2048)
            self.account_key_path.write_bytes(private_key_pem)
            self.account_key_path.chmod(0o600)
            # Load the key object for signing operations
            self.account_key = serialization.load_pem_private_key(private_key_pem, password=None)
            logger.info("Generated new account key (Rust) and saved to %s", self.account_key_path)

    async def _get_nonce(self) -> str:
        """Get a fresh nonce from the ACME server."""
        if not self.nonce:
            response = await self.client.head(self.directory["newNonce"])
            response.raise_for_status()
            self.nonce = response.headers["Replay-Nonce"]
        return self.nonce

    def _jose_header(self, url: str, kid: str | None = None) -> dict[str, Any]:
        """Create JOSE header for ACME requests."""
        header = {
            "alg": "RS256",
            "nonce": self.nonce,
            "url": url,
        }

        if kid:
            header["kid"] = kid
        else:
            # Include JWK for new account requests
            public_key = self.account_key.public_key()
            public_numbers = public_key.public_numbers()

            # Convert to base64url encoded integers
            n = self._int_to_base64url(public_numbers.n)
            e = self._int_to_base64url(public_numbers.e)

            header["jwk"] = {
                "kty": "RSA",
                "n": n,
                "e": e,
            }

        return header

    def _int_to_base64url(self, value: int) -> str:
        """Convert integer to base64url encoding."""
        # Convert to bytes, removing leading zeros
        byte_length = (value.bit_length() + 7) // 8
        value_bytes = value.to_bytes(byte_length, byteorder="big")
        return base64.urlsafe_b64encode(value_bytes).decode("ascii").rstrip("=")

    def _base64url_encode(self, data: bytes) -> str:
        """Base64url encode data."""
        return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")

    async def _sign_and_post(
        self, url: str, payload: dict[str, Any], kid: str | None = None
    ) -> httpx.Response:
        """Sign and POST a JOSE request to the ACME server."""
        await self._get_nonce()

        # Create protected header
        protected = self._jose_header(url, kid)
        protected_b64 = self._base64url_encode(json.dumps(protected).encode())

        # Create payload
        payload_b64 = self._base64url_encode(json.dumps(payload).encode())

        # Create signing input
        signing_input = f"{protected_b64}.{payload_b64}".encode()

        # Sign with account key
        signature = self.account_key.sign(
            signing_input,
            hashes.SHA256(),
        )
        signature_b64 = self._base64url_encode(signature)

        # Create JWS
        jws = {
            "protected": protected_b64,
            "payload": payload_b64,
            "signature": signature_b64,
        }

        # POST request
        response = await self.client.post(
            url, json=jws, headers={"Content-Type": "application/jose+json"}
        )

        # Update nonce from response
        if "Replay-Nonce" in response.headers:
            self.nonce = response.headers["Replay-Nonce"]

        return response

    async def _get_account(self) -> None:
        """Get or create ACME account."""
        # Try to find existing account first
        payload = {"onlyReturnExisting": True}
        response = await self._sign_and_post(self.directory["newAccount"], payload)

        if response.status_code == 200:
            # Existing account found
            self.account_url = response.headers["Location"]
            logger.info("Found existing ACME account: %s", self.account_url)
        elif response.status_code == 400:
            # Account doesn't exist, create new one
            await self._create_account()
        else:
            response.raise_for_status()

    async def _create_account(self) -> None:
        """Create a new ACME account."""
        payload = {
            "termsOfServiceAgreed": True,
        }

        if self.contact_email:
            payload["contact"] = [f"mailto:{self.contact_email}"]

        response = await self._sign_and_post(self.directory["newAccount"], payload)

        if response.status_code == 201:
            self.account_url = response.headers["Location"]
            logger.info("Created new ACME account: %s", self.account_url)
        else:
            response.raise_for_status()

    async def request_certificate(
        self,
        domain: str,
        challenge_type: str = "http-01",
        key_path: str | None = None,
        cert_path: str | None = None,
    ) -> tuple[str, str]:
        """
        Request a certificate for the given domain.

        Args:
            domain: Domain name for the certificate
            challenge_type: ACME challenge type ("http-01" or "dns-01")
            key_path: Path to save the private key (optional)
            cert_path: Path to save the certificate (optional)

        Returns:
            Tuple of (certificate_path, private_key_path)
        """
        logger.info("Requesting certificate for domain: %s", domain)

        # Generate certificate private key using Rust
        cert_key_pem, _ = rust_rsa_generate(2048)
        cert_key = serialization.load_pem_private_key(cert_key_pem, password=None)

        # Create CSR
        csr = self._create_csr(domain, cert_key)

        # Create order
        order_url = await self._create_order(domain)

        # Process authorizations
        await self._process_authorizations(order_url, challenge_type)

        # Finalize order
        certificate_pem = await self._finalize_order(order_url, csr)

        # Save certificate and key
        if not key_path:
            key_path = str(self.cert_storage_dir / f"{domain}.key")
        if not cert_path:
            cert_path = str(self.cert_storage_dir / f"{domain}.crt")

        # Save private key
        key_pem = cert_key.private_bytes(
            encoding=Encoding.PEM,
            format=PrivateFormat.PKCS8,
            encryption_algorithm=NoEncryption(),
        )
        Path(key_path).write_bytes(key_pem)
        Path(key_path).chmod(0o600)

        # Save certificate
        Path(cert_path).write_text(certificate_pem)

        logger.info("Certificate saved to %s, key saved to %s", cert_path, key_path)
        return cert_path, key_path

    def _create_csr(self, domain: str, private_key: rsa.RSAPrivateKey) -> bytes:
        """Create a Certificate Signing Request."""
        subject = x509.Name(
            [
                x509.NameAttribute(NameOID.COMMON_NAME, domain),
            ]
        )

        builder = x509.CertificateSigningRequestBuilder()
        builder = builder.subject_name(subject)
        builder = builder.add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName(domain),
                ]
            ),
            critical=False,
        )

        csr = builder.sign(private_key, hashes.SHA256())
        return csr.public_bytes(Encoding.DER)

    async def _create_order(self, domain: str) -> str:
        """Create an ACME order for the domain."""
        payload = {
            "identifiers": [{"type": "dns", "value": domain}],
        }

        response = await self._sign_and_post(
            self.directory["newOrder"], payload, kid=self.account_url
        )

        if response.status_code == 201:
            order_url = response.headers["Location"]
            logger.info("Created ACME order: %s", order_url)
            return order_url
        else:
            response.raise_for_status()

    async def _process_authorizations(self, order_url: str, challenge_type: str) -> None:
        """Process all authorizations for an order."""
        # Get order details
        response = await self.client.get(order_url)
        response.raise_for_status()
        order = response.json()

        for authz_url in order["authorizations"]:
            await self._process_authorization(authz_url, challenge_type)

    async def _process_authorization(self, authz_url: str, challenge_type: str) -> None:
        """Process a single authorization."""
        # Get authorization details
        response = await self.client.get(authz_url)
        response.raise_for_status()
        authz = response.json()

        if authz["status"] == "valid":
            logger.info("Authorization already valid for %s", authz["identifier"]["value"])
            return

        # Find the requested challenge
        challenge = None
        for chall in authz["challenges"]:
            if chall["type"] == challenge_type:
                challenge = chall
                break

        if not challenge:
            raise ACMEError(
                f"Challenge type {challenge_type} not supported for {authz['identifier']['value']}"
            )

        # Calculate key authorization
        key_authz = self._calculate_key_authorization(challenge["token"])

        if challenge_type == "http-01":
            await self._setup_http_challenge(challenge["token"], key_authz)
        else:
            raise ACMEError(f"Challenge type {challenge_type} not implemented")

        # Trigger challenge validation
        await self._trigger_challenge(challenge["url"])

        # Wait for challenge completion
        await self._wait_for_authorization(authz_url)

    def _calculate_key_authorization(self, token: str) -> str:
        """Calculate key authorization for challenge."""
        # Get account key thumbprint
        public_key = self.account_key.public_key()
        public_numbers = public_key.public_numbers()

        jwk = {
            "kty": "RSA",
            "n": self._int_to_base64url(public_numbers.n),
            "e": self._int_to_base64url(public_numbers.e),
        }

        # Create thumbprint
        jwk_json = json.dumps(jwk, sort_keys=True, separators=(",", ":"))
        thumbprint = hashlib.sha256(jwk_json.encode()).digest()
        thumbprint_b64 = self._base64url_encode(thumbprint)

        return f"{token}.{thumbprint_b64}"

    async def _setup_http_challenge(self, token: str, key_authz: str) -> None:
        """Set up HTTP-01 challenge response."""
        challenge_dir = self.cert_storage_dir / ".well-known" / "acme-challenge"
        challenge_dir.mkdir(parents=True, exist_ok=True)

        challenge_file = challenge_dir / token
        challenge_file.write_text(key_authz)

        logger.info("HTTP challenge set up at %s", challenge_file)

    async def _trigger_challenge(self, challenge_url: str) -> None:
        """Trigger challenge validation."""
        payload = {}  # Empty payload to trigger
        response = await self._sign_and_post(challenge_url, payload, kid=self.account_url)

        if response.status_code == 200:
            logger.info("Challenge triggered successfully")
        else:
            response.raise_for_status()

    async def _wait_for_authorization(self, authz_url: str, max_attempts: int = 60) -> None:
        """Wait for authorization to complete."""
        for attempt in range(max_attempts):
            response = await self.client.get(authz_url)
            response.raise_for_status()
            authz = response.json()

            if authz["status"] == "valid":
                logger.info("Authorization completed successfully")
                return
            elif authz["status"] == "invalid":
                raise ACMEError(f"Authorization failed: {authz}")

            # Wait before next check
            await asyncio.sleep(2)

        raise ACMEError("Authorization timed out")

    async def _finalize_order(self, order_url: str, csr: bytes) -> str:
        """Finalize the order and get the certificate."""
        # Get order details
        response = await self.client.get(order_url)
        response.raise_for_status()
        order = response.json()

        if order["status"] != "ready":
            raise ACMEError(f"Order not ready for finalization: {order['status']}")

        # Submit CSR
        payload = {
            "csr": self._base64url_encode(csr),
        }

        response = await self._sign_and_post(order["finalize"], payload, kid=self.account_url)
        response.raise_for_status()

        # Wait for certificate to be ready
        certificate_url = await self._wait_for_certificate(order_url)

        # Download certificate
        response = await self.client.get(certificate_url)
        response.raise_for_status()

        return response.text

    async def _wait_for_certificate(self, order_url: str, max_attempts: int = 60) -> str:
        """Wait for certificate to be ready and return certificate URL."""
        for attempt in range(max_attempts):
            response = await self.client.get(order_url)
            response.raise_for_status()
            order = response.json()

            if order["status"] == "valid" and "certificate" in order:
                return order["certificate"]
            elif order["status"] == "invalid":
                raise ACMEError(f"Order failed: {order}")

            await asyncio.sleep(2)

        raise ACMEError("Certificate generation timed out")

    async def renew_certificate(
        self,
        domain: str,
        cert_path: str,
        key_path: str,
        days_before_expiry: int = 30,
    ) -> bool:
        """
        Renew certificate if it's close to expiry.

        Args:
            domain: Domain name
            cert_path: Path to current certificate
            key_path: Path to current private key
            days_before_expiry: Renew if certificate expires within this many days

        Returns:
            True if certificate was renewed, False if renewal not needed
        """
        if not Path(cert_path).exists():
            logger.info("Certificate not found, requesting new one")
            await self.request_certificate(domain, key_path=key_path, cert_path=cert_path)
            return True

        # Check expiry date using Rust bindings
        cert_data = Path(cert_path).read_bytes()
        der_data = certificate_pem_to_der(cert_data.decode("utf-8"))
        cert_info = get_certificate_info(der_data)

        expiry_date = datetime.fromisoformat(cert_info["not_after"].replace("Z", "+00:00"))
        days_until_expiry = (expiry_date - datetime.now(timezone.utc)).days

        if days_until_expiry <= days_before_expiry:
            logger.info(
                "Certificate expires in %d days, renewing (threshold: %d days)",
                days_until_expiry,
                days_before_expiry,
            )
            await self.request_certificate(domain, key_path=key_path, cert_path=cert_path)
            return True
        else:
            logger.info(
                "Certificate expires in %d days, renewal not needed (threshold: %d days)",
                days_until_expiry,
                days_before_expiry,
            )
            return False


# Predefined ACME server configurations
ACME_SERVERS = {
    "letsencrypt-staging": "https://acme-staging-v02.api.letsencrypt.org/directory",
    "letsencrypt-production": "https://acme-v02.api.letsencrypt.org/directory",
    "pebble": "https://localhost:14000/dir",  # Default Pebble URL for development
}


async def create_acme_client(
    server: str = "letsencrypt-staging",
    contact_email: str | None = None,
    cert_storage_dir: str = "data/acme_certs",
) -> ACMEClient:
    """
    Create and initialize an ACME client.

    Args:
        server: ACME server ("letsencrypt-staging", "letsencrypt-production", "pebble", or custom URL)
        contact_email: Contact email for account registration
        cert_storage_dir: Directory to store certificates

    Returns:
        Initialized ACMEClient instance
    """
    directory_url = ACME_SERVERS.get(server, server)

    client = ACMEClient(
        directory_url=directory_url,
        contact_email=contact_email,
        cert_storage_dir=cert_storage_dir,
    )

    await client.initialize()
    return client


__all__ = [
    "ACMEClient",
    "ACMEError",
    "ACME_SERVERS",
    "create_acme_client",
]
