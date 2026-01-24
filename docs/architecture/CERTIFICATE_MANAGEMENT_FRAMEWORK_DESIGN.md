# Certificate Management Framework Design

## Overview

This document outlines the design for abstracting Marty's certificate management capabilities into the Marty Microservices Framework (MMF) as a pluggable module. This will eliminate duplication and provide reusable PKI primitives for other services.

## Current Certificate Management Components in Marty

### 1. Certificate Expiry Notification Service
- **Location**: `src/trust_anchor/app/services/certificate_expiry_service.py`
- **Purpose**: Monitors certificate expiration and sends notifications
- **Key Features**:
  - Configurable notification thresholds (30, 15, 7, 3, 1 days)
  - Notification history tracking to prevent duplicates
  - Integration with OpenXPKI for certificate data
  - Background service with periodic checks

### 2. OpenXPKI Integration Layer
- **Location**: `src/marty_common/services/base_openxpki_service.py`
- **Purpose**: Base service for PKI operations
- **Key Features**:
  - Session management and authentication
  - Certificate import/export operations
  - Master list management
  - Error handling and retry logic

### 3. Certificate Parser and Validator
- **Location**: `services/trust-svc/certificate_parser.py`
- **Purpose**: Advanced X.509 certificate parsing
- **Key Features**:
  - ICAO-specific extension parsing
  - Certificate chain validation
  - Trust path construction
  - Multiple format support (PEM, DER)

### 4. Trust Store Management
- **Location**: Various services (trust-svc, trust-anchor, pkd-service)
- **Purpose**: Certificate storage and retrieval
- **Key Features**:
  - Vault integration for secure storage
  - Certificate rotation management
  - Chain building and verification

## Proposed Certificate Management Framework Architecture

### Core Components

#### 1. Certificate Manager Plugin Interface

```python
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta

@dataclass
class CertificateInfo:
    """Standardized certificate information container."""
    serial_number: str
    subject: str
    issuer: str
    not_before: datetime
    not_after: datetime
    country_code: Optional[str] = None
    certificate_type: Optional[str] = None
    fingerprint_sha256: str = ""
    status: str = "valid"  # valid, expired, revoked, pending

@dataclass
class ExpiryNotificationConfig:
    """Configuration for certificate expiry notifications."""
    notification_days: List[int] = field(default_factory=lambda: [30, 15, 7, 3, 1])
    check_interval_hours: int = 24
    history_enabled: bool = True
    history_storage_path: Optional[str] = None

@dataclass
class CertificateStoreConfig:
    """Configuration for certificate storage backend."""
    store_type: str  # vault, file, database
    connection_params: Dict[str, Any] = field(default_factory=dict)
    encryption_enabled: bool = True
    backup_enabled: bool = True

class ICertificateAuthorityClient(ABC):
    """Interface for Certificate Authority clients."""
    
    @abstractmethod
    async def get_certificates(self, filter_params: Optional[Dict[str, Any]] = None) -> List[CertificateInfo]:
        """Retrieve certificates from the CA."""
        pass
    
    @abstractmethod
    async def get_expiring_certificates(self, days_threshold: int) -> List[CertificateInfo]:
        """Get certificates expiring within the specified days."""
        pass
    
    @abstractmethod
    async def import_certificate(self, cert_data: bytes, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Import a certificate into the CA."""
        pass
    
    @abstractmethod
    async def revoke_certificate(self, serial_number: str, reason: str) -> bool:
        """Revoke a certificate."""
        pass

class ICertificateStore(ABC):
    """Interface for certificate storage backends."""
    
    @abstractmethod
    async def store_certificate(self, cert_id: str, cert_data: bytes, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Store a certificate."""
        pass
    
    @abstractmethod
    async def retrieve_certificate(self, cert_id: str) -> Optional[bytes]:
        """Retrieve a certificate by ID."""
        pass
    
    @abstractmethod
    async def list_certificates(self, filter_params: Optional[Dict[str, Any]] = None) -> List[str]:
        """List certificate IDs."""
        pass
    
    @abstractmethod
    async def delete_certificate(self, cert_id: str) -> bool:
        """Delete a certificate."""
        pass

class ICertificateParser(ABC):
    """Interface for certificate parsing."""
    
    @abstractmethod
    def parse_certificate(self, cert_data: bytes) -> CertificateInfo:
        """Parse certificate data into structured information."""
        pass
    
    @abstractmethod
    def validate_certificate(self, cert_data: bytes, trusted_cas: List[bytes]) -> bool:
        """Validate certificate against trusted CAs."""
        pass
    
    @abstractmethod
    def build_certificate_chain(self, cert_data: bytes, intermediate_certs: List[bytes]) -> List[bytes]:
        """Build complete certificate chain."""
        pass

class INotificationProvider(ABC):
    """Interface for certificate notification providers."""
    
    @abstractmethod
    async def send_expiry_notification(self, cert_info: CertificateInfo, days_remaining: int) -> bool:
        """Send certificate expiry notification."""
        pass
    
    @abstractmethod
    async def send_revocation_notification(self, cert_info: CertificateInfo) -> bool:
        """Send certificate revocation notification."""
        pass
```

