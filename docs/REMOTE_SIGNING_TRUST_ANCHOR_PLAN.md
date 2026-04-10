# Remote Signing & Trust Anchor Upload Implementation Plan

## Executive Summary

This document outlines the implementation plan for production tier organizations to:
1. **Upload custom trust anchor certificates** for credential verification
2. **Configure remote signing** with their own KMS/HSM providers
3. **Use remote signing** for credential issuance operations

## Current State Analysis

### ✅ What Already Exists

1. **Trust Anchor Upload API** (`src/digital_identity/infrastructure/adapters/rest/trust_anchors.py`)
   - `POST /v1/identity/trust-profiles/{profile_id}/anchors`
   - Uploads PEM certificates to trust profiles
   - Stores in `OrganizationCustomAnchor` entity
   - Repository: `CustomAnchorRepository`

2. **Subscription Tier System** (`src/subscription/`)
   - FREE & DEVS tiers: Service key vault (weekly/biweekly rotation)
   - STARTER, PROFESSIONAL, ENTERPRISE: Remote signing required
   - `requires_remote_signing` flag on plan limits

3. **Credential Template Remote Signing Config** (`src/digital_identity/domain/entities.py`)
   - `remote_signing_config` field for KMS configuration
   - Used in credential issuance service
   - Template-level configuration

4. **CSCA Trust Store** (`packages/marty-common/marty_common/crypto/csca_trust_store.py`)
   - Manages CSCA certificates with trust levels
   - Country-specific organization
   - Certificate validation and verification

5. **Key Vault Abstraction** (`packages/marty-common/marty_backend_common/infrastructure/key_vault.py`)
   - `FileKeyVaultClient` - File-based keys
   - `HashiCorpKeyVaultClient` - Vault Transit
   - `KeyVaultClient` protocol

### ❌ What's Missing

#### 1. Organization-Level Remote Signing Configuration
**Gap**: Organizations need to configure their KMS at the organization level, not just per credential template.

**Needed**:
- Organization model extension for KMS configuration
- API endpoints to configure organization KMS
- Secure storage of KMS credentials (encrypted)
- Support for multiple KMS providers

#### 2. Remote Signing Service/Adapter
**Gap**: No service to actually perform remote signing via customer KMS.

**Needed**:
- `RemoteSigningService` - Orchestrates remote signing operations
- KMS provider adapters (AWS, Azure, GCP, HashiCorp)
- Signing request/response models
- Error handling and retry logic

#### 3. KMS Provider Support
**Gap**: Only HashiCorp Vault and file-based keys supported.

**Needed**:
- AWS KMS client
- Azure Key Vault client  
- GCP Cloud KMS client
- Provider-specific configuration models

#### 4. Trust Anchor Management Tests
**Gap**: No tests for organizations uploading and managing trust anchors.

**Needed**:
- Upload trust anchor tests
- List/retrieve trust anchor tests
- Delete/revoke trust anchor tests
- Trust anchor validation tests
- Certificate expiry tests

#### 5. Remote Signing Workflow Tests
**Gap**: No tests verifying remote signing for production tiers.

**Needed**:
- Configure remote signing tests
- Sign with remote KMS tests
- Tier enforcement tests
- KMS provider-specific tests
- Error handling tests

#### 6. Trust Anchor to Organization Linking
**Gap**: Trust anchors are linked to trust profiles, not directly to organizations.

**Needed** (optional):
- Organization-level trust anchor storage
- Default trust anchors per organization
- Automatic trust profile population

---

## Implementation Plan

### Phase 1: Organization KMS Configuration (Foundation)

#### 1.1 Extend Organization Model

**File**: `src/subscription/models.py`

```python
class Organization(Base):
    # ... existing fields ...
    
    # Remote signing / KMS configuration
    kms_config: Mapped[dict] = mapped_column(
        JSONBType, 
        default=dict, 
        nullable=False,
        comment="KMS/HSM configuration for remote signing"
    )
    kms_provider: Mapped[Optional[str]] = mapped_column(
        String(50), 
        nullable=True,
        comment="KMS provider: aws_kms, azure_key_vault, gcp_kms, hashicorp_vault"
    )
    kms_credentials_encrypted: Mapped[Optional[str]] = mapped_column(
        Text, 
        nullable=True,
        comment="Encrypted KMS credentials/API keys"
    )
```

