"""
KMS/HSM Provider Abstraction for Secure Key Management

This module provides a unified interface for key management operations
that can be backed by various providers including Cloud KMS, Hardware
Security Modules (HSMs), or software-based implementations for development.

All private key operations are wrapped through providers to ensure:
1. Consistent security across environments
2. Hardware-backed security where required
3. Audit trail of all key operations
4. Role-based access controls
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, Union

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from .role_separation import (
    CryptoRole,
    KeyIdentity,
    KeyPurpose,
    RoleSeparationEnforcer,
    get_role_policy,
)


class KMSProvider(Enum):
    """Supported KMS/HSM providers."""

    AWS_KMS = "aws_kms"
    AZURE_KEY_VAULT = "azure_key_vault"
    GCP_KMS = "gcp_kms"
    HASHICORP_VAULT = "hashicorp_vault"
    OPENBAO = "openbao"
    PKCS11_HSM = "pkcs11_hsm"
    SOFTWARE_HSM = "software_hsm"  # For development/testing
    FILE_BASED = "file_based"  # For development only


class KeyOperation(Enum):
    """Key operations that can be audited."""

    GENERATE = "generate"
    IMPORT = "import"
    SIGN = "sign"
    ENCRYPT = "encrypt"
    DECRYPT = "decrypt"
    VERIFY = "verify"
    EXPORT_PUBLIC = "export_public"
    DELETE = "delete"
    ROTATE = "rotate"
    BACKUP = "backup"
    RESTORE = "restore"


@dataclass
class KeyMaterial:
    """Represents key material with metadata."""

    key_identity: KeyIdentity
    algorithm: str
    public_key_pem: bytes
    provider: KMSProvider
    provider_key_id: str
    created_at: datetime
    expires_at: datetime | None = None
    metadata: dict[str, Any] | None = None

    @property
    def is_expired(self) -> bool:
        """Check if the key has expired."""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at


@dataclass
class KeyOperationAuditLog:
    """Audit log entry for key operations."""

    timestamp: datetime
    operation: KeyOperation
    key_identity: KeyIdentity
    provider: KMSProvider
    success: bool
    error_message: str | None = None
    requesting_entity: str | None = None
    additional_context: dict[str, Any] | None = None


class KMSProviderInterface(ABC):
    """Abstract interface for KMS/HSM providers."""

    @abstractmethod
    async def generate_key(
        self, key_identity: KeyIdentity, algorithm: str, **kwargs
    ) -> KeyMaterial:
        """Generate a new key."""
        pass

    @abstractmethod
    async def sign(
        self, key_identity: KeyIdentity, data: bytes, algorithm: str = "SHA256"
    ) -> bytes:
        """Sign data using the specified key."""
        pass

    @abstractmethod
    async def encrypt(
        self, key_identity: KeyIdentity, plaintext: bytes, algorithm: str = "AES-256-GCM"
    ) -> bytes:
        """Encrypt data using the specified key."""
        pass

    @abstractmethod
    async def decrypt(
        self, key_identity: KeyIdentity, ciphertext: bytes, algorithm: str = "AES-256-GCM"
    ) -> bytes:
        """Decrypt data using the specified key."""
        pass

    @abstractmethod
    async def get_public_key(self, key_identity: KeyIdentity) -> bytes:
        """Get the public key in PEM format."""
        pass

    @abstractmethod
    async def delete_key(self, key_identity: KeyIdentity) -> bool:
        """Delete a key (if supported by provider)."""
        pass

    @abstractmethod
    async def list_keys(self, role: CryptoRole | None = None) -> list[KeyMaterial]:
        """List available keys, optionally filtered by role."""
        pass

    @abstractmethod
    async def key_exists(self, key_identity: KeyIdentity) -> bool:
        """Check if a key exists."""
        pass

    @abstractmethod
    def provides_attestation(self) -> bool:
        """Return True if this provider can produce hardware attestation evidence."""
        pass


class SoftwareHSMProvider(KMSProviderInterface):
    """Software-based HSM implementation for development and testing."""

    def __init__(self, storage_path: str = "/tmp/marty_software_hsm"):
        self.storage_path = storage_path
        self.logger = logging.getLogger(f"{__name__}.SoftwareHSMProvider")
        self._keys: dict[str, KeyMaterial] = {}
        self._private_keys: dict[str, Any] = {}  # Store actual private key objects

        # Create storage directory
        import os

        os.makedirs(storage_path, exist_ok=True)

    async def generate_key(
        self, key_identity: KeyIdentity, algorithm: str, **kwargs
    ) -> KeyMaterial:
        """Generate a new key pair."""

        # Validate role permissions
        policy = get_role_policy(key_identity.role)
        if policy.requires_hsm() and not kwargs.get("allow_software", False):
            raise ValueError(f"Role {key_identity.role} requires hardware HSM")

        # Generate key based on algorithm
        if algorithm.upper().startswith("RSA"):
            key_size = int(algorithm.replace("RSA", "") or "2048")
            private_key = rsa.generate_private_key(public_exponent=65537, key_size=key_size)
        elif algorithm.upper().startswith("EC") or algorithm == "ES256":
            private_key = ec.generate_private_key(ec.SECP256R1())
        else:
            raise ValueError(f"Unsupported algorithm: {algorithm}")

        # Extract public key
        public_key = private_key.public_key()
        public_key_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        # Create key material
        key_material = KeyMaterial(
            key_identity=key_identity,
            algorithm=algorithm,
            public_key_pem=public_key_pem,
            provider=KMSProvider.SOFTWARE_HSM,
            provider_key_id=key_identity.full_key_id,
            created_at=datetime.now(timezone.utc),
            metadata=kwargs,
        )

        # Store keys
        self._keys[key_identity.full_key_id] = key_material
        self._private_keys[key_identity.full_key_id] = private_key

        self.logger.info(f"Generated key for {key_identity.role}/{key_identity.purpose}")
        return key_material

    async def sign(
        self, key_identity: KeyIdentity, data: bytes, algorithm: str = "SHA256"
    ) -> bytes:
        """Sign data using the specified key."""

        # Validate operation
        RoleSeparationEnforcer.validate_key_operation(key_identity, "sign", key_identity.role)

        private_key = self._private_keys.get(key_identity.full_key_id)
        if not private_key:
            raise ValueError(f"Key not found: {key_identity.full_key_id}")

        # Sign based on key type
        if isinstance(private_key, rsa.RSAPrivateKey):
            hash_alg = hashes.SHA256()
            signature = private_key.sign(data, padding.PKCS1v15(), hash_alg)
        elif isinstance(private_key, ec.EllipticCurvePrivateKey):
            hash_alg = hashes.SHA256()
            signature = private_key.sign(data, ec.ECDSA(hash_alg))
        else:
            raise ValueError("Unsupported key type for signing")

        self.logger.debug(f"Signed data with key {key_identity.full_key_id}")
        return signature

    async def encrypt(
        self, key_identity: KeyIdentity, plaintext: bytes, algorithm: str = "AES-256-GCM"
    ) -> bytes:
        """Encrypt data using the specified key."""
        # For this implementation, we'll use the key to derive an encryption key
        # In a real HSM, this would be handled internally
        raise NotImplementedError("Encryption not implemented in SoftwareHSM")

    async def decrypt(
        self, key_identity: KeyIdentity, ciphertext: bytes, algorithm: str = "AES-256-GCM"
    ) -> bytes:
        """Decrypt data using the specified key."""
        raise NotImplementedError("Decryption not implemented in SoftwareHSM")

    async def get_public_key(self, key_identity: KeyIdentity) -> bytes:
        """Get the public key in PEM format."""
        key_material = self._keys.get(key_identity.full_key_id)
        if not key_material:
            raise ValueError(f"Key not found: {key_identity.full_key_id}")
        return key_material.public_key_pem

    async def delete_key(self, key_identity: KeyIdentity) -> bool:
        """Delete a key."""
        full_key_id = key_identity.full_key_id
        if full_key_id in self._keys:
            del self._keys[full_key_id]
            del self._private_keys[full_key_id]
            self.logger.info(f"Deleted key {full_key_id}")
            return True
        return False

    async def list_keys(self, role: CryptoRole | None = None) -> list[KeyMaterial]:
        """List available keys, optionally filtered by role."""
        keys = list(self._keys.values())
        if role:
            keys = [k for k in keys if k.key_identity.role == role]
        return keys

    async def key_exists(self, key_identity: KeyIdentity) -> bool:
        """Check if a key exists."""
        return key_identity.full_key_id in self._keys

    def provides_attestation(self) -> bool:
        return False


class FileBasedProvider(KMSProviderInterface):
    """File-based provider for development (inherits from existing FileKeyVaultClient logic)."""

    def __init__(self, storage_path: str):
        self.storage_path = storage_path
        self.logger = logging.getLogger(f"{__name__}.FileBasedProvider")
        # Implementation would extend existing FileKeyVaultClient

    async def generate_key(
        self, key_identity: KeyIdentity, algorithm: str, **kwargs
    ) -> KeyMaterial:
        # Implementation using existing FileKeyVaultClient logic
        raise NotImplementedError("FileBasedProvider not fully implemented")

    def provides_attestation(self) -> bool:
        return False

    # ... other methods would delegate to FileKeyVaultClient


try:
    import pkcs11
    from pkcs11 import Attribute, KeyType, Mechanism, ObjectClass
    from pkcs11 import lib as pkcs11_lib
    import pkcs11.util.ec as _pkcs11_ec
    _PKCS11_AVAILABLE = True
except ImportError:
    _PKCS11_AVAILABLE = False


class AWSKMSProvider(KMSProviderInterface):
    """AWS KMS provider for production key management."""

    def __init__(
        self,
        region_name: str,
        key_prefix: str = "marty/",
        endpoint_url: str | None = None,
    ):
        import boto3
        from botocore.exceptions import ClientError

        self.key_prefix = key_prefix
        self.logger = logging.getLogger(f"{__name__}.AWSKMSProvider")
        self._ClientError = ClientError
        kms_kwargs: dict[str, Any] = {"region_name": region_name}
        if endpoint_url:
            kms_kwargs["endpoint_url"] = endpoint_url
        self._kms = boto3.client("kms", **kms_kwargs)

    def _run(self, fn):
        """Run a synchronous boto3 call in a thread executor."""
        loop = asyncio.get_event_loop()
        return loop.run_in_executor(None, fn)

    def _alias_for(self, key_id: str) -> str:
        """Resolve a key_id string to an AWS KMS key reference."""
        if key_id.startswith("arn:") or key_id.startswith("alias/"):
            return key_id
        return f"alias/{self.key_prefix}{key_id}"

    async def generate_key(
        self, key_identity: KeyIdentity, algorithm: str, **kwargs
    ) -> KeyMaterial:
        """Create a new key in AWS KMS and return its material."""
        alg_upper = algorithm.upper()
        if alg_upper in ("ES256", "EC"):
            key_spec = "ECC_NIST_P256"
            key_usage = "SIGN_VERIFY"
        elif alg_upper in ("RSA2048", "RS256", "PS256"):
            key_spec = "RSA_2048"
            key_usage = "SIGN_VERIFY"
        else:
            raise ValueError(f"Unsupported algorithm for AWS KMS: {algorithm}")

        try:
            create_response = await self._run(
                lambda: self._kms.create_key(
                    KeySpec=key_spec,
                    KeyUsage=key_usage,
                    Tags=[{"TagKey": "marty:key-id", "TagValue": key_identity.key_id}],
                    Description=f"Marty key: {key_identity.key_id}",
                )
            )
            provider_key_id = create_response["KeyMetadata"]["KeyId"]
            alias_name = f"alias/{self.key_prefix}{key_identity.key_id}"
            await self._run(
                lambda: self._kms.create_alias(
                    AliasName=alias_name,
                    TargetKeyId=provider_key_id,
                )
            )
            public_key_pem = await self.get_public_key(key_identity)
            self.logger.info(f"Created AWS KMS key {provider_key_id} with alias {alias_name}")
            return KeyMaterial(
                key_identity=key_identity,
                algorithm=algorithm,
                public_key_pem=public_key_pem,
                provider=KMSProvider.AWS_KMS,
                provider_key_id=provider_key_id,
                created_at=datetime.now(timezone.utc),
                metadata=kwargs,
            )
        except self._ClientError as e:
            self.logger.error(f"AWS KMS ClientError in generate_key: {e}")
            raise RuntimeError(f"AWS KMS error: {e}") from e

    async def sign(
        self, key_identity: KeyIdentity, data: bytes, algorithm: str = "SHA256"
    ) -> bytes:
        """Sign data using an AWS KMS key."""
        _algo_map = {
            "ES256": "ECDSA_SHA_256",
            "RS256": "RSASSA_PKCS1_V1_5_SHA_256",
            "PS256": "RSASSA_PSS_SHA_256",
        }
        signing_algorithm = _algo_map.get(algorithm, algorithm)
        key_ref = self._alias_for(key_identity.key_id)
        try:
            response = await self._run(
                lambda: self._kms.sign(
                    KeyId=key_ref,
                    Message=data,
                    MessageType="RAW",
                    SigningAlgorithm=signing_algorithm,
                )
            )
            return response["Signature"]
        except self._ClientError as e:
            self.logger.error(f"AWS KMS ClientError in sign: {e}")
            raise RuntimeError(f"AWS KMS error: {e}") from e

    async def encrypt(
        self, key_identity: KeyIdentity, plaintext: bytes, algorithm: str = "RSAES_OAEP_SHA_256"
    ) -> bytes:
        """Encrypt data using an AWS KMS key."""
        key_ref = self._alias_for(key_identity.key_id)
        try:
            response = await self._run(
                lambda: self._kms.encrypt(
                    KeyId=key_ref,
                    Plaintext=plaintext,
                    EncryptionAlgorithm="RSAES_OAEP_SHA_256",
                )
            )
            return response["CiphertextBlob"]
        except self._ClientError as e:
            self.logger.error(f"AWS KMS ClientError in encrypt: {e}")
            raise RuntimeError(f"AWS KMS error: {e}") from e

    async def decrypt(
        self, key_identity: KeyIdentity, ciphertext: bytes, algorithm: str = "RSAES_OAEP_SHA_256"
    ) -> bytes:
        """Decrypt data using an AWS KMS key."""
        key_ref = self._alias_for(key_identity.key_id)
        try:
            response = await self._run(
                lambda: self._kms.decrypt(
                    KeyId=key_ref,
                    CiphertextBlob=ciphertext,
                    EncryptionAlgorithm="RSAES_OAEP_SHA_256",
                )
            )
            return response["Plaintext"]
        except self._ClientError as e:
            self.logger.error(f"AWS KMS ClientError in decrypt: {e}")
            raise RuntimeError(f"AWS KMS error: {e}") from e

    async def get_public_key(self, key_identity: KeyIdentity) -> bytes:
        """Get the public key in PEM format from AWS KMS."""
        key_ref = self._alias_for(key_identity.key_id)
        try:
            response = await self._run(
                lambda: self._kms.get_public_key(KeyId=key_ref)
            )
            der_bytes = response["PublicKey"]
            public_key = serialization.load_der_public_key(der_bytes)
            return public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        except self._ClientError as e:
            self.logger.error(f"AWS KMS ClientError in get_public_key: {e}")
            raise RuntimeError(f"AWS KMS error: {e}") from e

    async def delete_key(self, key_identity: KeyIdentity) -> bool:
        """Schedule an AWS KMS key for deletion with a 7-day pending window."""
        key_ref = self._alias_for(key_identity.key_id)
        try:
            await self._run(
                lambda: self._kms.schedule_key_deletion(
                    KeyId=key_ref,
                    PendingWindowInDays=7,
                )
            )
            self.logger.info(f"Scheduled deletion for AWS KMS key {key_identity.full_key_id}")
            return True
        except self._ClientError as e:
            self.logger.error(f"AWS KMS ClientError in delete_key: {e}")
            raise RuntimeError(f"AWS KMS error: {e}") from e

    async def list_keys(self, role: CryptoRole | None = None) -> list[KeyMaterial]:
        """List AWS KMS keys whose aliases match the configured prefix."""
        try:
            response = await self._run(
                lambda: self._kms.list_aliases(Limit=100)
            )
            aliases = response.get("Aliases", [])
            prefix_filter = f"alias/{self.key_prefix}"
            results: list[KeyMaterial] = []
            for alias in aliases:
                alias_name = alias.get("AliasName", "")
                if not alias_name.startswith(prefix_filter):
                    continue
                key_id_stub = alias_name[len(prefix_filter):]
                stub_role = role or CryptoRole.READER
                stub_purpose = KeyPurpose.SIGNATURE_VERIFICATION if stub_role in (CryptoRole.READER, CryptoRole.VERIFIER) else KeyPurpose.DOCUMENT_SIGNING
                stub_identity = KeyIdentity(
                    role=stub_role,
                    purpose=stub_purpose,
                    key_id=key_id_stub,
                )
                results.append(
                    KeyMaterial(
                        key_identity=stub_identity,
                        algorithm="unknown",
                        public_key_pem=b"",
                        provider=KMSProvider.AWS_KMS,
                        provider_key_id=alias.get("TargetKeyId", ""),
                        created_at=datetime.now(timezone.utc),
                    )
                )
            return results
        except self._ClientError as e:
            self.logger.error(f"AWS KMS ClientError in list_keys: {e}")
            raise RuntimeError(f"AWS KMS error: {e}") from e

    async def key_exists(self, key_identity: KeyIdentity) -> bool:
        """Check whether a key exists in AWS KMS."""
        key_ref = self._alias_for(key_identity.key_id)
        try:
            await self._run(lambda: self._kms.describe_key(KeyId=key_ref))
            return True
        except self._ClientError:
            return False

    def provides_attestation(self) -> bool:
        return True


class AzureKeyVaultProvider(KMSProviderInterface):
    """Azure Key Vault provider for production key management.

    Uses azure-identity DefaultAzureCredential for authentication and
    azure-keyvault-keys CryptographyClient for signing operations.

    Requires:
        pip install azure-identity azure-keyvault-keys
    """

    def __init__(
        self,
        vault_url: str,
        tenant_id: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
    ):
        from azure.identity import ClientSecretCredential, DefaultAzureCredential
        from azure.keyvault.keys import KeyClient
        from azure.core.exceptions import ResourceNotFoundError, HttpResponseError

        self.vault_url = vault_url
        self.logger = logging.getLogger(f"{__name__}.AzureKeyVaultProvider")
        self._ResourceNotFoundError = ResourceNotFoundError
        self._HttpResponseError = HttpResponseError

        if tenant_id and client_id and client_secret:
            credential = ClientSecretCredential(
                tenant_id=tenant_id,
                client_id=client_id,
                client_secret=client_secret,
            )
        else:
            credential = DefaultAzureCredential()

        self._credential = credential
        self._key_client = KeyClient(vault_url=vault_url, credential=credential)

    def _run(self, fn):
        """Run a synchronous Azure SDK call in a thread executor."""
        loop = asyncio.get_event_loop()
        return loop.run_in_executor(None, fn)

    async def generate_key(
        self, key_identity: KeyIdentity, algorithm: str, **kwargs
    ) -> KeyMaterial:
        """Create a new key in Azure Key Vault."""
        from azure.keyvault.keys import KeyCurveName, KeyType as AzureKeyType

        alg_upper = algorithm.upper()
        if alg_upper in ("ES256", "EC"):
            key_type = AzureKeyType.ec
            curve = KeyCurveName.p_256
        elif alg_upper in ("RSA2048", "RS256", "PS256"):
            key_type = AzureKeyType.rsa
            curve = None
        else:
            raise ValueError(f"Unsupported algorithm for Azure Key Vault: {algorithm}")

        key_name = key_identity.key_id.replace(":", "-")

        try:
            create_kwargs: dict[str, Any] = {"name": key_name, "key_type": key_type}
            if curve:
                create_kwargs["curve"] = curve
            if key_type == AzureKeyType.rsa:
                create_kwargs["size"] = 2048

            key_bundle = await self._run(
                lambda: self._key_client.create_key(**create_kwargs)
            )
            public_key_pem = await self.get_public_key(key_identity)
            self.logger.info(f"Created Azure Key Vault key {key_name}")
            return KeyMaterial(
                key_identity=key_identity,
                algorithm=algorithm,
                public_key_pem=public_key_pem,
                provider=KMSProvider.AZURE_KEY_VAULT,
                provider_key_id=key_bundle.id,
                created_at=datetime.now(timezone.utc),
                metadata=kwargs,
            )
        except self._HttpResponseError as e:
            self.logger.error(f"Azure Key Vault error in generate_key: {e}")
            raise RuntimeError(f"Azure Key Vault error: {e}") from e

    async def sign(
        self, key_identity: KeyIdentity, data: bytes, algorithm: str = "SHA256"
    ) -> bytes:
        """Sign data using an Azure Key Vault key."""
        from azure.keyvault.keys.crypto import CryptographyClient, SignatureAlgorithm

        _algo_map = {
            "ES256": SignatureAlgorithm.es256,
            "RS256": SignatureAlgorithm.rs256,
            "PS256": SignatureAlgorithm.ps256,
        }
        sig_algorithm = _algo_map.get(algorithm)
        if sig_algorithm is None:
            raise ValueError(f"Unsupported signing algorithm: {algorithm}")

        key_name = key_identity.key_id.replace(":", "-")

        try:
            key_bundle = await self._run(
                lambda: self._key_client.get_key(key_name)
            )
            crypto_client = CryptographyClient(key_bundle, credential=self._credential)
            # Azure expects a digest, not raw data for ES256
            if sig_algorithm == SignatureAlgorithm.es256:
                import hashlib
                digest = hashlib.sha256(data).digest()
                result = await self._run(
                    lambda: crypto_client.sign(sig_algorithm, digest)
                )
            else:
                result = await self._run(
                    lambda: crypto_client.sign(sig_algorithm, data)
                )
            return result.signature
        except (self._ResourceNotFoundError, self._HttpResponseError) as e:
            self.logger.error(f"Azure Key Vault error in sign: {e}")
            raise RuntimeError(f"Azure Key Vault error: {e}") from e

    async def encrypt(
        self, key_identity: KeyIdentity, plaintext: bytes, algorithm: str = "RSA-OAEP-256"
    ) -> bytes:
        """Encrypt data using an Azure Key Vault key."""
        from azure.keyvault.keys.crypto import CryptographyClient, EncryptionAlgorithm

        key_name = key_identity.key_id.replace(":", "-")
        try:
            key_bundle = await self._run(
                lambda: self._key_client.get_key(key_name)
            )
            crypto_client = CryptographyClient(key_bundle, credential=self._credential)
            result = await self._run(
                lambda: crypto_client.encrypt(EncryptionAlgorithm.rsa_oaep_256, plaintext)
            )
            return result.ciphertext
        except (self._ResourceNotFoundError, self._HttpResponseError) as e:
            self.logger.error(f"Azure Key Vault error in encrypt: {e}")
            raise RuntimeError(f"Azure Key Vault error: {e}") from e

    async def decrypt(
        self, key_identity: KeyIdentity, ciphertext: bytes, algorithm: str = "RSA-OAEP-256"
    ) -> bytes:
        """Decrypt data using an Azure Key Vault key."""
        from azure.keyvault.keys.crypto import CryptographyClient, EncryptionAlgorithm

        key_name = key_identity.key_id.replace(":", "-")
        try:
            key_bundle = await self._run(
                lambda: self._key_client.get_key(key_name)
            )
            crypto_client = CryptographyClient(key_bundle, credential=self._credential)
            result = await self._run(
                lambda: crypto_client.decrypt(EncryptionAlgorithm.rsa_oaep_256, ciphertext)
            )
            return result.plaintext
        except (self._ResourceNotFoundError, self._HttpResponseError) as e:
            self.logger.error(f"Azure Key Vault error in decrypt: {e}")
            raise RuntimeError(f"Azure Key Vault error: {e}") from e

    async def get_public_key(self, key_identity: KeyIdentity) -> bytes:
        """Get the public key in PEM format from Azure Key Vault."""
        key_name = key_identity.key_id.replace(":", "-")
        try:
            key_bundle = await self._run(
                lambda: self._key_client.get_key(key_name)
            )
            jwk = key_bundle.key
            # Convert JWK to PEM via cryptography
            if jwk.kty == "EC":
                from cryptography.hazmat.primitives.asymmetric.ec import (
                    EllipticCurvePublicNumbers,
                    SECP256R1,
                )
                x = int.from_bytes(jwk.x, "big")
                y = int.from_bytes(jwk.y, "big")
                pub_numbers = EllipticCurvePublicNumbers(x, y, SECP256R1())
                public_key = pub_numbers.public_key()
            elif jwk.kty == "RSA":
                from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers
                n = int.from_bytes(jwk.n, "big")
                e = int.from_bytes(jwk.e, "big")
                pub_numbers = RSAPublicNumbers(e, n)
                public_key = pub_numbers.public_key()
            else:
                raise ValueError(f"Unsupported key type: {jwk.kty}")

            return public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        except self._ResourceNotFoundError as e:
            self.logger.error(f"Azure Key Vault key not found: {e}")
            raise RuntimeError(f"Azure Key Vault key not found: {e}") from e

    async def delete_key(self, key_identity: KeyIdentity) -> bool:
        """Delete a key from Azure Key Vault (soft-delete enabled)."""
        key_name = key_identity.key_id.replace(":", "-")
        try:
            await self._run(
                lambda: self._key_client.begin_delete_key(key_name).result()
            )
            self.logger.info(f"Deleted Azure Key Vault key {key_name}")
            return True
        except (self._ResourceNotFoundError, self._HttpResponseError) as e:
            self.logger.error(f"Azure Key Vault error in delete_key: {e}")
            raise RuntimeError(f"Azure Key Vault error: {e}") from e

    async def list_keys(self, role: CryptoRole | None = None) -> list[KeyMaterial]:
        """List keys in the Azure Key Vault."""
        try:
            key_properties_list = await self._run(
                lambda: list(self._key_client.list_properties_of_keys())
            )
            results: list[KeyMaterial] = []
            for kp in key_properties_list:
                stub_role = role or CryptoRole.READER
                stub_purpose = KeyPurpose.SIGNATURE_VERIFICATION if stub_role in (CryptoRole.READER, CryptoRole.VERIFIER) else KeyPurpose.DOCUMENT_SIGNING
                stub_identity = KeyIdentity(
                    role=stub_role,
                    purpose=stub_purpose,
                    key_id=kp.name,
                )
                results.append(
                    KeyMaterial(
                        key_identity=stub_identity,
                        algorithm="unknown",
                        public_key_pem=b"",
                        provider=KMSProvider.AZURE_KEY_VAULT,
                        provider_key_id=kp.id or kp.name,
                        created_at=kp.created_on or datetime.now(timezone.utc),
                    )
                )
            return results
        except self._HttpResponseError as e:
            self.logger.error(f"Azure Key Vault error in list_keys: {e}")
            raise RuntimeError(f"Azure Key Vault error: {e}") from e

    async def key_exists(self, key_identity: KeyIdentity) -> bool:
        """Check whether a key exists in Azure Key Vault."""
        key_name = key_identity.key_id.replace(":", "-")
        try:
            await self._run(lambda: self._key_client.get_key(key_name))
            return True
        except self._ResourceNotFoundError:
            return False

    def provides_attestation(self) -> bool:
        return True


class GCPCloudKMSProvider(KMSProviderInterface):
    """Google Cloud KMS provider for production key management.

    Uses google-cloud-kms client library. Keys are addressed by their
    full resource name: projects/{project}/locations/{location}/keyRings/{ring}/cryptoKeys/{key}.

    Requires:
        pip install google-cloud-kms
    """

    def __init__(
        self,
        project_id: str,
        location: str = "global",
        key_ring: str = "marty",
        credentials_json: str | None = None,
    ):
        from google.cloud import kms as google_kms
        from google.api_core.exceptions import NotFound, GoogleAPICallError

        self.project_id = project_id
        self.location = location
        self.key_ring = key_ring
        self.logger = logging.getLogger(f"{__name__}.GCPCloudKMSProvider")
        self._NotFound = NotFound
        self._GoogleAPICallError = GoogleAPICallError
        self._google_kms = google_kms

        client_kwargs: dict[str, Any] = {}
        if credentials_json:
            from google.oauth2 import service_account
            import json as _json
            creds = service_account.Credentials.from_service_account_info(
                _json.loads(credentials_json)
            )
            client_kwargs["credentials"] = creds

        self._client = google_kms.KeyManagementServiceClient(**client_kwargs)
        self._key_ring_name = self._client.key_ring_path(project_id, location, key_ring)

        # Ensure key ring exists
        try:
            self._client.get_key_ring(request={"name": self._key_ring_name})
        except NotFound:
            location_name = f"projects/{project_id}/locations/{location}"
            self._client.create_key_ring(
                request={
                    "parent": location_name,
                    "key_ring_id": key_ring,
                    "key_ring": {},
                }
            )

    def _run(self, fn):
        """Run a synchronous GCP call in a thread executor."""
        loop = asyncio.get_event_loop()
        return loop.run_in_executor(None, fn)

    def _crypto_key_path(self, key_id: str) -> str:
        """Get the full resource path for a crypto key."""
        safe_id = key_id.replace(":", "-")
        return self._client.crypto_key_path(
            self.project_id, self.location, self.key_ring, safe_id
        )

    def _crypto_key_version_path(self, key_id: str, version: str = "1") -> str:
        """Get the full resource path for a crypto key version."""
        safe_id = key_id.replace(":", "-")
        return self._client.crypto_key_version_path(
            self.project_id, self.location, self.key_ring, safe_id, version
        )

    async def generate_key(
        self, key_identity: KeyIdentity, algorithm: str, **kwargs
    ) -> KeyMaterial:
        """Create a new asymmetric signing key in GCP Cloud KMS."""
        kms = self._google_kms

        alg_upper = algorithm.upper()
        if alg_upper in ("ES256", "EC"):
            purpose = kms.CryptoKey.CryptoKeyPurpose.ASYMMETRIC_SIGN
            version_algorithm = kms.CryptoKeyVersion.CryptoKeyVersionAlgorithm.EC_SIGN_P256_SHA256
        elif alg_upper in ("RSA2048", "RS256"):
            purpose = kms.CryptoKey.CryptoKeyPurpose.ASYMMETRIC_SIGN
            version_algorithm = kms.CryptoKeyVersion.CryptoKeyVersionAlgorithm.RSA_SIGN_PKCS1_2048_SHA256
        elif alg_upper == "PS256":
            purpose = kms.CryptoKey.CryptoKeyPurpose.ASYMMETRIC_SIGN
            version_algorithm = kms.CryptoKeyVersion.CryptoKeyVersionAlgorithm.RSA_SIGN_PSS_2048_SHA256
        else:
            raise ValueError(f"Unsupported algorithm for GCP Cloud KMS: {algorithm}")

        safe_key_id = key_identity.key_id.replace(":", "-")

        try:
            crypto_key = await self._run(
                lambda: self._client.create_crypto_key(
                    request={
                        "parent": self._key_ring_name,
                        "crypto_key_id": safe_key_id,
                        "crypto_key": {
                            "purpose": purpose,
                            "version_template": {"algorithm": version_algorithm},
                        },
                    }
                )
            )
            public_key_pem = await self.get_public_key(key_identity)
            self.logger.info(f"Created GCP Cloud KMS key {safe_key_id}")
            return KeyMaterial(
                key_identity=key_identity,
                algorithm=algorithm,
                public_key_pem=public_key_pem,
                provider=KMSProvider.GCP_KMS,
                provider_key_id=crypto_key.name,
                created_at=datetime.now(timezone.utc),
                metadata=kwargs,
            )
        except self._GoogleAPICallError as e:
            self.logger.error(f"GCP Cloud KMS error in generate_key: {e}")
            raise RuntimeError(f"GCP Cloud KMS error: {e}") from e

    async def sign(
        self, key_identity: KeyIdentity, data: bytes, algorithm: str = "SHA256"
    ) -> bytes:
        """Sign data using a GCP Cloud KMS key."""
        import hashlib

        version_path = self._crypto_key_version_path(key_identity.key_id)

        # GCP expects a digest for asymmetric signing
        digest_bytes = hashlib.sha256(data).digest()

        try:
            response = await self._run(
                lambda: self._client.asymmetric_sign(
                    request={
                        "name": version_path,
                        "digest": {"sha256": digest_bytes},
                    }
                )
            )
            return response.signature
        except (self._NotFound, self._GoogleAPICallError) as e:
            self.logger.error(f"GCP Cloud KMS error in sign: {e}")
            raise RuntimeError(f"GCP Cloud KMS error: {e}") from e

    async def encrypt(
        self, key_identity: KeyIdentity, plaintext: bytes, algorithm: str = "RSA-OAEP-256"
    ) -> bytes:
        """Encrypt data using a GCP Cloud KMS asymmetric key."""
        version_path = self._crypto_key_version_path(key_identity.key_id)
        try:
            response = await self._run(
                lambda: self._client.asymmetric_encrypt(
                    request={"name": version_path, "plaintext": plaintext}
                )
            )
            return response.ciphertext
        except (self._NotFound, self._GoogleAPICallError) as e:
            self.logger.error(f"GCP Cloud KMS error in encrypt: {e}")
            raise RuntimeError(f"GCP Cloud KMS error: {e}") from e

    async def decrypt(
        self, key_identity: KeyIdentity, ciphertext: bytes, algorithm: str = "RSA-OAEP-256"
    ) -> bytes:
        """Decrypt data using a GCP Cloud KMS asymmetric key."""
        version_path = self._crypto_key_version_path(key_identity.key_id)
        try:
            response = await self._run(
                lambda: self._client.asymmetric_decrypt(
                    request={"name": version_path, "ciphertext": ciphertext}
                )
            )
            return response.plaintext
        except (self._NotFound, self._GoogleAPICallError) as e:
            self.logger.error(f"GCP Cloud KMS error in decrypt: {e}")
            raise RuntimeError(f"GCP Cloud KMS error: {e}") from e

    async def get_public_key(self, key_identity: KeyIdentity) -> bytes:
        """Get the public key in PEM format from GCP Cloud KMS."""
        version_path = self._crypto_key_version_path(key_identity.key_id)
        try:
            response = await self._run(
                lambda: self._client.get_public_key(request={"name": version_path})
            )
            # GCP returns PEM-encoded public key as a string
            return response.pem.encode("utf-8")
        except self._NotFound as e:
            self.logger.error(f"GCP Cloud KMS key not found: {e}")
            raise RuntimeError(f"GCP Cloud KMS key not found: {e}") from e

    async def delete_key(self, key_identity: KeyIdentity) -> bool:
        """Destroy the primary key version in GCP Cloud KMS."""
        version_path = self._crypto_key_version_path(key_identity.key_id)
        kms = self._google_kms
        try:
            await self._run(
                lambda: self._client.destroy_crypto_key_version(
                    request={"name": version_path}
                )
            )
            self.logger.info(f"Destroyed GCP Cloud KMS key version {version_path}")
            return True
        except (self._NotFound, self._GoogleAPICallError) as e:
            self.logger.error(f"GCP Cloud KMS error in delete_key: {e}")
            raise RuntimeError(f"GCP Cloud KMS error: {e}") from e

    async def list_keys(self, role: CryptoRole | None = None) -> list[KeyMaterial]:
        """List crypto keys in the key ring."""
        try:
            keys = await self._run(
                lambda: list(
                    self._client.list_crypto_keys(request={"parent": self._key_ring_name})
                )
            )
            results: list[KeyMaterial] = []
            for key in keys:
                # Extract short name from full resource path
                short_name = key.name.rsplit("/", 1)[-1]
                stub_role = role or CryptoRole.READER
                stub_purpose = KeyPurpose.SIGNATURE_VERIFICATION if stub_role in (CryptoRole.READER, CryptoRole.VERIFIER) else KeyPurpose.DOCUMENT_SIGNING
                stub_identity = KeyIdentity(
                    role=stub_role,
                    purpose=stub_purpose,
                    key_id=short_name,
                )
                results.append(
                    KeyMaterial(
                        key_identity=stub_identity,
                        algorithm="unknown",
                        public_key_pem=b"",
                        provider=KMSProvider.GCP_KMS,
                        provider_key_id=key.name,
                        created_at=key.create_time or datetime.now(timezone.utc),
                    )
                )
            return results
        except self._GoogleAPICallError as e:
            self.logger.error(f"GCP Cloud KMS error in list_keys: {e}")
            raise RuntimeError(f"GCP Cloud KMS error: {e}") from e

    async def key_exists(self, key_identity: KeyIdentity) -> bool:
        """Check whether a crypto key exists in the key ring."""
        key_path = self._crypto_key_path(key_identity.key_id)
        try:
            await self._run(
                lambda: self._client.get_crypto_key(request={"name": key_path})
            )
            return True
        except self._NotFound:
            return False

    def provides_attestation(self) -> bool:
        return True


class PKCS11HSMProvider(KMSProviderInterface):
    """PKCS#11 HSM provider for hardware security modules."""

    def __init__(self, library_path: str, token_label: str, user_pin: str):
        if not _PKCS11_AVAILABLE:
            raise RuntimeError("python-pkcs11 not installed: pip install python-pkcs11")
        self.logger = logging.getLogger(f"{__name__}.PKCS11HSMProvider")
        self._lib = pkcs11_lib(library_path)
        token = self._lib.get_token(token_label=token_label)
        self._session = token.open(user_pin=user_pin, rw=True)

    def _run_sync(self, fn):
        """Run a synchronous PKCS#11 call in a thread executor."""
        loop = asyncio.get_event_loop()
        return loop.run_in_executor(None, fn)

    async def generate_key(
        self, key_identity: KeyIdentity, algorithm: str, **kwargs
    ) -> KeyMaterial:
        """Generate a key pair on the HSM token."""
        def _generate():
            label = key_identity.key_id
            alg_upper = algorithm.upper()
            if alg_upper in ("ES256", "EC"):
                ec_params = _pkcs11_ec.encode_named_curve_parameters("secp256r1")
                domain_params = self._session.create_domain_parameters(
                    KeyType.EC,
                    {Attribute.EC_PARAMS: ec_params},
                    local=True,
                )
                public_key, _ = domain_params.generate_keypair(
                    store=True,
                    label=label,
                    private_template={
                        Attribute.TOKEN: True,
                        Attribute.SENSITIVE: True,
                        Attribute.EXTRACTABLE: False,
                    },
                )
            elif alg_upper in ("RSA2048", "RS256", "PS256"):
                public_key, _ = self._session.generate_keypair(
                    KeyType.RSA,
                    2048,
                    store=True,
                    label=label,
                    private_template={
                        Attribute.TOKEN: True,
                        Attribute.SENSITIVE: True,
                        Attribute.EXTRACTABLE: False,
                    },
                )
            else:
                raise ValueError(f"Unsupported algorithm for PKCS11: {algorithm}")

            try:
                if alg_upper in ("ES256", "EC"):
                    from pkcs11.util.ec import encode_ec_public_key
                    der_bytes = encode_ec_public_key(public_key)
                else:
                    from pkcs11.util.rsa import encode_rsa_public_key
                    der_bytes = encode_rsa_public_key(public_key)
                pub_key_obj = serialization.load_der_public_key(der_bytes)
                return pub_key_obj.public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo,
                )
            except Exception:
                return b""

        public_key_pem = await self._run_sync(_generate)
        return KeyMaterial(
            key_identity=key_identity,
            algorithm=algorithm,
            public_key_pem=public_key_pem,
            provider=KMSProvider.PKCS11_HSM,
            provider_key_id=key_identity.full_key_id,
            created_at=datetime.now(timezone.utc),
            metadata=kwargs,
        )

    async def sign(
        self, key_identity: KeyIdentity, data: bytes, algorithm: str = "SHA256"
    ) -> bytes:
        """Sign data using a private key stored on the HSM."""
        def _sign():
            objects = list(self._session.get_objects({
                Attribute.CLASS: ObjectClass.PRIVATE_KEY,
                Attribute.LABEL: key_identity.key_id,
            }))
            if not objects:
                raise ValueError(f"Private key not found: {key_identity.key_id}")
            private_key = objects[0]
            try:
                key_type = private_key[Attribute.KEY_TYPE]
            except Exception:
                key_type = None
            mechanism = Mechanism.ECDSA_SHA256 if key_type == KeyType.EC else Mechanism.SHA256_RSA_PKCS
            return private_key.sign(data, mechanism=mechanism)

        return await self._run_sync(_sign)

    async def encrypt(
        self, key_identity: KeyIdentity, plaintext: bytes, algorithm: str = ""
    ) -> bytes:
        raise NotImplementedError(
            "Use asymmetric sign/verify; encrypt/decrypt not wired for PKCS11"
        )

    async def decrypt(
        self, key_identity: KeyIdentity, ciphertext: bytes, algorithm: str = ""
    ) -> bytes:
        raise NotImplementedError(
            "Use asymmetric sign/verify; encrypt/decrypt not wired for PKCS11"
        )

    async def get_public_key(self, key_identity: KeyIdentity) -> bytes:
        """Get the public key in PEM format from the HSM."""
        def _get_pub():
            objects = list(self._session.get_objects({
                Attribute.CLASS: ObjectClass.PUBLIC_KEY,
                Attribute.LABEL: key_identity.key_id,
            }))
            if not objects:
                raise ValueError(f"Public key not found: {key_identity.key_id}")
            public_key = objects[0]
            try:
                key_type = public_key[Attribute.KEY_TYPE]
            except Exception:
                key_type = None
            if key_type == KeyType.EC:
                from pkcs11.util.ec import encode_ec_public_key
                der_bytes = encode_ec_public_key(public_key)
            else:
                from pkcs11.util.rsa import encode_rsa_public_key
                der_bytes = encode_rsa_public_key(public_key)
            pub_key_obj = serialization.load_der_public_key(der_bytes)
            return pub_key_obj.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )

        return await self._run_sync(_get_pub)

    async def delete_key(self, key_identity: KeyIdentity) -> bool:
        """Destroy both public and private key objects for the given label."""
        def _delete():
            label = key_identity.key_id
            destroyed = False
            for obj_class in (ObjectClass.PRIVATE_KEY, ObjectClass.PUBLIC_KEY):
                objects = list(self._session.get_objects({
                    Attribute.CLASS: obj_class,
                    Attribute.LABEL: label,
                }))
                for obj in objects:
                    obj.destroy()
                    destroyed = True
            return destroyed

        return await self._run_sync(_delete)

    async def list_keys(self, role: CryptoRole | None = None) -> list[KeyMaterial]:
        """List all private keys on the HSM token."""
        def _list():
            objects = list(self._session.get_objects({
                Attribute.CLASS: ObjectClass.PRIVATE_KEY,
            }))
            results: list[KeyMaterial] = []
            for obj in objects:
                try:
                    label = obj[Attribute.LABEL]
                except Exception:
                    label = "unknown"
                stub_role = role or CryptoRole.READER
                stub_purpose = KeyPurpose.SIGNATURE_VERIFICATION if stub_role in (CryptoRole.READER, CryptoRole.VERIFIER) else KeyPurpose.DOCUMENT_SIGNING
                stub_identity = KeyIdentity(
                    role=stub_role,
                    purpose=stub_purpose,
                    key_id=label,
                )
                results.append(
                    KeyMaterial(
                        key_identity=stub_identity,
                        algorithm="unknown",
                        public_key_pem=b"",
                        provider=KMSProvider.PKCS11_HSM,
                        provider_key_id=label,
                        created_at=datetime.now(timezone.utc),
                    )
                )
            return results

        return await self._run_sync(_list)

    async def key_exists(self, key_identity: KeyIdentity) -> bool:
        """Check if a private key with the given label exists on the HSM."""
        def _exists():
            objects = list(self._session.get_objects({
                Attribute.CLASS: ObjectClass.PRIVATE_KEY,
                Attribute.LABEL: key_identity.key_id,
            }))
            return len(objects) > 0

        return await self._run_sync(_exists)

    def provides_attestation(self) -> bool:
        return True


