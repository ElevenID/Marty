"""Managed-provider key vault abstraction; file-backed private custody is retired."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import hvac
from hvac.exceptions import VaultError

from marty_common.native_backends import NativeOperationError


class KeyVaultClient(Protocol):
    async def ensure_key(self, key_id: str, algorithm: str) -> None: ...

    async def sign(self, key_id: str, payload: bytes, algorithm: str) -> bytes: ...

    async def public_material(self, key_id: str) -> bytes: ...

    async def store_private_key(self, key_id: str, pem: bytes) -> None: ...

    async def load_private_key(self, key_id: str) -> bytes: ...


@dataclass(slots=True)
class KeyVaultConfig:
    provider: str
    file_path: str | None = None
    hsm_config_path: str | None = None
    vault_addr: str | None = None
    vault_auth_method: str = "token"  # "token" or "kubernetes"
    vault_role: str | None = None
    vault_mount_point: str = "transit"

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> KeyVaultConfig:
        return cls(
            provider=raw.get("provider", ""),
            file_path=raw.get("file_path"),
            hsm_config_path=raw.get("hsm_config_path"),
            vault_addr=raw.get("vault_addr"),
            vault_auth_method=raw.get("vault_auth_method", "token"),
            vault_role=raw.get("vault_role"),
            vault_mount_point=raw.get("vault_mount_point", "transit"),
        )


class FileKeyVaultClient:
    """Import-compatible rejection of retired file-backed private custody."""

    def __init__(self, base_path: str) -> None:
        raise NativeOperationError(
            "File-backed private-key custody is retired; use an explicit managed provider"
        )


class HashiCorpKeyVaultClient(KeyVaultClient):
    """
    HashiCorp Vault Transit Engine client for signing operations.
    
    Uses Vault's Transit secrets engine for cryptographic signing.
    Supports token and Kubernetes authentication.
    """
    
    def __init__(
        self,
        vault_addr: str,
        auth_method: str = "token",
        mount_point: str = "transit",
        role: str | None = None,
    ):
        """
        Initialize Vault client.
        
        Args:
            vault_addr: Vault server URL
            auth_method: "token" or "kubernetes" (explicit via VAULT_AUTH_METHOD env var)
            mount_point: Transit engine mount point
            role: Kubernetes role (for kubernetes auth)
        """
        self.vault_addr = vault_addr
        self.auth_method = auth_method
        self.mount_point = mount_point
        self.role = role
        
        self.client = hvac.Client(url=vault_addr)
        self._authenticated = False
    
    async def _ensure_authenticated(self) -> None:
        """Ensure client is authenticated based on auth method."""
        if self._authenticated and self.client.is_authenticated():
            return
        
        auth_method = self.auth_method or os.getenv("VAULT_AUTH_METHOD", "token")
        
        if auth_method == "token":
            token = os.getenv("VAULT_TOKEN")
            if not token:
                raise ValueError("VAULT_TOKEN environment variable not set")
            self.client.token = token
            
        elif auth_method == "kubernetes":
            role = self.role or os.getenv("VAULT_ROLE")
            if not role:
                raise ValueError("VAULT_ROLE not provided for Kubernetes auth")
            
            jwt_path = "/var/run/secrets/kubernetes.io/serviceaccount/token"
            jwt = Path(jwt_path).read_text().strip()
            
            response = await asyncio.to_thread(
                self.client.auth.kubernetes.login,
                role=role,
                jwt=jwt,
            )
            self.client.token = response["auth"]["client_token"]
            
        else:
            raise ValueError(f"Unsupported VAULT_AUTH_METHOD: {auth_method}")
        
        if not self.client.is_authenticated():
            raise RuntimeError(f"Vault authentication failed with method: {auth_method}")
        
        self._authenticated = True
    
    async def ensure_key(self, key_id: str, algorithm: str) -> None:
        """Ensure a signing key exists in Vault Transit."""
        await self._ensure_authenticated()
        
        # Map algorithm to Vault key types
        key_type_map = {
            "rsa": "rsa-2048",
            "rsa2048": "rsa-2048",
            "rsa4096": "rsa-4096",
            "ecdsa": "ecdsa-p256",
            "ecdsa-p256": "ecdsa-p256",
            "ecdsa-p384": "ecdsa-p384",
            "ed25519": "ed25519",
            "eddsa": "ed25519",
        }
        
        vault_key_type = key_type_map.get(algorithm.lower(), "ecdsa-p256")
        
        try:
            # Check if key exists
            await asyncio.to_thread(
                self.client.secrets.transit.read_key,
                name=key_id,
                mount_point=self.mount_point,
            )
        except VaultError:
            # Create key
            await asyncio.to_thread(
                self.client.secrets.transit.create_key,
                name=key_id,
                key_type=vault_key_type,
                mount_point=self.mount_point,
            )
    
    async def sign(self, key_id: str, payload: bytes, algorithm: str) -> bytes:
        """Sign payload using Vault Transit."""
        await self._ensure_authenticated()
        
        # Vault expects base64-encoded input
        import base64
        b64_payload = base64.b64encode(payload).decode()
        
        response = await asyncio.to_thread(
            self.client.secrets.transit.sign_data,
            name=key_id,
            hash_input=b64_payload,
            mount_point=self.mount_point,
        )
        
        # Parse signature (format: "vault:v1:BASE64SIG")
        signature_b64 = response["data"]["signature"].split(":")[-1]
        return base64.b64decode(signature_b64)
    
    async def public_material(self, key_id: str) -> bytes:
        """Get public key material from Vault Transit."""
        await self._ensure_authenticated()
        
        response = await asyncio.to_thread(
            self.client.secrets.transit.read_key,
            name=key_id,
            mount_point=self.mount_point,
        )
        
        # Get latest version public key
        keys = response["data"]["keys"]
        latest_version = str(response["data"]["latest_version"])
        public_key_pem = keys[latest_version]["public_key"]
        
        return public_key_pem.encode()
    
    async def store_private_key(self, key_id: str, pem: bytes) -> None:
        """Not supported for Vault Transit (keys are stored internally)."""
        raise NotImplementedError(
            "Vault Transit does not support importing private keys. "
            "Use ensure_key() to create keys in Vault."
        )
    
    async def load_private_key(self, key_id: str) -> bytes:
        """Not supported for Vault Transit (private keys never leave Vault)."""
        raise NotImplementedError(
            "Vault Transit private keys cannot be exported. "
            "Use sign() for signing operations."
        )


def build_key_vault_client(config: KeyVaultConfig) -> KeyVaultClient:
    if not isinstance(config.provider, str) or not config.provider.strip():
        raise ValueError("An explicit managed key-vault provider is required")
    provider = config.provider.strip().lower()
    if provider == "file":
        raise NativeOperationError(
            "File-backed private-key custody is retired; use an explicit managed provider"
        )
    if provider in ("hashicorp", "vault"):
        vault_addr = config.vault_addr or os.getenv("VAULT_ADDR")
        if not vault_addr:
            msg = "vault_addr or VAULT_ADDR environment variable required for HashiCorp provider"
            raise ValueError(msg)
        return HashiCorpKeyVaultClient(
            vault_addr=vault_addr,
            auth_method=config.vault_auth_method,
            mount_point=config.vault_mount_point,
            role=config.vault_role,
        )
    msg = f"Provider {config.provider} is not implemented yet"
    raise NotImplementedError(msg)