**KMS Config Structure**:
```python
{
    "provider": "aws_kms",  # or azure_key_vault, gcp_kms, hashicorp_vault
    "region": "us-west-2",
    "key_id": "arn:aws:kms:us-west-2:123456789012:key/...",
    "endpoint_url": "https://kms.us-west-2.amazonaws.com",
    "algorithm": "ECDSA_SHA_256",
    "metadata": {
        "key_alias": "marty-signing-key",
        "rotation_enabled": true
    }
}
```

#### 1.2 Create KMS Configuration Service

**File**: `src/subscription/kms_config_service.py`

```python
from dataclasses import dataclass
from typing import Optional
from cryptography.fernet import Fernet

@dataclass
class KMSProviderConfig:
    """KMS provider configuration."""
    provider: str
    region: Optional[str] = None
    key_id: Optional[str] = None
    endpoint_url: Optional[str] = None
    algorithm: str = "ECDSA_SHA_256"
    metadata: dict = field(default_factory=dict)

class KMSConfigService:
    """Manage organization KMS configuration."""
    
    def __init__(self, db: AsyncSession, encryption_key: bytes):
        self.db = db
        self.cipher = Fernet(encryption_key)
    
    async def configure_kms(
        self,
        organization: Organization,
        provider: str,
        credentials: dict,
        config: KMSProviderConfig,
    ) -> None:
        """Configure KMS for an organization."""
        # Validate subscription tier
        subscription = await self._get_subscription(organization.id)
        if not subscription:
            raise ValueError("No active subscription")
        
        plan = SquarePlan(subscription.plan)
        if not PLAN_LIMITS[plan].requires_remote_signing:
            raise ValueError(
                f"Tier {plan.value} uses service key vault. "
                "KMS configuration only for production tiers."
            )
        
        # Encrypt credentials
        credentials_json = json.dumps(credentials)
        encrypted = self.cipher.encrypt(credentials_json.encode())
        
        # Store configuration
        organization.kms_provider = provider
        organization.kms_config = asdict(config)
        organization.kms_credentials_encrypted = encrypted.decode()
        
        await self.db.commit()
    
    async def get_kms_config(
        self,
        organization: Organization,
    ) -> tuple[KMSProviderConfig, dict]:
        """Get KMS configuration and decrypted credentials."""
        if not organization.kms_provider:
            raise ValueError("KMS not configured for organization")
        
        config = KMSProviderConfig(**organization.kms_config)
        
        # Decrypt credentials
        encrypted = organization.kms_credentials_encrypted.encode()
        decrypted = self.cipher.decrypt(encrypted)
        credentials = json.loads(decrypted.decode())
        
        return config, credentials
```

#### 1.3 Create REST API Endpoints

**File**: `src/subscription/routes.py` (extend)

```python
@router.post(
    "/organizations/{org_id}/kms/configure",
    summary="Configure Remote Signing KMS",
)
async def configure_organization_kms(
    org_id: UUID,
    config: KMSConfigRequest,
    org: Organization = Depends(get_current_organization),
    kms_service: KMSConfigService = Depends(get_kms_config_service),
):
    """
    Configure KMS for remote signing (Production tiers only).
    
    Required for STARTER, PROFESSIONAL, and ENTERPRISE tiers.
    """
    # ... implementation

@router.get(
    "/organizations/{org_id}/kms",
    summary="Get KMS Configuration",
)
async def get_organization_kms_config(
    org_id: UUID,
    org: Organization = Depends(get_current_organization),
):
    """Get current KMS configuration (credentials redacted)."""
    # ... implementation

@router.delete(
    "/organizations/{org_id}/kms",
    summary="Remove KMS Configuration",
)
async def delete_organization_kms_config(
    org_id: UUID,
    org: Organization = Depends(get_current_organization),
):
    """Remove KMS configuration."""
    # ... implementation
```

---

### Phase 2: KMS Provider Adapters

#### 2.1 Create KMS Provider Protocol

**File**: `src/subscription/kms_providers.py`

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class KMSProvider(Protocol):
    """Protocol for KMS/HSM providers."""
    
    async def sign(
        self,
        key_id: str,
        payload: bytes,
        algorithm: str,
    ) -> bytes:
        """Sign payload using remote key."""
        ...
    
    async def get_public_key(self, key_id: str) -> bytes:
        """Get public key material."""
        ...
    
    async def verify_connectivity(self) -> bool:
        """Test KMS connectivity."""
        ...
```

#### 2.2 Implement AWS KMS Provider

**File**: `src/subscription/kms_providers/aws_kms.py`

```python
import boto3
from botocore.exceptions import ClientError