class HashiCorpVaultProvider(KMSProviderInterface):
    """HashiCorp Vault Transit secrets engine provider for key management.

    Uses the Transit engine for signing, key generation, and public key
    retrieval.  All private key operations happen inside Vault — keys
    never leave the server.

    Requires:
        pip install hvac
    """

    def __init__(
        self,
        vault_addr: str,
        token: str | None = None,
        mount_point: str = "transit",
        namespace: str | None = None,
    ):
        import hvac
        from hvac.exceptions import VaultError

        self.mount_point = mount_point
        self.logger = logging.getLogger(f"{__name__}.HashiCorpVaultProvider")
        self._VaultError = VaultError

        kwargs: dict[str, Any] = {"url": vault_addr}
        if namespace:
            kwargs["namespace"] = namespace
        self._client = hvac.Client(**kwargs)
        if token:
            self._client.token = token

    def _run(self, fn):
        loop = asyncio.get_event_loop()
        return loop.run_in_executor(None, fn)

    async def generate_key(
        self, key_identity: KeyIdentity, algorithm: str, **kwargs
    ) -> KeyMaterial:
        """Create a new Transit key and return its material."""
        alg_upper = algorithm.upper()
        if alg_upper in ("ES256", "EC", "ECDSA-P256"):
            vault_key_type = "ecdsa-p256"
        elif alg_upper in ("RS256", "PS256", "RSA2048", "RSA"):
            vault_key_type = "rsa-2048"
        elif alg_upper in ("ED25519", "EDDSA"):
            vault_key_type = "ed25519"
        else:
            raise ValueError(f"Unsupported algorithm for HashiCorp Vault: {algorithm}")

        key_name = key_identity.key_id.replace(":", "-")
        try:
            await self._run(
                lambda: self._client.secrets.transit.create_key(
                    name=key_name,
                    key_type=vault_key_type,
                    mount_point=self.mount_point,
                )
            )
            public_key_pem = await self.get_public_key(key_identity)
            self.logger.info(f"Created Vault Transit key {key_name}")
            return KeyMaterial(
                key_identity=key_identity,
                algorithm=algorithm,
                public_key_pem=public_key_pem,
                provider=KMSProvider.HASHICORP_VAULT,
                provider_key_id=key_name,
                created_at=datetime.now(timezone.utc),
                metadata=kwargs,
            )
        except self._VaultError as e:
            self.logger.error(f"Vault error in generate_key: {e}")
            raise RuntimeError(f"HashiCorp Vault error: {e}") from e

    async def sign(
        self, key_identity: KeyIdentity, data: bytes, algorithm: str = "SHA256"
    ) -> bytes:
        """Sign data using a Vault Transit key."""
        import base64

        key_name = key_identity.key_id.replace(":", "-")
        b64_payload = base64.b64encode(data).decode()
        try:
            response = await self._run(
                lambda: self._client.secrets.transit.sign_data(
                    name=key_name,
                    hash_input=b64_payload,
                    mount_point=self.mount_point,
                )
            )
            signature_b64 = response["data"]["signature"].split(":")[-1]
            return base64.b64decode(signature_b64)
        except self._VaultError as e:
            self.logger.error(f"Vault error in sign: {e}")
            raise RuntimeError(f"HashiCorp Vault error: {e}") from e

    async def encrypt(
        self, key_identity: KeyIdentity, plaintext: bytes, algorithm: str = "AES-256-GCM"
    ) -> bytes:
        """Encrypt data using a Vault Transit key."""
        import base64

        key_name = key_identity.key_id.replace(":", "-")
        b64_plaintext = base64.b64encode(plaintext).decode()
        try:
            response = await self._run(
                lambda: self._client.secrets.transit.encrypt_data(
                    name=key_name,
                    plaintext=b64_plaintext,
                    mount_point=self.mount_point,
                )
            )
            return response["data"]["ciphertext"].encode()
        except self._VaultError as e:
            self.logger.error(f"Vault error in encrypt: {e}")
            raise RuntimeError(f"HashiCorp Vault error: {e}") from e

    async def decrypt(
        self, key_identity: KeyIdentity, ciphertext: bytes, algorithm: str = "AES-256-GCM"
    ) -> bytes:
        """Decrypt data using a Vault Transit key."""
        import base64

        key_name = key_identity.key_id.replace(":", "-")
        ciphertext_str = ciphertext.decode() if isinstance(ciphertext, bytes) else ciphertext
        try:
            response = await self._run(
                lambda: self._client.secrets.transit.decrypt_data(
                    name=key_name,
                    ciphertext=ciphertext_str,
                    mount_point=self.mount_point,
                )
            )
            return base64.b64decode(response["data"]["plaintext"])
        except self._VaultError as e:
            self.logger.error(f"Vault error in decrypt: {e}")
            raise RuntimeError(f"HashiCorp Vault error: {e}") from e

    async def get_public_key(self, key_identity: KeyIdentity) -> bytes:
        """Get the public key in PEM format from Vault Transit."""
        key_name = key_identity.key_id.replace(":", "-")
        try:
            response = await self._run(
                lambda: self._client.secrets.transit.read_key(
                    name=key_name,
                    mount_point=self.mount_point,
                )
            )
            keys = response["data"]["keys"]
            latest_version = str(response["data"]["latest_version"])
            public_key_pem = keys[latest_version]["public_key"]
            return public_key_pem.encode() if isinstance(public_key_pem, str) else public_key_pem
        except self._VaultError as e:
            self.logger.error(f"Vault error in get_public_key: {e}")
            raise RuntimeError(f"HashiCorp Vault key not found: {e}") from e

    async def delete_key(self, key_identity: KeyIdentity) -> bool:
        """Delete a Vault Transit key (requires deletion_allowed=True)."""
        key_name = key_identity.key_id.replace(":", "-")
        try:
            # Must first update config to allow deletion
            await self._run(
                lambda: self._client.secrets.transit.update_key_configuration(
                    name=key_name,
                    deletion_allowed=True,
                    mount_point=self.mount_point,
                )
            )
            await self._run(
                lambda: self._client.secrets.transit.delete_key(
                    name=key_name,
                    mount_point=self.mount_point,
                )
            )
            self.logger.info(f"Deleted Vault Transit key {key_name}")
            return True
        except self._VaultError as e:
            self.logger.error(f"Vault error in delete_key: {e}")
            raise RuntimeError(f"HashiCorp Vault error: {e}") from e

    async def list_keys(self, role: CryptoRole | None = None) -> list[KeyMaterial]:
        """List Transit keys."""
        try:
            response = await self._run(
                lambda: self._client.secrets.transit.list_keys(
                    mount_point=self.mount_point,
                )
            )
            key_names = response.get("data", {}).get("keys", [])
            results: list[KeyMaterial] = []
            for name in key_names:
                stub_role = role or CryptoRole.READER
                stub_purpose = KeyPurpose.SIGNATURE_VERIFICATION if stub_role in (CryptoRole.READER, CryptoRole.VERIFIER) else KeyPurpose.DOCUMENT_SIGNING
                stub_identity = KeyIdentity(
                    role=stub_role,
                    purpose=stub_purpose,
                    key_id=name,
                )
                results.append(
                    KeyMaterial(
                        key_identity=stub_identity,
                        algorithm="unknown",
                        public_key_pem=b"",
                        provider=KMSProvider.HASHICORP_VAULT,
                        provider_key_id=name,
                        created_at=datetime.now(timezone.utc),
                    )
                )
            return results
        except self._VaultError as e:
            self.logger.error(f"Vault error in list_keys: {e}")
            raise RuntimeError(f"HashiCorp Vault error: {e}") from e

    async def key_exists(self, key_identity: KeyIdentity) -> bool:
        """Check whether a Transit key exists."""
        key_name = key_identity.key_id.replace(":", "-")
        try:
            await self._run(
                lambda: self._client.secrets.transit.read_key(
                    name=key_name,
                    mount_point=self.mount_point,
                )
            )
            return True
        except self._VaultError:
            return False

    def provides_attestation(self) -> bool:
        return False


