"""Key vault abstraction with a file-backed development implementation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

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

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> KeyVaultConfig:
        return cls(
            provider=raw.get("provider", "file"),
            file_path=raw.get("file_path", "data/keys"),
            hsm_config_path=raw.get("hsm_config_path"),
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


def build_key_vault_client(config: KeyVaultConfig) -> KeyVaultClient:
    provider = config.provider.lower()
    if provider == "file":
        if not config.file_path:
            msg = "file_path is required for file key vault provider"
            raise ValueError(msg)
        return FileKeyVaultClient(config.file_path)
    msg = f"Provider {config.provider} is not implemented yet"
    raise NotImplementedError(msg)