class AWSKMSProvider:
    """AWS KMS provider for remote signing."""
    
    def __init__(
        self,
        access_key_id: str,
        secret_access_key: str,
        region: str,
        endpoint_url: Optional[str] = None,
    ):
        self.client = boto3.client(
            'kms',
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=region,
            endpoint_url=endpoint_url,
        )
    
    async def sign(
        self,
        key_id: str,
        payload: bytes,
        algorithm: str = "ECDSA_SHA_256",
    ) -> bytes:
        """Sign using AWS KMS."""
        try:
            response = await asyncio.to_thread(
                self.client.sign,
                KeyId=key_id,
                Message=payload,
                MessageType='RAW',
                SigningAlgorithm=algorithm,
            )
            return response['Signature']
        except ClientError as e:
            raise SigningError(f"AWS KMS signing failed: {e}")
    
    async def get_public_key(self, key_id: str) -> bytes:
        """Get public key from AWS KMS."""
        try:
            response = await asyncio.to_thread(
                self.client.get_public_key,
                KeyId=key_id,
            )
            return response['PublicKey']
        except ClientError as e:
            raise SigningError(f"AWS KMS get_public_key failed: {e}")
    
    async def verify_connectivity(self) -> bool:
        """Test AWS KMS connectivity."""
        try:
            await asyncio.to_thread(self.client.list_keys, Limit=1)
            return True
        except Exception:
            return False
```

#### 2.3 Implement Azure Key Vault Provider

**File**: `src/subscription/kms_providers/azure_kv.py`

```python
from azure.identity import DefaultAzureCredential
from azure.keyvault.keys.crypto import CryptographyClient, SignatureAlgorithm

class AzureKeyVaultProvider:
    """Azure Key Vault provider for remote signing."""
    
    def __init__(
        self,
        vault_url: str,
        tenant_id: str,
        client_id: str,
        client_secret: str,
    ):
        self.vault_url = vault_url
        # Use service principal for authentication
        from azure.identity import ClientSecretCredential
        self.credential = ClientSecretCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
        )
    
    async def sign(
        self,
        key_id: str,
        payload: bytes,
        algorithm: str = "ES256",
    ) -> bytes:
        """Sign using Azure Key Vault."""
        key_url = f"{self.vault_url}/keys/{key_id}"
        crypto_client = CryptographyClient(key_url, self.credential)
        
        # Map algorithm
        az_algorithm = {
            "ES256": SignatureAlgorithm.es256,
            "ES384": SignatureAlgorithm.es384,
            "ES512": SignatureAlgorithm.es512,
            "RS256": SignatureAlgorithm.rs256,
        }.get(algorithm, SignatureAlgorithm.es256)
        
        result = await asyncio.to_thread(
            crypto_client.sign,
            az_algorithm,
            payload,
        )
        return result.signature
```

#### 2.4 Implement GCP KMS Provider

**File**: `src/subscription/kms_providers/gcp_kms.py`

```python
from google.cloud import kms

class GCPKMSProvider:
    """Google Cloud KMS provider for remote signing."""
    
    def __init__(
        self,
        project_id: str,
        location: str,
        key_ring: str,
        credentials_json: dict,
    ):
        self.project_id = project_id
        self.location = location
        self.key_ring = key_ring
        
        # Create client from service account credentials
        from google.oauth2 import service_account
        credentials = service_account.Credentials.from_service_account_info(
            credentials_json
        )
        self.client = kms.KeyManagementServiceClient(credentials=credentials)
    
    async def sign(
        self,
        key_id: str,
        payload: bytes,
        algorithm: str = "EC_SIGN_P256_SHA256",
    ) -> bytes:
        """Sign using GCP KMS."""
        # Build the key name
        key_name = (
            f"projects/{self.project_id}/locations/{self.location}/"
            f"keyRings/{self.key_ring}/cryptoKeys/{key_id}/"
            f"cryptoKeyVersions/1"
        )
        
        # Create the digest
        import hashlib
        digest = hashlib.sha256(payload).digest()
        
        # Call KMS
        response = await asyncio.to_thread(
            self.client.asymmetric_sign,
            request={
                "name": key_name,
                "digest": {"sha256": digest},
            }
        )
        return response.signature