class KMSManager:
    """Central manager for KMS/HSM operations with role enforcement."""

    def __init__(self, provider: KMSProviderInterface):
        self.provider = provider
        self.logger = logging.getLogger(f"{__name__}.KMSManager")
        self.audit_logs: list[KeyOperationAuditLog] = []
        self.role_enforcer = RoleSeparationEnforcer()

    async def generate_key_for_role(
        self, role: CryptoRole, purpose: KeyPurpose, key_id: str, algorithm: str = "ES256", **kwargs
    ) -> KeyMaterial:
        """Generate a key for a specific role and purpose."""

        # Create key identity
        key_identity = KeyIdentity(
            role=role,
            purpose=purpose,
            key_id=key_id,
            issuer_identifier=kwargs.get("issuer_identifier"),
            device_identifier=kwargs.get("device_identifier"),
        )

        # Validate role policy
        policy = get_role_policy(role)
        if policy.requires_hsm() and not self.provider.provides_attestation():
            _enforce = os.environ.get("ENFORCE_HSM_ATTESTATION", "true").lower()
            if _enforce == "true":
                raise ValueError(
                    f"Role {role} requires hardware attestation but provider "
                    f"{type(self.provider).__name__} does not provide it. "
                    "Set ENFORCE_HSM_ATTESTATION=false to override in development."
                )
            self.logger.warning(
                "HSM attestation required for role %s but %s does not provide attestation "
                "(ENFORCE_HSM_ATTESTATION=false — NOT suitable for production)",
                role,
                type(self.provider).__name__,
            )

        try:
            key_material = await self.provider.generate_key(key_identity, algorithm, **kwargs)

            # Log the operation
            await self._log_operation(
                KeyOperation.GENERATE,
                key_identity,
                success=True,
                additional_context={"algorithm": algorithm},
            )

            return key_material

        except Exception as e:
            await self._log_operation(
                KeyOperation.GENERATE, key_identity, success=False, error_message=str(e)
            )
            raise

    async def sign_with_role_validation(
        self,
        key_identity: KeyIdentity,
        data: bytes,
        requesting_role: CryptoRole,
        algorithm: str = "SHA256",
    ) -> bytes:
        """Sign data with role boundary validation."""

        # Validate the operation is allowed
        self.role_enforcer.validate_key_operation(key_identity, "sign", requesting_role)

        try:
            signature = await self.provider.sign(key_identity, data, algorithm)

            await self._log_operation(
                KeyOperation.SIGN,
                key_identity,
                success=True,
                requesting_entity=requesting_role.value,
            )

            return signature

        except Exception as e:
            await self._log_operation(
                KeyOperation.SIGN,
                key_identity,
                success=False,
                error_message=str(e),
                requesting_entity=requesting_role.value,
            )
            raise

    async def get_public_key_for_verification(
        self, key_identity: KeyIdentity, requesting_role: CryptoRole
    ) -> bytes:
        """Get public key for verification purposes."""

        # Public keys can be shared for verification
        if requesting_role in [CryptoRole.READER, CryptoRole.VERIFIER]:
            return await self.provider.get_public_key(key_identity)

        # Other roles need validation
        self.role_enforcer.validate_key_operation(key_identity, "export_public", requesting_role)

        return await self.provider.get_public_key(key_identity)

    async def _log_operation(
        self,
        operation: KeyOperation,
        key_identity: KeyIdentity,
        success: bool,
        error_message: str | None = None,
        requesting_entity: str | None = None,
        additional_context: dict[str, Any] | None = None,
    ) -> None:
        """Log a key operation for audit purposes."""

        log_entry = KeyOperationAuditLog(
            timestamp=datetime.now(timezone.utc),
            operation=operation,
            key_identity=key_identity,
            provider=KMSProvider.SOFTWARE_HSM,  # Get from provider
            success=success,
            error_message=error_message,
            requesting_entity=requesting_entity,
            additional_context=additional_context,
        )

        self.audit_logs.append(log_entry)

        # In production, this would also write to persistent audit storage
        if get_role_policy(key_identity.role).requires_audit:
            self.logger.info(
                f"Audit: {operation.value} on {key_identity.full_key_id} "
                f"by {requesting_entity} - {'SUCCESS' if success else 'FAILED'}"
            )

    async def list_keys_by_role(self, role: CryptoRole) -> list[KeyMaterial]:
        """List all keys for a specific role."""
        return await self.provider.list_keys(role)

    async def rotate_key(
        self, old_key_identity: KeyIdentity, algorithm: str = "ES256", overlap_days: int = 30
    ) -> KeyMaterial:
        """Rotate a key while maintaining overlap period."""

        # Generate new key with incremented version
        new_key_id = f"{old_key_identity.key_id}-rotated-{int(datetime.now().timestamp())}"
        new_key_identity = KeyIdentity(
            role=old_key_identity.role,
            purpose=old_key_identity.purpose,
            key_id=new_key_id,
            issuer_identifier=old_key_identity.issuer_identifier,
            device_identifier=old_key_identity.device_identifier,
        )

        # Generate new key
        new_key = await self.provider.generate_key(new_key_identity, algorithm)

        # Log rotation
        await self._log_operation(
            KeyOperation.ROTATE,
            old_key_identity,
            success=True,
            additional_context={
                "new_key_id": new_key_identity.full_key_id,
                "overlap_days": overlap_days,
            },
        )

        return new_key


