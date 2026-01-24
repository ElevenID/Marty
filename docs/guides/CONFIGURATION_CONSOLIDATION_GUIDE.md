# Marty Configuration Consolidation Guide

This document explains how to migrate Marty services to use the unified Marty Microservices Framework (MMF) configuration system while maintaining backward compatibility.

## Overview

The configuration consolidation eliminates duplication between Marty's YAML-based configuration and MMF's Python configuration system by extending MMF to natively support Marty's YAML configuration patterns.

## Changes Made

### 1. Extended MMF Configuration Sections

The MMF configuration system has been enhanced with Marty-specific configuration sections:

#### `CryptographicConfigSection`
- **Signing Configuration**: Algorithms, key IDs, key directories, rotation policies
- **SD-JWT Configuration**: Issuer settings, TTL values, certificate mappings
- **Vault Integration**: HashiCorp Vault connection and authentication settings

#### `TrustStoreConfigSection` 
- **PKD Configuration**: Public Key Directory service settings
- **Trust Anchor Configuration**: Certificate store paths and validation settings

#### `ServiceDiscoveryConfigSection`
- **Host/Port Mapping**: Service discovery patterns used by Marty
- **Service Mesh Integration**: Kubernetes service mesh support

### 2. Enhanced Database Configuration
- **Per-Service Databases**: Support for Marty's pattern of separate databases per service
- **Fallback to Default**: Automatic fallback to default database when service-specific config is missing

### 3. Backward Compatibility Adapter
- **Automatic Detection**: Detects whether MMF or Marty config files exist
- **Seamless Migration**: Services can use existing YAML files without modification
- **Gradual Migration**: Teams can migrate services one at a time

## Migration Strategies

### Strategy 1: Use Existing YAML Files (Recommended)

The MMF configuration system now reads Marty's existing YAML files directly:

```python
from framework.config import ServiceConfig, Environment

# Automatically detects and uses existing config/development.yaml
config = ServiceConfig(
    service_name="document_signer",
    environment=Environment.DEVELOPMENT,
    config_path=Path("config")
)

# Access Marty-specific configuration
crypto_config = config.cryptographic
signing_algo = crypto_config.signing.algorithm
vault_url = crypto_config.vault.url

trust_config = config.trust_store
cert_store = trust_config.trust_anchor.certificate_store_path
pkd_url = trust_config.pkd.service_url
```

### Strategy 2: Gradual Migration to MMF Structure

For new services or major refactoring, you can use pure MMF configuration:

```yaml
# config/base.yaml (MMF style)
database:
  default:
    host: localhost
    port: 5432
    pool_size: 10

security:
  grpc_tls:
    enabled: true
    mtls: true

cryptographic:
  signing:
    algorithm: rsa2048
    key_directory: data/keys
  vault:
    url: "${VAULT_ADDR:-https://vault.internal:8200}"
    auth_method: approle

trust_store:
  trust_anchor:
    certificate_store_path: /app/data/trust
  pkd:
    service_url: http://pkd-service:8089

service_discovery:
  hosts:
    csca_service: localhost
    document_signer: localhost
  ports:
    csca_service: 8081
    document_signer: 8082
```

## Configuration Mapping

### Marty YAML Structure → MMF Structure

| Marty Config | MMF Section | MMF Property |
|--------------|-------------|--------------|
| `services.document_signer.signing_algorithm` | `cryptographic.signing` | `algorithm` |
| `services.document_signer.sd_jwt` | `cryptographic.sd_jwt` | `*` |
| `vault.*` | `cryptographic.vault` | `*` |
| `security.key_directory` | `cryptographic.signing` | `key_directory` |
| `hosts.*` | `service_discovery` | `hosts` |
| `ports.*` | `service_discovery` | `ports` |
| `database.document_signer.*` | `database` | `*` (per-service) |

### Environment Variable Expansion

Both systems support environment variable expansion:

```yaml
# Marty/MMF compatible format
database:
  document_signer:
    url: "${DOCUMENT_SIGNER_DATABASE_URL:-postgresql://localhost/marty_doc_signer}"
    password: "${DB_PASSWORD:-dev_password}"

vault:
  url: "${VAULT_ADDR:-https://vault.internal:8200}"
  token: "${VAULT_TOKEN:-}"
```

## Service Migration Examples

### Document Signer Service

```python
# Before (Marty config)
from marty_common.config_manager import ConfigurationManager

config_manager = ConfigurationManager("config")
config = config_manager.load_service_config("document_signer", "development")

# After (Unified config) 
from framework.config import ServiceConfig, Environment

config = ServiceConfig(
    service_name="document_signer",
    environment=Environment.DEVELOPMENT
)

# Same YAML files, but now type-safe access
db_config = config.database  # DatabaseConfigSection with validation
crypto_config = config.cryptographic  # New cryptographic section
security_config = config.security  # Enhanced security section
```