```

#### 2.5 Create KMS Provider Factory

**File**: `src/subscription/kms_providers/__init__.py`

```python
def create_kms_provider(
    provider: str,
    credentials: dict,
    config: KMSProviderConfig,
) -> KMSProvider:
    """Factory to create KMS provider instances."""
    
    if provider == "aws_kms":
        from .aws_kms import AWSKMSProvider
        return AWSKMSProvider(
            access_key_id=credentials["access_key_id"],
            secret_access_key=credentials["secret_access_key"],
            region=config.region,
            endpoint_url=config.endpoint_url,
        )
    
    elif provider == "azure_key_vault":
        from .azure_kv import AzureKeyVaultProvider
        return AzureKeyVaultProvider(
            vault_url=config.endpoint_url,
            tenant_id=credentials["tenant_id"],
            client_id=credentials["client_id"],
            client_secret=credentials["client_secret"],
        )
    
    elif provider == "gcp_kms":
        from .gcp_kms import GCPKMSProvider
        return GCPKMSProvider(
            project_id=config.metadata["project_id"],
            location=config.region,
            key_ring=config.metadata["key_ring"],
            credentials_json=credentials,
        )
    
    elif provider == "hashicorp_vault":
        from marty_backend_common.infrastructure.key_vault import HashiCorpKeyVaultClient
        return HashiCorpKeyVaultClient(
            vault_addr=config.endpoint_url,
            auth_method=credentials.get("auth_method", "token"),
            mount_point=config.metadata.get("mount_point", "transit"),
        )
    
    else:
        raise ValueError(f"Unsupported KMS provider: {provider}")
```

---

### Phase 3: Remote Signing Service

#### 3.1 Create Remote Signing Service

**File**: `src/subscription/remote_signing_service.py`

```python
class RemoteSigningService:
    """
    Remote signing service for production tiers.
    
    Orchestrates signing operations using customer-provided KMS.
    """
    
    def __init__(
        self,
        db: AsyncSession,
        kms_config_service: KMSConfigService,
    ):
        self.db = db
        self.kms_config_service = kms_config_service
        self._provider_cache: dict[UUID, KMSProvider] = {}
    
    async def get_provider(
        self,
        organization: Organization,
    ) -> KMSProvider:
        """Get or create KMS provider for organization."""
        if organization.id in self._provider_cache:
            return self._provider_cache[organization.id]
        
        # Get configuration and credentials
        config, credentials = await self.kms_config_service.get_kms_config(
            organization
        )
        
        # Create provider
        provider = create_kms_provider(
            organization.kms_provider,
            credentials,
            config,
        )
        
        # Test connectivity
        if not await provider.verify_connectivity():
            raise SigningError(f"Cannot connect to {organization.kms_provider}")
        
        # Cache for reuse
        self._provider_cache[organization.id] = provider
        
        return provider
    
    async def sign(
        self,
        organization: Organization,
        key_id: str,
        payload: bytes,
        algorithm: Optional[str] = None,
    ) -> bytes:
        """
        Sign payload using organization's remote KMS.
        
        Args:
            organization: Organization performing the signing
            key_id: Key identifier in the KMS
            payload: Data to sign
            algorithm: Signing algorithm (uses org config if None)
        
        Returns:
            Signature bytes
        
        Raises:
            SigningError: If signing fails
            ValueError: If KMS not configured
        """
        # Verify tier requires remote signing
        subscription = await self._get_subscription(organization.id)
        if not subscription:
            raise SigningError("No active subscription")
        
        plan = SquarePlan(subscription.plan)
        if not PLAN_LIMITS[plan].requires_remote_signing:
            raise SigningError(
                f"Tier {plan.value} should use service key vault, "
                "not remote signing"
            )
        
        # Get KMS provider
        provider = await self.get_provider(organization)
        
        # Use configured algorithm if not specified
        if not algorithm:
            config, _ = await self.kms_config_service.get_kms_config(organization)
            algorithm = config.algorithm
        
        # Perform signing
        try:
            signature = await provider.sign(key_id, payload, algorithm)
            logger.info(
                f"Remote signing successful for org {organization.id} "
                f"using {organization.kms_provider}"
            )
            return signature
        except Exception as e:
            logger.error(f"Remote signing failed: {e}")
            raise SigningError(f"Remote signing failed: {e}")
    
    async def get_public_key(
        self,
        organization: Organization,
        key_id: str,
    ) -> bytes:
        """Get public key from organization's KMS."""
        provider = await self.get_provider(organization)
        return await provider.get_public_key(key_id)
