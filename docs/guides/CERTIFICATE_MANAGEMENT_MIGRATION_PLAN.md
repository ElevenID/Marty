# Certificate Management Migration Plan

## Executive Summary

This document provides a detailed implementation plan for migrating Marty's certificate management capabilities into the Marty Microservices Framework (MMF) as a pluggable module. This migration will eliminate code duplication, provide reusable PKI primitives, and enable other services to leverage enterprise-grade certificate management capabilities.

## Migration Goals

1. **Eliminate Duplication**: Consolidate certificate management logic from multiple Marty services
2. **Enable Reusability**: Provide pluggable certificate management for other MMF-based services  
3. **Maintain Specialization**: Preserve Marty's ICAO PKI requirements and OpenXPKI integration
4. **Improve Maintainability**: Single source of truth for certificate operations
5. **Enhance Observability**: Built-in monitoring and alerting for certificate operations

## Current State Analysis

### Certificate Management Components in Marty

| Component | Location | Purpose | Dependencies |
|-----------|----------|---------|--------------|
| Certificate Expiry Service | `src/trust_anchor/app/services/certificate_expiry_service.py` | Monitor cert expiry, send notifications | OpenXPKI Service |
| Base OpenXPKI Service | `src/marty_common/services/base_openxpki_service.py` | OpenXPKI integration layer | requests, urllib3 |
| Certificate Parser | `services/trust-svc/certificate_parser.py` | X.509 parsing with ICAO extensions | cryptography |
| Vault Client | `services/trust-svc/vault_client.py` | Certificate storage in Vault | hvac |
| Trust Store Management | Multiple services | Certificate validation and chains | Various |

### Identified Duplication Areas

1. **OpenXPKI Integration**: Similar patterns across Trust Anchor and PKD services
2. **Certificate Storage**: Vault integration duplicated across services
3. **Expiry Monitoring**: Basic monitoring logic could be reused
4. **Certificate Validation**: Similar validation patterns in multiple services

## Migration Strategy

### Phase 1: Foundation (4-6 weeks)

#### 1.1 Create Certificate Management Plugin Structure

**Location**: `marty-microservices-framework/marty_chassis/plugins/certificate_management/`

**Tasks**:
- [ ] Implement core plugin interfaces
- [ ] Create plugin registry and lifecycle management
- [ ] Establish configuration schema
- [ ] Implement basic logging and error handling

**Deliverables**:
```
marty_chassis/plugins/certificate_management/
├── __init__.py
├── interfaces.py                 # Core interfaces (ICertificateStore, etc.)
├── plugin.py                     # Main plugin implementation  
├── config.py                     # Configuration management
├── exceptions.py                 # Custom exceptions
├── models.py                     # Data models (CertificateInfo, etc.)
└── utils.py                      # Common utilities
```

#### 1.2 Implement Core Interfaces

**Certificate Authority Interface**:
```python
class ICertificateAuthorityClient(ABC):
    @abstractmethod
    async def get_certificates(self, filter_params: Optional[Dict[str, Any]] = None) -> List[CertificateInfo]
    
    @abstractmethod  
    async def get_expiring_certificates(self, days_threshold: int) -> List[CertificateInfo]
    
    @abstractmethod
    async def import_certificate(self, cert_data: bytes, metadata: Optional[Dict[str, Any]] = None) -> str
    
    @abstractmethod
    async def revoke_certificate(self, serial_number: str, reason: str) -> bool
```

**Certificate Store Interface**:
```python
class ICertificateStore(ABC):
    @abstractmethod
    async def store_certificate(self, cert_id: str, cert_data: bytes, metadata: Optional[Dict[str, Any]] = None)
    
    @abstractmethod
    async def retrieve_certificate(self, cert_id: str) -> Optional[bytes]
    
    @abstractmethod
    async def list_certificates(self, filter_params: Optional[Dict[str, Any]] = None) -> List[str]
    
    @abstractmethod
    async def delete_certificate(self, cert_id: str) -> bool
```

#### 1.3 Basic Plugin Implementation

**Plugin Registration**:
```python
@plugin(
    name="certificate-management",
    version="1.0.0", 
    description="Certificate management with monitoring and notifications",
    author="Marty Team",
    provides=["certificate-management", "pki", "security"],
    dependencies=["observability", "security"]
)
class CertificateManagementPlugin(IServicePlugin):
    # Core plugin implementation
```

### Phase 2: Implementation (6-8 weeks)

#### 2.1 OpenXPKI Certificate Authority Client

**Location**: `marty_chassis/plugins/certificate_management/ca_clients/openxpki.py`

**Migration Strategy**:
1. Extract OpenXPKI logic from `src/marty_common/services/base_openxpki_service.py`
2. Adapt to ICertificateAuthorityClient interface
3. Maintain backward compatibility for Marty services
4. Add enhanced error handling and retry logic

**Key Features**:
- Session management and authentication
- Certificate import/export operations  
- Expiry checking with configurable thresholds
- Master list management
- ICAO-specific extensions support