#### 2. Certificate Management Plugin

```python
from marty_chassis.plugins import IServicePlugin, plugin
import asyncio
from typing import Dict, List, Optional

@plugin(
    name="certificate-management",
    version="1.0.0",
    description="Comprehensive certificate management with monitoring and notifications",
    author="Marty Team",
    provides=["certificate-management", "pki", "security", "monitoring"],
    dependencies=["observability", "security"]
)
class CertificateManagementPlugin(IServicePlugin):
    """
    Certificate Management Plugin for MMF.
    
    Provides comprehensive certificate lifecycle management including:
    - Certificate Authority integration
    - Expiry monitoring and notifications
    - Certificate storage and rotation
    - Trust chain validation
    """
    
    def __init__(self):
        super().__init__()
        self.ca_clients: Dict[str, ICertificateAuthorityClient] = {}
        self.certificate_stores: Dict[str, ICertificateStore] = {}
        self.parsers: Dict[str, ICertificateParser] = {}
        self.notification_providers: Dict[str, INotificationProvider] = {}
        self.expiry_monitor_task: Optional[asyncio.Task] = None
        self.config: CertificateManagerConfig = None
    
    async def initialize(self, context):
        """Initialize the certificate management plugin."""
        self.logger = context.logger
        self.config = self._load_config(context.config)
        
        # Register certificate management extension points
        await self._register_extension_points(context)
        
        # Initialize storage backends
        await self._initialize_stores()
        
        # Initialize CA clients
        await self._initialize_ca_clients()
        
        # Initialize parsers
        await self._initialize_parsers()
        
        # Initialize notification providers
        await self._initialize_notification_providers()
        
        self.logger.info("Certificate Management Plugin initialized")
    
    async def start(self):
        """Start the certificate management services."""
        # Start expiry monitoring
        if self.config.expiry_monitoring.enabled:
            self.expiry_monitor_task = asyncio.create_task(self._expiry_monitoring_loop())
            self.logger.info("Certificate expiry monitoring started")
        
        # Register health checks
        await self._register_health_checks()
    
    async def stop(self):
        """Stop the certificate management services."""
        if self.expiry_monitor_task:
            self.expiry_monitor_task.cancel()
            try:
                await self.expiry_monitor_task
            except asyncio.CancelledError:
                pass
        
        # Cleanup resources
        await self._cleanup_resources()
        
        self.logger.info("Certificate Management Plugin stopped")
    
    # Certificate Authority Operations
    async def register_ca_client(self, name: str, client: ICertificateAuthorityClient):
        """Register a Certificate Authority client."""
        self.ca_clients[name] = client
        self.logger.info(f"Registered CA client: {name}")
    
    async def get_certificates_from_ca(self, ca_name: str, filter_params: Optional[Dict] = None) -> List[CertificateInfo]:
        """Get certificates from a specific CA."""
        if ca_name not in self.ca_clients:
            raise ValueError(f"CA client '{ca_name}' not found")
        
        return await self.ca_clients[ca_name].get_certificates(filter_params)
    
    async def get_expiring_certificates(self, ca_name: str, days_threshold: int) -> List[CertificateInfo]:
        """Get expiring certificates from a CA."""
        if ca_name not in self.ca_clients:
            raise ValueError(f"CA client '{ca_name}' not found")
        
        return await self.ca_clients[ca_name].get_expiring_certificates(days_threshold)
    
    # Certificate Storage Operations
    async def register_certificate_store(self, name: str, store: ICertificateStore):
        """Register a certificate storage backend."""
        self.certificate_stores[name] = store
        self.logger.info(f"Registered certificate store: {name}")
    
    async def store_certificate(self, store_name: str, cert_id: str, cert_data: bytes, metadata: Optional[Dict] = None):
        """Store a certificate in the specified store."""
        if store_name not in self.certificate_stores:
            raise ValueError(f"Certificate store '{store_name}' not found")
        
        await self.certificate_stores[store_name].store_certificate(cert_id, cert_data, metadata)
    
    # Certificate Parsing Operations
    async def register_certificate_parser(self, name: str, parser: ICertificateParser):
        """Register a certificate parser."""
        self.parsers[name] = parser
        self.logger.info(f"Registered certificate parser: {name}")
    
    def parse_certificate(self, parser_name: str, cert_data: bytes) -> CertificateInfo:
        """Parse certificate using the specified parser."""
        if parser_name not in self.parsers:
            raise ValueError(f"Certificate parser '{parser_name}' not found")
        
        return self.parsers[parser_name].parse_certificate(cert_data)
    
    # Notification Operations
    async def register_notification_provider(self, name: str, provider: INotificationProvider):
        """Register a notification provider."""
        self.notification_providers[name] = provider
        self.logger.info(f"Registered notification provider: {name}")
    
    async def send_expiry_notification(self, cert_info: CertificateInfo, days_remaining: int):
        """Send expiry notification using all registered providers."""
        for name, provider in self.notification_providers.items():
            try:
                await provider.send_expiry_notification(cert_info, days_remaining)
                self.logger.info(f"Expiry notification sent via {name}")
            except Exception as e:
                self.logger.error(f"Failed to send notification via {name}: {e}")
    
    # Private Methods
    async def _expiry_monitoring_loop(self):
        """Background task for monitoring certificate expiry."""
        while True:
            try:
                await self._check_certificate_expiry()
                
                # Wait for next check
                interval_seconds = self.config.expiry_monitoring.check_interval_hours * 3600
                await asyncio.sleep(interval_seconds)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in expiry monitoring: {e}")
                await asyncio.sleep(300)  # Wait 5 minutes before retry
    
    async def _check_certificate_expiry(self):
        """Check for expiring certificates and send notifications."""
        for ca_name, ca_client in self.ca_clients.items():
            try:
                # Check for certificates expiring within the maximum threshold
                max_days = max(self.config.expiry_monitoring.notification_days)
                expiring_certs = await ca_client.get_expiring_certificates(max_days)
                
                for cert in expiring_certs:
                    days_remaining = (cert.not_after - datetime.now()).days
                    
                    # Check if we should send notification for this threshold
                    if days_remaining in self.config.expiry_monitoring.notification_days:
                        if await self._should_send_notification(cert, days_remaining):
                            await self.send_expiry_notification(cert, days_remaining)
                            await self._record_notification_sent(cert, days_remaining)
                
            except Exception as e:
                self.logger.error(f"Error checking expiry for CA {ca_name}: {e}")
    
    async def _should_send_notification(self, cert: CertificateInfo, days_remaining: int) -> bool:
        """Check if notification should be sent based on history."""
        if not self.config.expiry_monitoring.history_enabled:
            return True
        
        # Implementation would check notification history
        # This is a simplified version
        return True
    
    async def _record_notification_sent(self, cert: CertificateInfo, days_remaining: int):
        """Record that a notification was sent."""
        # Implementation would store notification history
        pass
```