```

#### 3.2 Integrate with Signing Service

**File**: `src/subscription/signing_service.py` (extend)

```python
class SigningService:
    def __init__(
        self,
        db: AsyncSession,
        service_key_vault: Optional[KeyVaultClient] = None,
        remote_signing_service: Optional[RemoteSigningService] = None,
    ):
        self.db = db
        self.service_key_vault = service_key_vault
        self.remote_signing_service = remote_signing_service
        self._key_rotation_tracker: dict[str, datetime] = {}
    
    async def sign(
        self,
        organization: Organization,
        key_id: str,
        payload: bytes,
        algorithm: str = "ecdsa-p256",
        force_rotation_check: bool = True,
    ) -> bytes:
        """Sign payload (routes to service vault or remote KMS)."""
        subscription = await self.get_subscription(organization)
        if not subscription:
            raise SigningError("No active subscription found")
        
        plan = SquarePlan(subscription.plan)
        
        # Route to appropriate signing method
        if self.requires_remote_signing(plan):
            # Production tier - use customer's KMS
            if not self.remote_signing_service:
                raise SigningError("Remote signing service not configured")
            
            return await self.remote_signing_service.sign(
                organization=organization,
                key_id=key_id,
                payload=payload,
                algorithm=algorithm,
            )
        else:
            # FREE/DEVS tier - use service key vault
            # ... existing service vault logic ...
```

---

### Phase 4: Comprehensive Tests

#### 4.1 Trust Anchor Upload Tests

**File**: `tests/subscription/test_trust_anchor_upload.py`

```python
"""
Tests for organization trust anchor certificate upload.

Tests organizations uploading custom X.509 certificates for:
- Custom trust profiles
- Supplementing standard frameworks (ICAO, AAMVA)
- Multi-issuer credential verification
"""
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