**Implementation Outline**:
```python
class OpenXPKICertificateAuthorityClient(ICertificateAuthorityClient):
    def __init__(self, config: OpenXPKIConfig):
        self.base_url = config.base_url
        self.credentials = config.credentials
        self.session = requests.Session()
        
    async def get_expiring_certificates(self, days_threshold: int) -> List[CertificateInfo]:
        # Migrate existing expiry check logic
        # Add structured error handling
        # Return standardized CertificateInfo objects
```

#### 2.2 Vault Certificate Store Implementation

**Location**: `marty_chassis/plugins/certificate_management/stores/vault.py`

**Migration Strategy**:
1. Extract Vault integration from `services/trust-svc/vault_client.py`
2. Adapt to ICertificateStore interface
3. Add certificate metadata support
4. Implement backup and recovery features

**Key Features**:
- Secure certificate storage with encryption
- Metadata tracking and searching
- Certificate rotation support
- Backup and recovery capabilities
- Audit logging for all operations

#### 2.3 ICAO Certificate Parser Implementation

**Location**: `marty_chassis/plugins/certificate_management/parsers/icao.py`

**Migration Strategy**:
1. Extract parsing logic from `services/trust-svc/certificate_parser.py`
2. Adapt to ICertificateParser interface
3. Maintain ICAO-specific extension support
4. Add enhanced validation features

**Key Features**:
- X.509 certificate parsing
- ICAO-specific extension parsing
- Certificate chain validation
- Trust path construction
- Multiple format support (PEM, DER)

#### 2.4 Certificate Expiry Monitoring Service

**Location**: `marty_chassis/plugins/certificate_management/services/expiry_monitor.py`

**Migration Strategy**:
1. Extract core logic from `src/trust_anchor/app/services/certificate_expiry_service.py`
2. Make it generic and configurable for any CA client
3. Add support for multiple notification providers
4. Implement notification history and deduplication

**Key Features**:
- Configurable monitoring intervals
- Multiple notification thresholds
- Notification history tracking
- Support for multiple CA clients
- Pluggable notification providers

### Phase 3: Marty Service Migration (4-6 weeks)

#### 3.1 Trust Anchor Service Migration

**Current Dependencies**:
- `CertificateExpiryService`
- `OpenXPKIService`

**Migration Steps**:
1. Update service to use Certificate Management Plugin
2. Configure OpenXPKI CA client
3. Migrate expiry notification logic
4. Update configuration and deployment
5. Add backward compatibility layer if needed

**Updated Service Structure**:
```python
class TrustAnchorService(TrustAnchorServicer):
    def __init__(self):
        # Initialize with Certificate Management Plugin
        self.cert_manager = self.get_plugin("certificate-management")
        
        # Register OpenXPKI CA client
        openxpki_client = OpenXPKICertificateAuthorityClient(openxpki_config)
        await self.cert_manager.register_ca_client("openxpki", openxpki_client)
```

#### 3.2 PKD Service Migration

**Current Dependencies**:
- `CscaManager` with OpenXPKI integration
- Certificate synchronization logic

**Migration Steps**:
1. Update PKD service to use plugin for certificate operations
2. Migrate certificate synchronization to use standardized interfaces
3. Update expiry checking to use plugin services
4. Maintain CSCA-specific business logic

#### 3.3 Trust Service Migration

**Current Dependencies**:
- `VaultClient` for certificate storage
- Certificate parsing and validation

**Migration Steps**:
1. Replace direct Vault integration with plugin store
2. Update certificate parsing to use plugin parsers
3. Migrate validation logic to use plugin services
4. Update API endpoints to use plugin interfaces

### Phase 4: Enhancement and Integration (3-4 weeks)

#### 4.1 MMF Integration Enhancements

**Security Integration**:
- Integrate with MMF's RBAC system for certificate operations
- Use MMF's audit logging for certificate management events
- Leverage MMF's security headers and authentication

**Observability Integration**:
- Emit metrics for certificate operations (creation, expiry, rotation)
- Add distributed tracing for certificate workflows
- Implement health checks for CA connectivity and storage

**Configuration Integration**:
- Use MMF's configuration management for plugin settings
- Support environment-specific overrides
- Integrate with secret management for credentials

#### 4.2 Additional Features

**Notification Providers**:
- Email notifications for certificate events
- Webhook integration for external systems  
- Slack/Teams integration for team notifications
- SNMP traps for network monitoring systems

**Certificate Automation**:
- Automatic certificate renewal workflows
- Certificate rotation scheduling
- Validation and deployment automation
- Integration with CI/CD pipelines

**Advanced Monitoring**:
- Certificate inventory dashboard
- Compliance reporting
- Trend analysis for certificate usage
- Automated security scanning

## Implementation Details

### Configuration Schema