def create_kms_manager(provider_type: KMSProvider, **config) -> KMSManager:
    """Factory function to create KMS manager with specified provider."""

    if provider_type == KMSProvider.SOFTWARE_HSM:
        provider = SoftwareHSMProvider(config.get("storage_path", "/tmp/marty_software_hsm"))
    elif provider_type == KMSProvider.FILE_BASED:
        provider = FileBasedProvider(config.get("storage_path", "/tmp/marty_keys"))
    elif provider_type == KMSProvider.AWS_KMS:
        provider = AWSKMSProvider(
            region_name=config["region_name"],
            key_prefix=config.get("key_prefix", "marty/"),
            endpoint_url=config.get("endpoint_url"),
        )
    elif provider_type == KMSProvider.PKCS11_HSM:
        provider = PKCS11HSMProvider(
            library_path=config["library_path"],
            token_label=config["token_label"],
            user_pin=config["user_pin"],
        )
    elif provider_type == KMSProvider.AZURE_KEY_VAULT:
        provider = AzureKeyVaultProvider(
            vault_url=config["vault_url"],
            tenant_id=config.get("tenant_id"),
            client_id=config.get("client_id"),
            client_secret=config.get("client_secret"),
        )
    elif provider_type == KMSProvider.GCP_KMS:
        provider = GCPCloudKMSProvider(
            project_id=config["project_id"],
            location=config.get("location", "global"),
            key_ring=config.get("key_ring", "marty"),
            credentials_json=config.get("credentials_json"),
        )
    elif provider_type == KMSProvider.HASHICORP_VAULT:
        provider = HashiCorpVaultProvider(
            vault_addr=config["vault_addr"],
            token=config.get("token"),
            mount_point=config.get("mount_point", "transit"),
            namespace=config.get("namespace"),
        )
    else:
        raise NotImplementedError(f"Provider {provider_type} not implemented yet")

    return KMSManager(provider)


