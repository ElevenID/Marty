"""OpenBao Transit secrets engine KMS provider.

Implements ``KMSProviderInterface`` using OpenBao's (or HashiCorp Vault's)
Transit secrets engine for remote key management and signing.  This enables
the BYOK (Bring Your Own Key) credential issuance flow where private keys
never leave the KMS boundary.

Configuration
-------------
The provider requires:
  - ``bao_addr``: OpenBao server URL (e.g. ``http://127.0.0.1:8200``)
  - ``bao_token``: authentication token (dev) or AppRole credentials (prod)
  - ``transit_mount``: mount path for the transit engine (default ``transit``)
"""

from __future__ import annotations

import base64
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from .kms_provider import (
    KMSProvider,
    KMSProviderInterface,
    KeyMaterial,
)
from .role_separation import (
    CryptoRole,
    KeyIdentity,
    RoleSeparationEnforcer,
)

logger = logging.getLogger(__name__)

# Map our algorithm names to OpenBao Transit key types
_ALGORITHM_TO_TRANSIT_TYPE: dict[str, str] = {
    "ES256": "ecdsa-p256",
    "EC": "ecdsa-p256",
    "ECDSA": "ecdsa-p256",
    "P-256": "ecdsa-p256",
    "ES384": "ecdsa-p384",
    "P-384": "ecdsa-p384",
    "EdDSA": "ed25519",
    "Ed25519": "ed25519",
    "RSA": "rsa-2048",
    "RSA2048": "rsa-2048",
    "RSA4096": "rsa-4096",
    "RS256": "rsa-2048",
}

# Map Transit key types to signing hash algorithms
_TRANSIT_TYPE_TO_HASH: dict[str, str] = {
    "ecdsa-p256": "sha2-256",
    "ecdsa-p384": "sha2-384",
    "ed25519": "none",  # EdDSA doesn't use separate hashing
    "rsa-2048": "sha2-256",
    "rsa-4096": "sha2-256",
}

# Map Transit key types to signature algorithm for SOD/CMS
_TRANSIT_TYPE_TO_SIG_ALG: dict[str, str] = {
    "ecdsa-p256": "pkcs1v15",
    "ecdsa-p384": "pkcs1v15",
    "rsa-2048": "pkcs1v15",
    "rsa-4096": "pkcs1v15",
}