```yaml
# Certificate Management Plugin Configuration
certificate_management:
  enabled: true
  
  # CA client configurations
  certificate_authorities:
    openxpki:
      type: "openxpki"
      base_url: "${OPENXPKI_BASE_URL}"
      username: "${OPENXPKI_USERNAME}"  
      password: "${OPENXPKI_PASSWORD}"
      realm: "${OPENXPKI_REALM:-marty}"
      connection_timeout: 30
      read_timeout: 60
      
    # Support for additional CA types
    vault_pki:
      type: "vault_pki"
      vault_url: "${VAULT_URL}"
      token: "${VAULT_TOKEN}"
      pki_mount: "pki"
  
  # Storage backend configurations  
  certificate_stores:
    primary:
      type: "vault"
      url: "${VAULT_URL}"
      token: "${VAULT_TOKEN}"
      mount_point: "secret"
      path_prefix: "certificates/"
      encryption_enabled: true
      
    backup:
      type: "file"
      base_path: "data/cert_backup"
      encryption_enabled: true
  
  # Parser configurations
  certificate_parsers:
    icao:
      type: "icao"
      validate_extensions: true
      strict_mode: false
      
    standard:
      type: "x509"
      basic_validation: true
  
  # Notification configurations
  notification_providers:
    logging:
      type: "logging"
      level: "WARNING"
      
    email:
      type: "email"
      smtp_host: "${SMTP_HOST}"
      smtp_port: 587
      from_address: "${CERT_NOTIFICATIONS_FROM}"
      to_addresses: ["${CERT_ADMIN_EMAIL}"]
  
  # Monitoring configurations
  expiry_monitoring:
    enabled: true
    check_interval_hours: 24
    notification_days: [30, 15, 7, 3, 1]
    history_enabled: true
    history_storage_type: "file"
    
  # Security settings
  security:
    encrypt_stored_certificates: true
    audit_all_operations: true
    require_secure_transport: true
```

### Migration Timeline

| Phase | Duration | Key Milestones |
|-------|----------|----------------|
| **Phase 1: Foundation** | 4-6 weeks | Core interfaces, plugin structure, basic config |
| **Phase 2: Implementation** | 6-8 weeks | OpenXPKI client, Vault store, ICAO parser, expiry monitoring |
| **Phase 3: Service Migration** | 4-6 weeks | Trust Anchor, PKD, Trust Service migration |
| **Phase 4: Enhancement** | 3-4 weeks | MMF integration, additional features, monitoring |
| **Total** | **17-24 weeks** | **Complete migration with enhancements** |

### Testing Strategy

#### Unit Testing
- Test all plugin interfaces with mock implementations
- Test OpenXPKI client with test server
- Test certificate parsing with sample certificates
- Test configuration loading and validation

#### Integration Testing  
- Test plugin registration and lifecycle
- Test CA client integration with real OpenXPKI
- Test certificate storage with Vault
- Test notification delivery

#### Migration Testing
- Test backward compatibility during migration
- Test service functionality after migration
- Performance testing for certificate operations
- Load testing for expiry monitoring

#### End-to-End Testing
- Test complete certificate lifecycle workflows
- Test failure scenarios and recovery
- Test monitoring and alerting
- Test security and access controls

### Risk Mitigation

#### Technical Risks

**Risk**: Breaking existing Marty functionality during migration
**Mitigation**: 
- Implement backward compatibility layers
- Gradual migration with feature flags
- Comprehensive testing at each phase
- Rollback procedures for each service

**Risk**: Performance degradation from additional abstraction
**Mitigation**:
- Performance benchmarking before and after migration
- Optimize plugin interfaces for efficiency
- Implement caching where appropriate
- Monitor resource usage during migration

**Risk**: Complex configuration management
**Mitigation**:
- Clear configuration documentation
- Configuration validation and error reporting
- Migration scripts for existing configurations
- Default configurations for common use cases

#### Operational Risks

**Risk**: Service downtime during migration
**Mitigation**:
- Blue-green deployment strategy
- Service-by-service migration approach
- Health checks and automated rollback
- Maintenance windows for critical changes

**Risk**: Loss of certificate monitoring during transition
**Mitigation**:
- Run old and new monitoring in parallel
- Gradual cutover with validation
- Alert validation before cutover
- Manual monitoring procedures as backup

### Success Criteria

#### Functional Success Criteria
- [ ] All existing certificate management functionality preserved
- [ ] New plugin successfully registered and operational in MMF
- [ ] All Marty services successfully migrated to use plugin
- [ ] Certificate expiry monitoring working with same accuracy
- [ ] OpenXPKI integration maintaining all current capabilities

#### Non-Functional Success Criteria
- [ ] No performance degradation (< 5% latency increase)
- [ ] No reduction in monitoring accuracy or reliability
- [ ] Configuration complexity not increased
- [ ] Documentation complete and accurate
- [ ] All tests passing with >95% coverage

#### Business Success Criteria
- [ ] Code duplication eliminated across Marty services
- [ ] Framework ready for use by other services
- [ ] Maintenance burden reduced for certificate management
- [ ] Enhanced observability and monitoring capabilities
- [ ] Foundation for future certificate automation features

## Conclusion

This migration plan provides a comprehensive approach to abstracting Marty's certificate management capabilities into the MMF while maintaining all existing functionality and enabling future enhancements. The phased approach minimizes risk while delivering value incrementally.

The resulting Certificate Management Plugin will serve as a foundation for enterprise-grade PKI operations across all MMF-based services, eliminating duplication and providing a standardized approach to certificate lifecycle management.