#### 3. Concrete Implementations

```python
# OpenXPKI Certificate Authority Client
class OpenXPKICertificateAuthorityClient(ICertificateAuthorityClient):
    """OpenXPKI implementation of Certificate Authority client."""
    
    def __init__(self, config: Dict[str, Any]):
        self.base_url = config.get("base_url")
        self.username = config.get("username")
        self.password = config.get("password")
        self.realm = config.get("realm", "marty")
        # ... initialization
    
    async def get_certificates(self, filter_params: Optional[Dict[str, Any]] = None) -> List[CertificateInfo]:
        """Retrieve certificates from OpenXPKI."""
        # Implementation using existing OpenXPKI integration
        pass
    
    async def get_expiring_certificates(self, days_threshold: int) -> List[CertificateInfo]:
        """Get expiring certificates from OpenXPKI."""
        # Implementation using existing expiry check logic
        pass

# Vault Certificate Store
class VaultCertificateStore(ICertificateStore):
    """Vault implementation of certificate storage."""
    
    def __init__(self, config: Dict[str, Any]):
        self.vault_client = self._create_vault_client(config)
        self.mount_point = config.get("mount_point", "secret")
    
    async def store_certificate(self, cert_id: str, cert_data: bytes, metadata: Optional[Dict[str, Any]] = None):
        """Store certificate in Vault."""
        # Implementation using existing Vault client
        pass

# ICAO X.509 Certificate Parser
class ICAOCertificateParser(ICertificateParser):
    """ICAO-aware X.509 certificate parser."""
    
    def __init__(self):
        # Use existing certificate parser logic
        pass
    
    def parse_certificate(self, cert_data: bytes) -> CertificateInfo:
        """Parse certificate with ICAO extensions support."""
        # Implementation using existing parser
        pass

# Logging Notification Provider
class LoggingNotificationProvider(INotificationProvider):
    """Simple logging-based notification provider."""
    
    def __init__(self, logger):
        self.logger = logger
    
    async def send_expiry_notification(self, cert_info: CertificateInfo, days_remaining: int) -> bool:
        """Send notification via logging."""
        self.logger.warning(
            f"CERTIFICATE EXPIRY NOTIFICATION: Certificate {cert_info.serial_number} "
            f"for {cert_info.country_code} expires in {days_remaining} days"
        )
        return True
```