class OpenBaoTransitProvider(KMSProviderInterface):
    """KMS provider backed by OpenBao/Vault Transit secrets engine."""

    def __init__(
        self,
        bao_addr: str = "http://127.0.0.1:8200",
        bao_token: str | None = None,
        transit_mount: str = "transit",
        *,
        timeout: float = 10.0,
    ):
        self._addr = bao_addr.rstrip("/")
        self._mount = transit_mount
        self._timeout = timeout
        self._headers: dict[str, str] = {}
        if bao_token:
            self._headers["X-Vault-Token"] = bao_token
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._addr,
                headers=self._headers,
                timeout=self._timeout,
            )
        return self._client

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def _transit_url(self, action: str, key_name: str) -> str:
        return f"/v1/{self._mount}/{action}/{key_name}"

    # -----------------------------------------------------------------
    # KMSProviderInterface implementation
    # -----------------------------------------------------------------

    async def generate_key(
        self, key_identity: KeyIdentity, algorithm: str, **kwargs: Any
    ) -> KeyMaterial:
        transit_type = _ALGORITHM_TO_TRANSIT_TYPE.get(algorithm.upper())
        if transit_type is None:
            msg = f"Unsupported algorithm for Transit engine: {algorithm}"
            raise ValueError(msg)

        key_name = key_identity.full_key_id
        client = await self._get_client()

        # Create the key in Transit
        resp = await client.post(
            self._transit_url("keys", key_name),
            json={
                "type": transit_type,
                "exportable": kwargs.get("exportable", False),
                "allow_plaintext_backup": False,
            },
        )
        resp.raise_for_status()

        # Read back key metadata + public key
        resp = await client.get(self._transit_url("keys", key_name))
        resp.raise_for_status()
        key_data = resp.json().get("data", {})

        # Extract the latest version's public key
        keys = key_data.get("keys", {})
        latest_version = str(key_data.get("latest_version", 1))
        public_key_pem = b""
        if latest_version in keys:
            pk = keys[latest_version].get("public_key", "")
            if pk:
                public_key_pem = pk.encode("utf-8")

        return KeyMaterial(
            key_identity=key_identity,
            algorithm=algorithm,
            public_key_pem=public_key_pem,
            provider=KMSProvider.HASHICORP_VAULT,
            provider_key_id=key_name,
            created_at=datetime.now(timezone.utc),
            metadata={
                "transit_type": transit_type,
                "transit_mount": self._mount,
                **kwargs,
            },
        )

    async def sign(
        self,
        key_identity: KeyIdentity,
        data: bytes,
        algorithm: str = "SHA256",
    ) -> bytes:
        RoleSeparationEnforcer.validate_key_operation(
            key_identity, "sign", key_identity.role
        )

        key_name = key_identity.full_key_id
        client = await self._get_client()

        # Determine hash algorithm from key type metadata
        # First, read key info to get the transit type
        resp = await client.get(self._transit_url("keys", key_name))
        resp.raise_for_status()
        key_data = resp.json().get("data", {})
        transit_type = key_data.get("type", "ecdsa-p256")

        hash_alg = _TRANSIT_TYPE_TO_HASH.get(transit_type, "sha2-256")

        # Base64-encode the input
        input_b64 = base64.b64encode(data).decode("ascii")

        sign_payload: dict[str, Any] = {"input": input_b64}
        if hash_alg != "none":
            sign_payload["hash_algorithm"] = hash_alg
            # For pre-hashed data, set prehashed=true
            sign_payload["prehashed"] = False

        # Sign via Transit
        resp = await client.post(
            self._transit_url("sign", key_name),
            json=sign_payload,
        )
        resp.raise_for_status()

        signature_str = resp.json().get("data", {}).get("signature", "")
        # Transit returns "vault:v1:base64signature"
        parts = signature_str.split(":")
        if len(parts) >= 3:
            sig_b64 = parts[2]
        else:
            msg = f"Unexpected signature format from Transit: {signature_str}"
            raise ValueError(msg)

        return base64.b64decode(sig_b64)

    async def encrypt(
        self,
        key_identity: KeyIdentity,
        plaintext: bytes,
        algorithm: str = "AES-256-GCM",
    ) -> bytes:
        key_name = key_identity.full_key_id
        client = await self._get_client()

        input_b64 = base64.b64encode(plaintext).decode("ascii")
        resp = await client.post(
            self._transit_url("encrypt", key_name),
            json={"plaintext": input_b64},
        )
        resp.raise_for_status()

        ciphertext = resp.json().get("data", {}).get("ciphertext", "")
        return ciphertext.encode("utf-8")

    async def decrypt(
        self,
        key_identity: KeyIdentity,
        ciphertext: bytes,
        algorithm: str = "AES-256-GCM",
    ) -> bytes:
        key_name = key_identity.full_key_id
        client = await self._get_client()

        resp = await client.post(
            self._transit_url("decrypt", key_name),
            json={"ciphertext": ciphertext.decode("utf-8")},
        )
        resp.raise_for_status()

        plaintext_b64 = resp.json().get("data", {}).get("plaintext", "")
        return base64.b64decode(plaintext_b64)

    async def get_public_key(self, key_identity: KeyIdentity) -> bytes:
        key_name = key_identity.full_key_id
        client = await self._get_client()

        resp = await client.get(self._transit_url("keys", key_name))
        resp.raise_for_status()

        key_data = resp.json().get("data", {})
        keys = key_data.get("keys", {})
        latest_version = str(key_data.get("latest_version", 1))

        if latest_version in keys:
            pk = keys[latest_version].get("public_key", "")
            if pk:
                return pk.encode("utf-8")

        msg = f"No public key available for {key_name}"
        raise ValueError(msg)

    async def delete_key(self, key_identity: KeyIdentity) -> bool:
        key_name = key_identity.full_key_id
        client = await self._get_client()

        # Must set deletion_allowed first
        await client.post(
            self._transit_url("keys", f"{key_name}/config"),
            json={"deletion_allowed": True},
        )

        resp = await client.delete(self._transit_url("keys", key_name))
        return resp.status_code == 204

    async def list_keys(
        self, role: CryptoRole | None = None
    ) -> list[KeyMaterial]:
        client = await self._get_client()

        resp = await client.request(
            "LIST", f"/v1/{self._mount}/keys"
        )
        if resp.status_code == 404:
            return []  # No keys
        resp.raise_for_status()

        key_names = resp.json().get("data", {}).get("keys", [])

        results: list[KeyMaterial] = []
        for name in key_names:
            if role and not name.startswith(f"{role.value}:"):
                continue
            # Read each key to get metadata
            key_resp = await client.get(self._transit_url("keys", name))
            if key_resp.status_code != 200:
                continue
            key_data = key_resp.json().get("data", {})
            keys = key_data.get("keys", {})
            latest_version = str(key_data.get("latest_version", 1))
            public_key_pem = b""
            if latest_version in keys:
                pk = keys[latest_version].get("public_key", "")
                if pk:
                    public_key_pem = pk.encode("utf-8")

            results.append(
                KeyMaterial(
                    key_identity=KeyIdentity.parse(name),
                    algorithm=key_data.get("type", "unknown"),
                    public_key_pem=public_key_pem,
                    provider=KMSProvider.HASHICORP_VAULT,
                    provider_key_id=name,
                    created_at=datetime.now(timezone.utc),
                )
            )

        return results

    async def key_exists(self, key_identity: KeyIdentity) -> bool:
        key_name = key_identity.full_key_id
        client = await self._get_client()

        resp = await client.get(self._transit_url("keys", key_name))
        return resp.status_code == 200