# Example usage
async def example_usage():
    """Example of using the KMS manager with role separation."""

    # Create KMS manager with software HSM for development
    kms = create_kms_manager(KMSProvider.SOFTWARE_HSM)

    # Generate CSCA key (requires HSM in production)
    csca_key = await kms.generate_key_for_role(
        role=CryptoRole.CSCA,
        purpose=KeyPurpose.CERTIFICATE_SIGNING,
        key_id="csca-us-001",
        algorithm="RSA2048",
        issuer_identifier="US",
        allow_software=True,  # Override HSM requirement for dev
    )

    # Generate DSC key
    dsc_key = await kms.generate_key_for_role(
        role=CryptoRole.DSC,
        purpose=KeyPurpose.DOCUMENT_SIGNING,
        key_id="dsc-us-passport-001",
        algorithm="ES256",
        issuer_identifier="US",
        allow_software=True,
    )

    # Generate evidence signing key
    evidence_key = await kms.generate_key_for_role(
        role=CryptoRole.EVIDENCE,
        purpose=KeyPurpose.EVIDENCE_SIGNING,
        key_id="evidence-verifier-001",
        algorithm="ES256",
    )

    # Example: Sign some data with DSC key
    data_to_sign = b"Document data to be signed"
    signature = await kms.sign_with_role_validation(
        key_identity=dsc_key.key_identity, data=data_to_sign, requesting_role=CryptoRole.DSC
    )

    # Example: Verifier getting public key (allowed)
    public_key = await kms.get_public_key_for_verification(
        key_identity=dsc_key.key_identity, requesting_role=CryptoRole.VERIFIER
    )

    print(f"Generated {len(await kms.list_keys_by_role(CryptoRole.DSC))} DSC keys")


if __name__ == "__main__":
    asyncio.run(example_usage())