## Configuration Schema

```yaml
# Certificate Management Plugin Configuration
certificate_management:
  enabled: true
  
  # Certificate Authority configurations
  certificate_authorities:
    openxpki:
      type: "openxpki"
      base_url: "${OPENXPKI_BASE_URL:-https://localhost:8443/api/v2}"
      username: "${OPENXPKI_USERNAME}"
      password: "${OPENXPKI_PASSWORD}"
      realm: "${OPENXPKI_REALM:-marty}"
      verify_ssl: "${OPENXPKI_VERIFY_SSL:-false}"
      connection_timeout: 30
      read_timeout: 60
  
  # Certificate stores configuration
  certificate_stores:
    vault:
      type: "vault"
      url: "${VAULT_URL:-http://localhost:8200}"
      token: "${VAULT_TOKEN}"
      mount_point: "secret"
      path_prefix: "certificates/"
    
    file:
      type: "file"
      base_path: "${CERT_STORAGE_PATH:-data/certificates}"
      backup_enabled: true
      encryption_enabled: true
  
  # Certificate parsers configuration
  certificate_parsers:
    icao:
      type: "icao"
      validate_extensions: true
      strict_mode: false
    
    standard:
      type: "x509"
      basic_validation: true
  
  # Notification providers configuration
  notification_providers:
    logging:
      type: "logging"
      level: "WARNING"
    
    email:
      type: "email"
      smtp_host: "${SMTP_HOST}"
      smtp_port: "${SMTP_PORT:-587}"
      username: "${SMTP_USERNAME}"
      password: "${SMTP_PASSWORD}"
      from_address: "${CERT_NOTIFICATIONS_FROM}"
      to_addresses: 
        - "${CERT_ADMIN_EMAIL}"
    
    webhook:
      type: "webhook"
      url: "${CERT_WEBHOOK_URL}"
      headers:
        Authorization: "Bearer ${CERT_WEBHOOK_TOKEN}"
  
  # Expiry monitoring configuration
  expiry_monitoring:
    enabled: true
    check_interval_hours: 24
    notification_days: [30, 15, 7, 3, 1]
    history_enabled: true
    history_storage: "file"  # file, database, memory
    history_path: "${DATA_DIR:-data}/cert_notification_history.json"
  
  # Certificate validation configuration
  validation:
    strict_mode: false
    check_revocation: true
    verify_chain: true
    allow_self_signed: false
    
  # Security settings
  security:
    encrypt_stored_certificates: true
    audit_all_operations: true
    require_secure_transport: true
```

## Integration Points with Existing MMF Components

### 1. Security Framework Integration
- Leverage existing mTLS and authentication components
- Use MMF's security configuration patterns
- Integrate with RBAC for certificate management permissions

### 2. Observability Integration
- Emit metrics for certificate operations
- Integrate with distributed tracing
- Use structured logging patterns

### 3. Plugin Architecture Integration
- Register as MMF service plugin
- Use extension points for custom CA clients
- Leverage plugin lifecycle management

### 4. Configuration Management Integration
- Use MMF's configuration system
- Support environment-specific overrides
- Integrate with secret management

## Benefits of This Approach

1. **Elimination of Duplication**: Single source of truth for certificate management
2. **Reusability**: Other services can use the same PKI primitives
3. **Pluggability**: Support for multiple CA backends, storage systems, and notification providers
4. **Standardization**: Consistent interfaces across all certificate operations
5. **Observability**: Built-in monitoring and alerting
6. **Security**: Leverages MMF's security framework
7. **Scalability**: Asynchronous operations and efficient resource management

## Migration Strategy

### Phase 1: Framework Implementation
1. Implement core interfaces and plugin structure
2. Create OpenXPKI CA client implementation
3. Implement Vault storage backend
4. Create basic notification providers

### Phase 2: Marty Service Migration
1. Migrate Certificate Expiry Service to use plugin
2. Update Trust Anchor Service to use framework
3. Migrate PKD Service certificate operations
4. Update configuration and deployment

### Phase 3: Enhancement and Optimization
1. Add additional CA client implementations
2. Implement advanced notification providers
3. Add certificate rotation automation
4. Performance optimization and monitoring