class TestTrustAnchorUpload:
    """Test trust anchor certificate upload."""
    
    @pytest.mark.asyncio
    async def test_upload_root_ca_certificate(
        self,
        authenticated_client,
        test_trust_profile,
    ):
        """Organizations can upload root CA certificates."""
        # Generate test certificate
        cert_pem = generate_test_certificate(
            subject="CN=Test Root CA,O=Test Org",
            is_ca=True,
        )
        
        response = await authenticated_client.post(
            f"/v1/identity/trust-profiles/{test_trust_profile.id}/anchors",
            json={
                "certificate_pem": cert_pem,
                "purpose": "verification",
                "anchor_type": "root_ca",
                "metadata": {"description": "Test root CA"},
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["anchor_type"] == "root_ca"
        assert data["purpose"] == "verification"
        assert "CN=Test Root CA" in data["subject"]
    
    @pytest.mark.asyncio
    async def test_upload_intermediate_certificate(
        self,
        authenticated_client,
        test_trust_profile,
    ):
        """Organizations can upload intermediate certificates."""
        # ... test implementation
    
    @pytest.mark.asyncio
    async def test_upload_invalid_certificate_fails(
        self,
        authenticated_client,
        test_trust_profile,
    ):
        """Uploading invalid certificates fails with clear error."""
        response = await authenticated_client.post(
            f"/v1/identity/trust-profiles/{test_trust_profile.id}/anchors",
            json={
                "certificate_pem": "INVALID_CERTIFICATE_DATA",
                "purpose": "verification",
            }
        )
        
        assert response.status_code == 400
        assert "invalid certificate" in response.json()["detail"].lower()
    
    @pytest.mark.asyncio
    async def test_list_uploaded_trust_anchors(
        self,
        authenticated_client,
        test_trust_profile,
        uploaded_anchors,
    ):
        """Organizations can list their uploaded trust anchors."""
        response = await authenticated_client.get(
            f"/v1/identity/trust-profiles/{test_trust_profile.id}/anchors"
        )
        
        assert response.status_code == 200
        anchors = response.json()
        assert len(anchors) == len(uploaded_anchors)
    
    @pytest.mark.asyncio
    async def test_delete_trust_anchor(
        self,
        authenticated_client,
        test_trust_profile,
        uploaded_anchor,
    ):
        """Organizations can delete their trust anchors."""
        response = await authenticated_client.delete(
            f"/v1/identity/trust-profiles/{test_trust_profile.id}/anchors/{uploaded_anchor.id}"
        )
        
        assert response.status_code == 204
    
    @pytest.mark.asyncio
    async def test_expired_certificate_warning(
        self,
        authenticated_client,
        test_trust_profile,
    ):
        """Uploading expired certificates shows warning."""
        # Generate expired certificate
        cert_pem = generate_test_certificate(
            subject="CN=Expired CA",
            days_valid=-30,  # Expired 30 days ago
        )
        
        response = await authenticated_client.post(
            f"/v1/identity/trust-profiles/{test_trust_profile.id}/anchors",
            json={"certificate_pem": cert_pem}
        )
        
        # Should succeed but with warning
        assert response.status_code == 201
        assert "expired" in response.json().get("warnings", [])
```

#### 4.2 Remote Signing Configuration Tests

**File**: `tests/subscription/test_remote_signing_config.py`

```python
"""
Tests for organization remote signing configuration.

Tests production tier organizations configuring their own KMS/HSM
for remote signing operations.
"""
import pytest

class TestRemoteSigningConfiguration:
    """Test organization KMS configuration."""
    
    @pytest.mark.asyncio
    async def test_configure_aws_kms(
        self,
        authenticated_client,
        starter_organization,
        starter_subscription,
    ):
        """STARTER tier can configure AWS KMS."""
        response = await authenticated_client.post(
            f"/v1/subscriptions/organizations/{starter_organization.id}/kms/configure",
            json={
                "provider": "aws_kms",
                "credentials": {
                    "access_key_id": "AKIAIOSFODNN7EXAMPLE",
                    "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                },
                "config": {
                    "region": "us-west-2",
                    "key_id": "arn:aws:kms:us-west-2:123456789012:key/12345678-1234-1234-1234-123456789012",
                    "algorithm": "ECDSA_SHA_256",
                }
            }
        )
        
        assert response.status_code == 200
        assert response.json()["provider"] == "aws_kms"
    
    @pytest.mark.asyncio
    async def test_free_tier_cannot_configure_kms(
        self,
        authenticated_client,
        free_organization,
        free_subscription,
    ):
        """FREE tier cannot configure KMS (uses service vault)."""
        response = await authenticated_client.post(
            f"/v1/subscriptions/organizations/{free_organization.id}/kms/configure",
            json={
                "provider": "aws_kms",
                "credentials": {"access_key_id": "...", "secret_access_key": "..."},
                "config": {"region": "us-west-2", "key_id": "..."},
            }
        )
        
        assert response.status_code == 400
        assert "free" in response.json()["detail"].lower()
        assert "service key vault" in response.json()["detail"].lower()
    
    @pytest.mark.asyncio
    async def test_configure_azure_key_vault(
        self,
        authenticated_client,
        professional_organization,
    ):
        """PROFESSIONAL tier can configure Azure Key Vault."""
        # ... test implementation
    
    @pytest.mark.asyncio
    async def test_get_kms_configuration_redacts_credentials(
        self,
        authenticated_client,
        starter_organization_with_kms,
    ):
        """Getting KMS config redacts sensitive credentials."""
        response = await authenticated_client.get(
            f"/v1/subscriptions/organizations/{starter_organization_with_kms.id}/kms"
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "aws_kms"
        assert "region" in data["config"]
        # Credentials should be redacted
        assert "credentials" not in data
        assert "access_key_id" not in str(data)
```

#### 4.3 Remote Signing Workflow Tests

**File**: `tests/subscription/test_remote_signing_workflow.py`

```python
"""
Tests for remote signing workflows.

Tests end-to-end signing operations using customer KMS/HSM.
"""
import pytest

class TestRemoteSigningWorkflow:
    """Test remote signing operations."""
    
    @pytest.mark.asyncio
    async def test_sign_with_aws_kms(
        self,
        remote_signing_service,
        starter_organization_with_aws_kms,
        mock_aws_kms,
    ):
        """Organizations can sign using AWS KMS."""
        payload = b"test data to sign"
        
        signature = await remote_signing_service.sign(
            organization=starter_organization_with_aws_kms,
            key_id="arn:aws:kms:us-west-2:123:key/abc",
            payload=payload,
        )
        
        assert signature
        assert isinstance(signature, bytes)
        # Verify AWS KMS was called
        mock_aws_kms.sign.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_public_key_from_kms(
        self,
        remote_signing_service,
        starter_organization_with_aws_kms,
        mock_aws_kms,
    ):
        """Organizations can retrieve public keys from their KMS."""
        public_key = await remote_signing_service.get_public_key(
            organization=starter_organization_with_aws_kms,
            key_id="arn:aws:kms:us-west-2:123:key/abc",
        )
        
        assert public_key
        mock_aws_kms.get_public_key.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_kms_connectivity_failure(
        self,
        remote_signing_service,
        starter_organization_with_invalid_kms,
    ):
        """Clear error when KMS connectivity fails."""
        with pytest.raises(SigningError) as exc_info:
            await remote_signing_service.sign(
                organization=starter_organization_with_invalid_kms,
                key_id="invalid-key",
                payload=b"data",
            )
        
        assert "cannot connect" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_free_tier_cannot_use_remote_signing(
        self,
        remote_signing_service,
        free_organization,
    ):
        """FREE tier cannot use remote signing service."""
        with pytest.raises(SigningError) as exc_info:
            await remote_signing_service.sign(
                organization=free_organization,
                key_id="some-key",
                payload=b"data",
            )
        
        assert "free" in str(exc_info.value).lower()
        assert "service key vault" in str(exc_info.value).lower()
```

#### 4.4 Integration Tests

**File**: `tests/integration/test_remote_signing_integration.py`

```python
"""
Integration tests for full remote signing workflows.

Tests complete credential issuance flow using customer KMS.
"""
import pytest

class TestRemoteSigningIntegration:
    """Integration tests for remote signing."""
    
    @pytest.mark.asyncio
    async def test_issue_credential_with_remote_kms(
        self,
        credential_issuance_service,
        starter_organization_with_aws_kms,
        credential_template_with_remote_signing,
    ):
        """Issue credential signed with customer's AWS KMS."""
        credential = await credential_issuance_service.issue_credential(
            template=credential_template_with_remote_signing,
            subject_data={
                "given_name": "John",
                "family_name": "Doe",
                "birth_date": "1980-01-01",
            },
            organization=starter_organization_with_aws_kms,
        )
        
        assert credential.id
        assert credential.signature
        # Verify signature was created using AWS KMS
        # ... verification logic
    
    @pytest.mark.asyncio
    async def test_verify_credential_with_uploaded_trust_anchor(
        self,
        verification_service,
        issued_credential,
        trust_profile_with_custom_anchor,
    ):
        """Verify credential using uploaded trust anchor."""
        result = await verification_service.verify_credential(
            credential=issued_credential,
            trust_profile=trust_profile_with_custom_anchor,
        )
        
        assert result.is_valid
        assert result.trust_chain_valid
```

---

### Phase 5: Documentation & Examples

#### 5.1 Configuration Guide

**File**: `docs/REMOTE_SIGNING_CONFIGURATION.md`

- Getting started with remote signing
- Supported KMS providers
- Configuration examples for each provider
- Security best practices
- Troubleshooting guide

#### 5.2 API Documentation

- OpenAPI/Swagger specs for KMS configuration endpoints
- Trust anchor upload API docs
- Example requests/responses

#### 5.3 Code Examples

**File**: `examples/remote_signing_example.py`

```python
"""
Example: Configure and use remote signing with AWS KMS.
"""
import asyncio

async def configure_and_sign_example():
    # 1. Configure AWS KMS
    await configure_aws_kms(
        organization_id="org-123",
        access_key_id="AKIA...",
        secret_access_key="...",
        region="us-west-2",
        key_id="arn:aws:kms:...",
    )
    
    # 2. Upload trust anchor
    await upload_trust_anchor(
        organization_id="org-123",
        certificate_pem=load_certificate("ca.pem"),
    )
    
    # 3. Sign credential
    signature = await sign_credential(
        organization_id="org-123",
        payload=credential_data,
    )
    
    print(f"Signed with AWS KMS: {signature.hex()}")
```

---

## Implementation Timeline

### Week 1: Foundation
- [ ] Extend Organization model with KMS fields
- [ ] Create KMSConfigService
- [ ] Create KMS configuration API endpoints
- [ ] Write configuration tests

### Week 2: KMS Providers
- [ ] Implement AWS KMS provider
- [ ] Implement Azure Key Vault provider
- [ ] Implement GCP KMS provider
- [ ] Create provider factory
- [ ] Write provider-specific tests

### Week 3: Remote Signing Service
- [ ] Create RemoteSigningService
- [ ] Integrate with SigningService
- [ ] Add tier enforcement
- [ ] Write remote signing workflow tests

### Week 4: Trust Anchor Tests & Integration
- [ ] Write trust anchor upload tests
- [ ] Write integration tests
- [ ] End-to-end credential issuance tests
- [ ] Performance testing

### Week 5: Documentation & Polish
- [ ] Write configuration guide
- [ ] Create API documentation
- [ ] Write code examples
- [ ] Security audit
- [ ] Final testing and bug fixes

---

## Security Considerations

### Credential Encryption
- KMS credentials MUST be encrypted at rest
- Use Fernet (symmetric encryption) with key rotation
- Store encryption key in environment variable or secret manager
- Never log decrypted credentials

### Access Control
- Only organization admins can configure KMS
- API endpoint authentication required
- Rate limiting on KMS configuration changes
- Audit logging for all KMS operations

### Validation
- Validate KMS connectivity before saving configuration
- Test signing with a no-op operation
- Certificate validation on upload (expiry, chain, format)
- Algorithm validation (ensure supported by KMS)

### Error Handling
- Never expose KMS credentials in error messages
- Generic error messages for auth failures
- Detailed logging server-side only
- Circuit breaker for repeated KMS failures

---

## Testing Strategy

### Unit Tests
- KMS provider adapters (mock KMS calls)
- Configuration service logic
- Encryption/decryption
- Provider factory

### Integration Tests
- Real KMS connectivity (dev/staging only)
- Trust anchor upload workflow
- Full signing workflow
- Error scenarios

### E2E Tests
- Complete credential issuance with remote KMS
- Verification with uploaded trust anchors
- Multi-tier organization workflows

### Performance Tests
- KMS signing latency
- Concurrent signing operations
- Provider connection pooling

---

## Success Metrics

### Functionality
- ✅ All KMS providers working
- ✅ 100% test coverage
- ✅ Zero credential exposure
- ✅ Sub-second signing operations

### Documentation
- ✅ Configuration guide complete
- ✅ API docs published
- ✅ 3+ working examples

### Security
- ✅ Credentials encrypted at rest
- ✅ Audit logging implemented
- ✅ Security review passed
- ✅ Penetration test completed

---

## Future Enhancements

### Near-term (3-6 months)
- [ ] Support for PKCS#11 HSMs
- [ ] Key rotation automation
- [ ] Multi-region KMS support
- [ ] KMS failover/redundancy

### Long-term (6-12 months)
- [ ] Automated trust anchor discovery
- [ ] Trust anchor rotation workflows
- [ ] Certificate revocation checking for uploaded anchors
- [ ] Trust anchor compliance scoring

---

## Questions & Decisions Needed

1. **Encryption Key Management**: Where to store the Fernet encryption key? Environment variable vs secret manager?

2. **KMS Credentials Scope**: Should we support multiple KMS configurations per organization (dev/staging/prod)?

3. **Trust Anchor Approval**: Should uploaded trust anchors require admin approval before use?

4. **Rate Limiting**: Aggressive rate limiting on KMS operations to prevent abuse?

5. **Billing**: Should we meter/charge for remote signing operations separately?

6. **Monitoring**: What metrics should we track for remote signing?
   - Success/failure rates
   - Latency percentiles
   - KMS provider distribution
   - Certificate expiry alerts

---

## Appendix: API Schemas

### KMS Configuration Request
```json
{
  "provider": "aws_kms",
  "credentials": {
    "access_key_id": "AKIAIOSFODNN7EXAMPLE",
    "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
  },
  "config": {
    "region": "us-west-2",
    "key_id": "arn:aws:kms:us-west-2:123456789012:key/12345678-1234-1234-1234-123456789012",
    "algorithm": "ECDSA_SHA_256",
    "endpoint_url": null,
    "metadata": {
      "key_alias": "marty-signing-key",
      "rotation_enabled": true
    }
  }
}
```

### Trust Anchor Upload Request
```json
{
  "certificate_pem": "-----BEGIN CERTIFICATE-----\\n...\\n-----END CERTIFICATE-----",
  "purpose": "verification",
  "anchor_type": "root_ca",
  "metadata": {
    "description": "Company Root CA",
    "issuer_country": "US",
    "contact_email": "security@example.com"
  }
}
```

### Trust Anchor Upload Response
```json
{
  "id": "anchor-123",
  "profile_id": "profile-456",
  "anchor_type": "root_ca",
  "subject": "CN=Example Root CA,O=Example Corp,C=US",
  "issuer": "CN=Example Root CA,O=Example Corp,C=US",
  "not_before": "2024-01-01T00:00:00Z",
  "not_after": "2034-01-01T00:00:00Z",
  "purpose": "verification",
  "uploaded_by": "user-789",
  "uploaded_at": "2026-04-06T10:00:00Z",
  "created_at": "2026-04-06T10:00:00Z"
}
```