### Trust Anchor Service

```python
# Unified configuration with Marty-specific features
config = ServiceConfig(
    service_name="trust_anchor",
    environment=Environment.DEVELOPMENT
)

# Access trust store configuration
trust_config = config.trust_store
certificate_path = trust_config.trust_anchor.certificate_store_path
update_interval = trust_config.trust_anchor.update_interval_hours

# Access PKD configuration
pkd_config = trust_config.pkd
pkd_url = pkd_config.service_url
pkd_enabled = pkd_config.enabled
```

## Validation and Type Safety

The unified configuration provides type safety and validation:

```python
# Type-safe configuration access
config = ServiceConfig("document_signer", Environment.DEVELOPMENT)

# These are validated dataclass instances
db: DatabaseConfigSection = config.database
security: SecurityConfigSection = config.security
crypto: CryptographicConfigSection = config.cryptographic

# Validation happens automatically
try:
    invalid_config = ServiceConfig("bad_service", Environment.DEVELOPMENT)
except ValidationError as e:
    print(f"Configuration validation failed: {e}")
```

## Migration Timeline

### Phase 1: Immediate (Current)
- ✅ Extended MMF configuration sections added
- ✅ Backward compatibility with existing Marty YAML files
- ✅ Type-safe access to Marty-specific configuration

### Phase 2: Service Migration (Ongoing)
- Update individual services to use `ServiceConfig` instead of `ConfigurationManager`
- Keep existing YAML files unchanged
- Add type annotations and validation

### Phase 3: Cleanup (Future)
- Remove redundant Marty configuration classes
- Consolidate configuration files
- Update documentation

## Best Practices

### 1. Use Environment-Specific Configs
```yaml
# config/development.yaml
security:
  grpc_tls:
    enabled: false  # OK for development
  auth:
    required: false

# config/production.yaml  
security:
  grpc_tls:
    enabled: true   # Required for production
    mtls: true
  auth:
    required: true
```

### 2. Leverage Per-Service Database Config
```yaml
database:
  # Service-specific databases for data isolation
  document_signer:
    url: "${DOCUMENT_SIGNER_DB_URL:-postgresql://localhost/marty_doc_signer}"
    name: marty_document_signer
    
  csca_service:
    url: "${CSCA_DB_URL:-postgresql://localhost/marty_csca}"
    name: marty_csca
    
  # Fallback for services without specific config
  default:
    url: "${DEFAULT_DB_URL:-postgresql://localhost/marty_default}"
    name: marty_default
```

### 3. Use YAML Anchors for DRY Configuration
```yaml
# Common patterns
common_database: &common_db
  pool_size: 10
  max_overflow: 20
  pool_timeout: 30

# Apply to multiple services
database:
  document_signer:
    <<: *common_db
    url: "${DOCUMENT_SIGNER_DB_URL:-postgresql://localhost/marty_doc_signer}"
    
  csca_service:
    <<: *common_db
    url: "${CSCA_DB_URL:-postgresql://localhost/marty_csca}"
```

## Troubleshooting

### Configuration Not Found Error
```python
# Error: No database configuration found for service 'my_service'
# Solution: Add default database config or service-specific config

# Option 1: Add default
database:
  default:
    host: localhost
    port: 5432
    database: marty_default

# Option 2: Add service-specific
database:
  my_service:
    host: localhost
    port: 5432
    database: marty_my_service
```

### Validation Errors
```python
# Error: Invalid port number: 0
# Solution: Ensure all port numbers are valid (1-65535)

ports:
  my_service: 8080  # Valid
  invalid_service: 0  # Invalid - will cause ValidationError
```

### Missing Environment Variables
```yaml
# Use default values to prevent missing variable errors
vault:
  url: "${VAULT_ADDR:-https://vault.default:8200}"
  token: "${VAULT_TOKEN:-}"  # Empty string as default
```

## Conclusion

The unified configuration system provides:

1. **Backward Compatibility**: Existing Marty YAML files work without changes
2. **Type Safety**: Configuration sections are validated dataclasses  
3. **Marty-Specific Features**: Support for cryptographic, trust store, and service discovery patterns
4. **Gradual Migration**: Services can be migrated incrementally
5. **DRY Principle**: Eliminates configuration duplication between systems

Services can immediately start using the unified configuration system with minimal code changes while keeping their existing YAML configuration files.