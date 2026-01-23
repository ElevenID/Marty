"""Key vault abstraction with file-backed and HashiCorp Vault implementations."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import hvac
from hvac.exceptions import VaultError

from marty_plugin.common import crypto_bridge


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
            provider=raw.get("provider", "file"),
            file_path=raw.get("file_path", "data/keys"),
            hsm_config_path=raw.get("hsm_config_path"),
            vault_addr=raw.get("vault_addr"),
            vault_auth_method=raw.get("vault_auth_method", "token"),
            vault_role=raw.get("vault_role"),
            vault_mount_point=raw.get("vault_mount_point", "transit"),
        )


class FileKeyVaultClient(KeyVaultClient):
    """Stores private keys on disk for non-production environments."""

    def __init__(self, base_path: str) -> None:
        self._path = Path(base_path)
        self._path.mkdir(parents=True, exist_ok=True)

    async def ensure_key(self, key_id: str, algorithm: str) -> None:
        key_file = self._path / f"{key_id}.pem"
        if key_file.exists():
            return
        private_key_der, _ = self._generate_key_material(algorithm)
        pem = crypto_bridge.save_private_key_pem(private_key_der)
        await self.store_private_key(key_id, pem.encode("utf-8"))

    def _generate_key_material(self, algorithm: str) -> tuple[bytes, bytes]:
        """Generate key material and return (private_der, public_der)."""
        key_algorithm = algorithm.lower()
        if key_algorithm.startswith("rsa"):
            key_size = int(key_algorithm.replace("rsa", "") or 2048)
            return crypto_bridge.rsa_generate(key_size)
        if key_algorithm.startswith("ecdsa"):
            curve_name = key_algorithm.replace("ecdsa-", "") or "p256"
            if curve_name == "p256":
                raw_priv, raw_pub = crypto_bridge.ecdsa_p256_generate()
                priv_der = crypto_bridge.raw_private_key_to_pkcs8(raw_priv, "P256")
                pub_der = crypto_bridge.raw_public_key_to_spki(raw_pub, "P256")
                return priv_der, pub_der
            elif curve_name == "p384":
                raw_priv, raw_pub = crypto_bridge.ecdsa_p384_generate()
                priv_der = crypto_bridge.raw_private_key_to_pkcs8(raw_priv, "P384")
                pub_der = crypto_bridge.raw_public_key_to_spki(raw_pub, "P384")
                return priv_der, pub_der
            else:
                msg = f"Unsupported EC curve: {curve_name}"
                raise ValueError(msg)
        if key_algorithm.startswith(("ed", "eddsa")):
            if "448" in key_algorithm:
                msg = "Ed448 is not supported, use Ed25519"
                raise ValueError(msg)
            raw_priv, raw_pub = crypto_bridge.ed25519_generate()
            priv_der = crypto_bridge.raw_private_key_to_pkcs8(raw_priv, "Ed25519")
            pub_der = crypto_bridge.raw_public_key_to_spki(raw_pub, "Ed25519")
            return priv_der, pub_der
        msg = f"Unsupported key algorithm: {algorithm}"
        raise ValueError(msg)

    async def sign(self, key_id: str, payload: bytes, algorithm: str) -> bytes:
        private_key_pem = await self.load_private_key(key_id)
        private_key_der = crypto_bridge.load_private_key_pem(private_key_pem.decode("utf-8"))
        key_type = crypto_bridge.detect_private_key_type(private_key_der)
        
        algo = algorithm.lower()
        if algo.startswith("rsa"):
            signature = await asyncio.to_thread(
                crypto_bridge.rsa_pkcs1_sha256_sign, private_key_der, payload
            )
            return bytes(signature)
        if algo.startswith("ecdsa"):
            # Extract raw key for ECDSA
            raw_key, _ = crypto_bridge.pkcs8_to_raw_private_key(private_key_der)
            if key_type == "P-256":
                signature = await asyncio.to_thread(
                    crypto_bridge.ecdsa_p256_sign, raw_key, payload
                )
            elif key_type == "P-384":
                signature = await asyncio.to_thread(
                    crypto_bridge.ecdsa_p384_sign, raw_key, payload
                )
            else:
                msg = f"Unsupported EC curve type: {key_type}"
                raise ValueError(msg)
            return bytes(signature)
        if algo.startswith(("ed", "eddsa")):
            raw_key, _ = crypto_bridge.pkcs8_to_raw_private_key(private_key_der)
            signature = await asyncio.to_thread(
                crypto_bridge.ed25519_sign, raw_key, payload
            )
            return bytes(signature)
        msg = f"Unsupported signing algorithm: {algorithm}"
        raise ValueError(msg)

    async def public_material(self, key_id: str) -> bytes:
        private_key_pem = await self.load_private_key(key_id)
        private_key_der = crypto_bridge.load_private_key_pem(private_key_pem.decode("utf-8"))
        public_key_der = crypto_bridge.extract_public_key(private_key_der)
        public_key_pem = crypto_bridge.save_public_key_pem(public_key_der)
        return public_key_pem.encode("utf-8")

    async def store_private_key(self, key_id: str, pem: bytes) -> None:
        key_file = self._path / f"{key_id}.pem"
        await asyncio.to_thread(key_file.write_bytes, pem)

    async def load_private_key(self, key_id: str) -> bytes:
        key_file = self._path / f"{key_id}.pem"
        if not key_file.exists():
            msg = f"Key {key_id} not found"
            raise FileNotFoundError(msg)
        return await asyncio.to_thread(key_file.read_bytes)


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
    provider = config.provider.lower()
    if provider == "file":
        if not config.file_path:
            msg = "file_path is required for file key vault provider"
            raise ValueError(msg)
        return FileKeyVaultClient(config.file_path)
    elif provider in ("hashicorp", "vault"):
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
