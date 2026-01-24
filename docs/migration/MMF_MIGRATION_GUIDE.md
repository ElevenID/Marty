# Marty to MMF Plugin Migration Guide

## Executive Summary

This comprehensive guide outlines the complete strategy and implementation roadmap for transforming Marty from an independent microservices platform into a **specialized plugin of the Marty Microservices Framework (MMF)**. This migration achieves clean separation of concerns where MMF handles all cross-cutting infrastructure, middleware, and framework capabilities, while Marty contains only domain-specific trust & PKI business logic.

### Migration Objectives

- **Infrastructure Separation**: Eliminate 80%+ infrastructure duplication by leveraging MMF's proven patterns
- **Plugin Architecture**: Transform Marty services into MMF plugin components with clear interfaces
- **Deployment Modernization**: Migrate from Helm to Kustomize for simpler, more maintainable deployments
- **CI/CD Consolidation**: Adopt MMF's reusable workflows to standardize automation
- **Zero Downtime**: Complete migration with blue-green deployment ensuring continuous availability

### Key Benefits

**For Marty:**
- Reduced complexity with 80% reduction in infrastructure code
- Faster development focused on trust & PKI domain logic
- Better reliability leveraging battle-tested MMF infrastructure
- Easier maintenance with no infrastructure overhead

**For MMF:**
- Production validation with real-world enterprise usage
- Enhanced features driven by complex migration requirements
- Established plugin ecosystem pattern for other domains
- Comprehensive reference implementation

**For the Ecosystem:**
- Reusable infrastructure patterns for all microservices
- Standardized deployment and operational practices
- Reduced duplication across projects
- Faster innovation with domain-focused development

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Current State Analysis](#current-state-analysis)
3. [Plugin System Design](#plugin-system-design)
4. [Migration Strategy](#migration-strategy)
5. [Technical Implementation Guidelines](#technical-implementation-guidelines)
6. [Detailed Implementation Roadmap](#detailed-implementation-roadmap)
7. [Framework Enhancements](#framework-enhancements)
8. [Testing & Validation](#testing-validation)
9. [Deployment Procedures](#deployment-procedures)
10. [Success Metrics](#success-metrics)

---

## Architecture Overview

### Core Principle: MMF as Infrastructure, Marty as Domain Plugin

```
┌─────────────────────────────────────────────────────────────┐
│                 Marty Microservices Framework               │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                Infrastructure Layer                 │    │
│  │ • Auth/Security • Config • Database • Messaging   │    │
│  │ • Deployment • Observability • Service Mesh       │    │
│  └─────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                  Plugin System                     │    │
│  │        ┌─────────────────────────────────┐         │    │
│  │        │        Marty Trust & PKI        │         │    │
│  │        │           Plugin               │         │    │
│  │        │                                │         │    │
│  │        │ • Trust Store Management       │         │    │
│  │        │ • PKD Integration              │         │    │
│  │        │ • Document Signing Services    │         │    │
│  │        │ • Certificate Lifecycle        │         │    │
│  │        │ • Passport/Visa Processing     │         │    │
│  │        └─────────────────────────────────┘         │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

**MMF Infrastructure Layer:**
- Authentication & authorization middleware
- Configuration management system
- Database connection pooling and management
- Event bus and messaging infrastructure
- Deployment automation (Kubernetes, Kustomize)
- Observability (metrics, logging, tracing)
- Security framework (JWT, rate limiting, headers)
- Service mesh integration patterns

**Marty Plugin Layer:**
- Trust store management and verification
- PKD (Public Key Directory) integration
- Document signing and verification services
- Certificate lifecycle management
- Passport and visa processing
- Trust anchor operations
- Consistency engine for data validation

---

## Current State Analysis

### Marty's Current Infrastructure (To Be Migrated to MMF)

#### Services Architecture (`/src/services/`)
- **20+ microservices** including Document Signer, PKD Service, Trust Anchor, Consistency Engine
- Each service has its own database, models, and gRPC/REST APIs
- Custom middleware stack for auth, logging, metrics, rate limiting

#### Infrastructure Components (To Become MMF Standard Patterns)
- **Deployment**: Helm charts with 9 template files per service, complex Kubernetes manifests
- **Databases**: Per-service PostgreSQL databases with custom connection management
- **Configuration**: Custom YAML-based config system with environment overrides
- **Monitoring**: Prometheus/Grafana setup with ServiceMonitor configurations
- **Security**: Custom authentication, authorization, and rate limiting implementations
- **Terraform Modules**: AWS, Azure, GCP infrastructure provisioning

#### Framework Capabilities Already in MMF
- ✅ Authentication & Authorization middleware
- ✅ Configuration system with Marty-specific sections (CryptographicConfig, TrustStoreConfig)
- ✅ Database management with per-service support
- ✅ Messaging middleware with validation, transformation, authentication
- ✅ Deployment automation (Kubernetes, Helm, Kustomize)
- ✅ Observability framework with metrics, logging, tracing
- ✅ Security framework with JWT auth, rate limiting, security headers
- ✅ Service mesh integration patterns

### Deployment Workflows

#### Marty's Current State
- Uses Helm charts with templated Kubernetes manifests
- Complex Helm chart structure with 9 template files
- Custom service mesh configuration (Istio/Linkerd)
- Observability integration via ServiceMonitor/PodMonitor
- Support for HPA, PVC, migration jobs, and service accounts

#### MMF's Current State
- Uses Kustomize with base/overlay pattern
- Simpler structure focused on core microservice components
- Built-in service mesh and observability annotations
- Environment-specific overlays (dev, prod, service-mesh)

---

## Plugin System Design

### MMF Plugin Interface

The plugin system provides a standardized way for domain-specific services to integrate with MMF infrastructure.

```python
# In MMF framework
from abc import ABC, abstractmethod
from typing import Dict, Any, List

class MMFPlugin(ABC):
    """Base class for all MMF plugins."""
    
    @property
    @abstractmethod
    def plugin_name(self) -> str:
        """Unique plugin identifier."""
        pass
    
    @property
    @abstractmethod
    def version(self) -> str:
        """Plugin version."""
        pass
    
    @abstractmethod
    async def initialize(self, context: PluginContext) -> None:
        """Initialize plugin with MMF context."""
        pass
    
    @abstractmethod
    def get_services(self) -> List[ServiceDefinition]:
        """Return list of services this plugin provides."""
        pass
    
    @abstractmethod
    def get_configuration_schema(self) -> Dict[str, Any]:
        """Return configuration schema for this plugin."""
        pass

class PluginContext:
    """Context provided by MMF to plugins."""
    
    def __init__(self, 
                 config: ServiceConfig,
                 database_manager: DatabaseManager,
                 event_bus: EventBus,
                 security_manager: SecurityManager,
                 observability: ObservabilityManager):
        self.config = config
        self.database = database_manager
        self.event_bus = event_bus
        self.security = security_manager
        self.observability = observability
```

### Marty as Trust & PKI Plugin

```python
# In Marty plugin
from mmf.plugins import MMFPlugin, PluginContext
from mmf.services import ServiceDefinition

class MartyTrustPKIPlugin(MMFPlugin):
    """Marty Trust & PKI domain plugin for MMF."""
    
    @property
    def plugin_name(self) -> str:
        return "marty-trust-pki"
    
    @property
    def version(self) -> str:
        return "2.0.0"
    
    async def initialize(self, context: PluginContext) -> None:
        """Initialize Marty plugin with MMF infrastructure."""
        self.context = context
        
        # Use MMF's infrastructure
        self.config = context.config
        self.database = context.database
        self.event_bus = context.event_bus
        self.security = context.security
        self.observability = context.observability
        
        # Initialize Marty-specific components
        await self._initialize_trust_store()
        await self._initialize_pkd_client()
        await self._initialize_crypto_services()
    
    def get_services(self) -> List[ServiceDefinition]:
        """Define Marty's domain services."""
        return [
            ServiceDefinition(
                name="document-signer",
                handler=DocumentSignerService,
                routes=["/api/v1/sign", "/api/v1/verify"],
                dependencies=["trust-anchor", "crypto-service"]
            ),
            ServiceDefinition(
                name="trust-anchor",
                handler=TrustAnchorService,
                routes=["/api/v1/trust", "/api/v1/verify-trust"],
                dependencies=["database"]
            ),
            ServiceDefinition(
                name="pkd-service",
                handler=PKDService,
                routes=["/api/v1/pkd", "/api/v1/certificates"],
                dependencies=["database", "trust-anchor"]
            ),
            # ... other Marty services
        ]
    
    def get_configuration_schema(self) -> Dict[str, Any]:
        """Return Marty's configuration requirements."""
        return {
            "cryptographic": {
                "signing": {...},
                "sd_jwt": {...},
                "vault": {...}
            },
            "trust_store": {
                "pkd": {...},
                "trust_anchor": {...}
            },
            "service_discovery": {...}
        }
```

---

## Migration Strategy

The migration follows a phased approach with clear milestones and validation gates:

### Phase 1: Infrastructure Foundation (4 weeks)

**Goal**: Establish MMF as the infrastructure foundation while maintaining Marty functionality.

#### Week 1-2: MMF Infrastructure Enhancement
- **Extend MMF Configuration**: Enhance existing Marty-specific config sections
- **Database per Service**: Ensure MMF supports Marty's database patterns
- **Security Integration**: Verify MMF security middleware meets Marty's requirements

#### Week 3-4: Plugin System Implementation
- **Create Plugin Interface**: Implement `MMFPlugin` base class and `PluginContext`
- **Plugin Discovery**: Add plugin loading and lifecycle management to MMF
- **Initial Marty Plugin**: Create basic Marty plugin structure

**Success Criteria:**
- [ ] MMF can load and initialize plugins
- [ ] Marty configuration seamlessly integrates with MMF
- [ ] All MMF infrastructure components work with Marty services

### Phase 2: Service Migration (6 weeks)

**Goal**: Migrate Marty services to use MMF infrastructure while maintaining all functionality.

#### Week 1-2: Core Services Migration
- **Trust Anchor Service**: Migrate to use MMF database, security, observability
- **Document Signer**: Refactor to use MMF configuration and middleware
- **PKD Service**: Convert to MMF service pattern

#### Week 3-4: Supporting Services Migration
- **Consistency Engine**: Migrate to MMF event bus and messaging
- **Certificate Lifecycle**: Use MMF's resilience and monitoring patterns
- **Passport/Visa Services**: Integrate with MMF service mesh

#### Week 5-6: Integration & Testing
- **End-to-End Testing**: Verify all services work through MMF
- **Performance Validation**: Ensure no regression in performance
- **Security Audit**: Validate security posture is maintained

**Success Criteria:**
- [ ] All Marty services run as MMF plugin services
- [ ] Functional parity with existing Marty deployment
- [ ] All tests pass with new architecture

### Phase 3: Infrastructure Consolidation (4 weeks)

**Goal**: Remove all infrastructure duplication from Marty, making it purely a domain plugin.

#### Week 1-2: Deployment Migration
- **Kustomize Transition**: Migrate from Helm to MMF's Kustomize patterns
- **CI/CD Integration**: Use MMF's reusable workflows
- **Infrastructure as Code**: Migrate Terraform to MMF modules

#### Week 3-4: Final Cleanup
- **Remove Duplicated Code**: Delete all infrastructure code from Marty
- **Documentation Update**: Update all documentation for new architecture
- **Migration Validation**: Final validation of clean separation

**Success Criteria:**
- [ ] Marty repository contains only domain logic
- [ ] All infrastructure managed by MMF
- [ ] Deployment process uses MMF patterns exclusively

### Phase 4: Production Deployment (2 weeks)

**Goal**: Deploy Marty as MMF plugin to production with zero downtime.

#### Week 1: Staging Deployment
- **Blue-Green Deployment**: Deploy plugin version alongside existing
- **Traffic Switching**: Gradually move traffic to plugin version
- **Monitoring & Validation**: Ensure system health and functionality

#### Week 2: Production Cutover
- **Final Traffic Switch**: Complete migration to plugin architecture
- **Legacy Cleanup**: Remove old Marty deployment infrastructure
- **Documentation & Training**: Finalize operational documentation

**Success Criteria:**
- [ ] Production runs Marty as MMF plugin
- [ ] Zero downtime migration achieved
- [ ] All monitoring and alerting functional

---

## Technical Implementation Guidelines

### Configuration Migration Patterns

#### Current Marty Configuration Pattern
```yaml
# config/development.yaml (Marty current)
database:
  host: localhost
  port: 5432
  username: marty_user
  password: marty_pass

cryptographic:
  signing:
    algorithm: ES256
    key_id: marty-signing-key
    key_directory: "/opt/marty/keys"
  vault:
    url: "https://vault.marty.internal"
    auth_method: "kubernetes"

trust_store:
  pkd:
    service_url: "https://pkd.icao.int"
    timeout_seconds: 30
  trust_anchor:
    certificate_store_path: "/data/trust-store"
    update_interval_hours: 24
```

#### Target MMF Plugin Configuration
```yaml
# config/marty-plugin.yaml (MMF plugin format)
service:
  name: "marty-platform"
  environment: "development"
  
plugins:
  - name: "marty-trust-pki"
    version: "2.0.0"
    enabled: true
    config:
      # Marty-specific configuration nested under plugin
      cryptographic:
        signing:
          algorithm: "ES256"
          key_id: "marty-signing-key"
          key_directory: "/opt/marty/keys"
          rotation_policy:
            enabled: true
            interval_days: 90
        sd_jwt:
          issuer: "https://marty.example.com"
          ttl_seconds: 3600
        vault:
          url: "https://vault.marty.internal"
          auth_method: "kubernetes"
          namespace: "marty"
      
      trust_store:
        pkd:
          service_url: "https://pkd.icao.int"
          timeout_seconds: 30
          cache_ttl_hours: 24
          retry_attempts: 3
        trust_anchor:
          certificate_store_path: "/data/trust-store"
          update_interval_hours: 24
          validation_timeout_seconds: 30
          enable_online_verification: false
      
      service_discovery:
        consul:
          host: "consul.service.consul"
          port: 8500
        kubernetes:
          namespace: "marty"
          service_account: "marty-sa"

# Standard MMF infrastructure configuration
database:
  default:
    host: ${DB_HOST:localhost}
    port: ${DB_PORT:5432}
    username: ${DB_USER:mmf_user}
    password: ${DB_PASSWORD:mmf_pass}
    database: "mmf_default"
  services:
    document_signer: "marty_document_signer"
    trust_anchor: "marty_trust_anchor"
    pkd_service: "marty_pkd"

security:
  authentication:
    jwt:
      secret_key: ${JWT_SECRET_KEY}
      algorithm: "HS256"
      expiration_hours: 24
  rate_limiting:
    default_requests_per_hour: 1000
    redis_url: ${REDIS_URL:redis://localhost:6379}

observability:
  metrics:
    enabled: true
    prometheus_port: 9090
  logging:
    level: "INFO"
    structured: true
  tracing:
    enabled: true
    jaeger_endpoint: ${JAEGER_ENDPOINT}
```

#### Configuration Migration Script
```python
#!/usr/bin/env python3
"""
Configuration migration script for Marty to MMF plugin.
"""

import yaml
from pathlib import Path
from typing import Dict, Any

class ConfigurationMigrator:
    def __init__(self, marty_config_path: Path, output_path: Path):
        self.marty_config_path = marty_config_path
        self.output_path = output_path
    
    def migrate(self) -> None:
        """Migrate Marty configuration to MMF plugin format."""
        # Load existing Marty configuration
        with open(self.marty_config_path, 'r') as f:
            marty_config = yaml.safe_load(f)
        
        # Transform to MMF plugin format
        mmf_config = self._transform_config(marty_config)
        
        # Write MMF configuration
        with open(self.output_path, 'w') as f:
            yaml.dump(mmf_config, f, default_flow_style=False, indent=2)
    
    def _transform_config(self, marty_config: Dict[str, Any]) -> Dict[str, Any]:
        """Transform Marty config to MMF plugin format."""
        return {
            "service": {
                "name": "marty-platform",
                "environment": marty_config.get("environment", "development")
            },
            "plugins": [{
                "name": "marty-trust-pki",
                "version": "2.0.0",
                "enabled": True,
                "config": {
                    "cryptographic": marty_config.get("cryptographic", {}),
                    "trust_store": marty_config.get("trust_store", {}),
                    "service_discovery": marty_config.get("service_discovery", {})
                }
            }],
            "database": self._transform_database_config(marty_config.get("database", {})),
            "security": self._extract_security_config(marty_config),
            "observability": self._extract_observability_config(marty_config)
        }
    
    def _transform_database_config(self, db_config: Dict[str, Any]) -> Dict[str, Any]:
        """Transform database configuration to MMF format."""
        return {
            "default": {
                "host": db_config.get("host", "localhost"),
                "port": db_config.get("port", 5432),
                "username": db_config.get("username", "mmf_user"),
                "password": db_config.get("password", "mmf_pass"),
                "database": "mmf_default"
            },
            "services": {
                "document_signer": "marty_document_signer",
                "trust_anchor": "marty_trust_anchor", 
                "pkd_service": "marty_pkd",
                "consistency_engine": "marty_consistency"
            }
        }

# Usage example
if __name__ == "__main__":
    migrator = ConfigurationMigrator(
        Path("config/development.yaml"),
        Path("config/mmf-development.yaml")
    )
    migrator.migrate()
```

### Service Refactoring Patterns

#### Before: Marty Service Pattern
```python
# src/services/document_signer.py (Original Marty)
import logging
from typing import Optional
import grpc

from marty_common.config import Config
from marty_common.database import DatabaseManager
from marty_common.crypto import CryptoManager
from marty_common.logging_config import get_logger

class DocumentSigner:
    def __init__(self, config_path: Optional[str] = None):
        # Marty-specific initialization
        self.config = Config(config_path)
        self.logger = get_logger("document-signer")
        self.database = DatabaseManager(self.config.database())
        self.crypto = CryptoManager(self.config.cryptographic)
        
        # Manual middleware setup
        self._setup_metrics()
        self._setup_auth()
    
    def _setup_metrics(self):
        """Manual metrics setup."""
        self.metrics = PrometheusMetrics(port=9090)
    
    def _setup_auth(self):
        """Manual authentication setup.""" 
        self.auth = JWTAuthenticator(
            secret=self.config.jwt_secret,
            algorithm="HS256"
        )
    
    async def sign_document(self, request):
        # Manual auth check
        if not self.auth.verify(request.token):
            raise AuthenticationError("Invalid token")
        
        # Manual metrics
        self.metrics.increment("documents_signed")
        
        # Business logic
        signature = await self.crypto.sign(request.document)
        
        # Manual database operation
        await self.database.store_signature(signature)
        
        return signature
```

#### After: MMF Plugin Service Pattern
```python
# marty_plugin/services/document_signer.py (MMF Plugin)
from mmf.plugins import PluginService, PluginContext
from mmf.decorators import requires_auth, track_metrics, trace_operation
from mmf.exceptions import AuthenticationError, SigningError

class DocumentSignerService(PluginService):
    def __init__(self, context: PluginContext):
        super().__init__(context)
        
        # Use MMF-provided infrastructure
        self.crypto_config = context.config.get_plugin_config("marty-trust-pki").cryptographic
        self.vault_client = context.security.get_vault_client()
        self.database = context.database.get_service_database("document_signer")
        
        # MMF handles metrics, logging, auth automatically
        self.logger = context.observability.get_logger("document-signer")
        
    @requires_auth(roles=["signer", "admin"])
    @track_metrics("documents_signed")
    @trace_operation("document-signing")
    async def sign_document(self, request: SigningRequest) -> SigningResponse:
        """Sign a document using the configured algorithm."""
        try:
            # Get signing key from MMF vault
            signing_key = await self.vault_client.get_signing_key(
                self.crypto_config.signing.key_id
            )
            
            # Perform signing (pure business logic)
            signature = await self._create_signature(request.document, signing_key)
            
            # Use MMF repository pattern
            repo = await self.database.get_repository(SignatureRepository)
            await repo.store(signature)
            
            # Publish event through MMF event bus
            await self.context.event_bus.publish(DocumentSignedEvent(
                document_id=request.document_id,
                signature_id=signature.id,
                algorithm=self.crypto_config.signing.algorithm
            ))
            
            return SigningResponse(signature=signature)
            
        except Exception as e:
            self.logger.error(f"Document signing failed: {e}")
            raise SigningError(f"Failed to sign document: {e}")
    
    async def _create_signature(self, document: bytes, signing_key) -> Signature:
        """Create signature using configured algorithm."""
        # Pure cryptographic business logic
        if self.crypto_config.signing.algorithm == "ES256":
            return await self._sign_with_ecdsa(document, signing_key)
        elif self.crypto_config.signing.algorithm == "RS256":
            return await self._sign_with_rsa(document, signing_key)
        else:
            raise ValueError(f"Unsupported algorithm: {self.crypto_config.signing.algorithm}")
```

### Database Repository Migration Pattern

#### Before: Marty Repository Pattern
```python
# src/marty_common/infrastructure/repositories.py (Original)
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List

class TrustEntityRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def find_by_id(self, entity_id: str) -> Optional[TrustEntity]:
        # Custom session management
        result = await self.session.execute(
            select(TrustEntity).where(TrustEntity.id == entity_id)
        )
        return result.scalar_one_or_none()
    
    async def is_trusted(self, entity_id: str) -> bool:
        entity = await self.find_by_id(entity_id)
        return entity.trusted if entity else False
```

#### After: MMF Repository Pattern
```python
# marty_plugin/repositories/trust_entity.py (MMF Plugin)
from mmf.database import BaseRepository, DatabaseSession
from mmf.decorators import transactional, cached
from typing import Optional, List
from datetime import datetime

class TrustEntityRepository(BaseRepository[TrustEntity]):
    """Repository for trust entity operations using MMF patterns."""
    
    @cached(ttl=300)  # Cache for 5 minutes
    async def find_by_id(self, entity_id: str) -> Optional[TrustEntity]:
        """Find trust entity by ID with caching."""
        return await self.session.get(TrustEntity, entity_id)
    
    @cached(ttl=300)
    async def is_trusted(self, entity_id: str) -> bool:
        """Check if entity is trusted with caching."""
        entity = await self.find_by_id(entity_id)
        return entity.trusted if entity else False
    
    @transactional
    async def update_trust_status(self, entity_id: str, trusted: bool) -> bool:
        """Update trust status with automatic transaction management."""
        entity = await self.find_by_id(entity_id)
        if not entity:
            return False
        
        entity.trusted = trusted
        entity.updated_at = datetime.utcnow()
        
        # MMF handles session commit/rollback
        await self.session.merge(entity)
        
        # Invalidate cache
        await self._invalidate_cache(f"find_by_id:{entity_id}")
        await self._invalidate_cache(f"is_trusted:{entity_id}")
        
        return True
    
    async def find_by_country(self, country_code: str) -> List[TrustEntity]:
        """Find all trust entities for a country."""
        result = await self.session.execute(
            select(TrustEntity)
            .where(TrustEntity.country_code == country_code)
            .where(TrustEntity.trusted == True)
        )
        return result.scalars().all()
```

### Event Processing Migration Pattern

#### Before: Custom Event Processing
```python
# src/services/consistency_engine.py (Original)
import asyncio
from typing import Dict, Any

class ConsistencyEngine:
    def __init__(self):
        self.event_queue = asyncio.Queue()
        self.processors = {}
    
    async def process_events(self):
        """Custom event processing loop."""
        while True:
            try:
                event = await self.event_queue.get()
                processor = self.processors.get(event.type)
                if processor:
                    await processor(event)
            except Exception as e:
                logger.error(f"Event processing error: {e}")
    
    async def handle_document_signed(self, event):
        """Handle document signed event."""
        # Custom consistency checking logic
        pass
```

#### After: MMF Event Bus Pattern
```python
# marty_plugin/services/consistency_engine.py (MMF Plugin)
from mmf.events import EventHandler, event_handler
from mmf.plugins import PluginService

class ConsistencyEngineService(PluginService):
    def __init__(self, context: PluginContext):
        super().__init__(context)
        self.workflow_engine = context.workflow_engine
    
    async def initialize(self):
        """Initialize event subscriptions using MMF event bus."""
        # Subscribe to events using MMF decorators
        await self.context.event_bus.subscribe_handler(self)
    
    @event_handler("document.signed")
    async def handle_document_signed(self, event: DocumentSignedEvent):
        """Handle document signed event with MMF workflow engine."""
        # Use MMF workflow engine for consistency checking
        workflow = await self.workflow_engine.create_workflow(
            "document-consistency-check",
            input_data={
                "document_id": event.document_id,
                "signature_id": event.signature_id,
                "algorithm": event.algorithm
            }
        )
        
        await workflow.execute()
    
    @event_handler("trust.updated")
    async def handle_trust_updated(self, event: TrustUpdatedEvent):
        """Handle trust status updates."""
        # Trigger re-validation of affected documents
        affected_docs = await self._find_documents_by_entity(event.entity_id)
        
        for doc_id in affected_docs:
            validation_workflow = await self.workflow_engine.create_workflow(
                "trust-revalidation",
                input_data={"document_id": doc_id, "entity_id": event.entity_id}
            )
            await validation_workflow.execute_async()  # Background processing
```

---

## Detailed Implementation Roadmap

### Phase 1: Infrastructure Foundation (4 weeks)

#### Week 1: MMF Infrastructure Assessment & Enhancement

##### Day 1-2: Configuration System Integration
**Tasks:**
- [ ] Audit existing MMF configuration sections for Marty compatibility
- [ ] Extend `CryptographicConfigSection` with missing Marty fields
- [ ] Enhance `TrustStoreConfigSection` for PKD integration patterns
- [ ] Add `ServiceDiscoveryConfigSection` Kubernetes service mesh support

**Implementation Steps:**
```python
# Extend MMF configuration in src/framework/config.py
@dataclass
class CryptographicConfigSection(BaseConfigSection):
    signing: SigningConfig = field(default_factory=SigningConfig)
    sd_jwt: SDJWTConfig = field(default_factory=SDJWTConfig)
    vault: VaultConfig = field(default_factory=VaultConfig)
    key_rotation: KeyRotationConfig = field(default_factory=KeyRotationConfig)  # New
    hsm_integration: HSMConfig = field(default_factory=HSMConfig)  # New
```

**Acceptance Criteria:**
- [ ] All Marty configuration patterns supported in MMF
- [ ] Backward compatibility maintained
- [ ] Configuration validation passes all tests

##### Day 3-5: Database Infrastructure Validation
**Tasks:**
- [ ] Verify MMF database per-service pattern works with Marty schemas
- [ ] Test connection pooling and transaction management
- [ ] Validate Alembic migration integration
- [ ] Ensure proper database isolation between services

**Acceptance Criteria:**
- [ ] All Marty services can connect to service-specific databases
- [ ] Database migrations work with MMF patterns
- [ ] Connection pooling performs within acceptable limits

#### Week 2: Plugin System Foundation

##### Day 1-3: Plugin Interface Design & Implementation
**Tasks:**
- [ ] Design `MMFPlugin` base class and `PluginContext`
- [ ] Implement plugin discovery and lifecycle management
- [ ] Create plugin configuration schema validation
- [ ] Build plugin dependency resolution

**Implementation Steps:**
```python
# Create src/framework/plugins/__init__.py
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

class PluginMetadata:
    def __init__(self, name: str, version: str, description: str, 
                 dependencies: List[str] = None):
        self.name = name
        self.version = version
        self.description = description
        self.dependencies = dependencies or []

class PluginContext:
    def __init__(self, config: ServiceConfig, services: Dict[str, Any]):
        self.config = config
        self.database = services.get('database')
        self.event_bus = services.get('event_bus')
        self.security = services.get('security')
        self.observability = services.get('observability')

class MMFPlugin(ABC):
    @property
    @abstractmethod
    def metadata(self) -> PluginMetadata:
        pass
    
    @abstractmethod
    async def initialize(self, context: PluginContext) -> None:
        pass
    
    @abstractmethod
    def get_service_definitions(self) -> List[ServiceDefinition]:
        pass

class PluginManager:
    def __init__(self):
        self.plugins: Dict[str, MMFPlugin] = {}
        self.plugin_contexts: Dict[str, PluginContext] = {}
    
    async def load_plugin(self, plugin_class: type[MMFPlugin], 
                         context: PluginContext) -> None:
        plugin = plugin_class()
        await plugin.initialize(context)
        self.plugins[plugin.metadata.name] = plugin
        self.plugin_contexts[plugin.metadata.name] = context
```

**Acceptance Criteria:**
- [ ] Plugin interface supports all required operations
- [ ] Plugin discovery mechanism works
- [ ] Plugin lifecycle (load, initialize, unload) functions correctly

##### Day 4-5: Service Definition Framework
**Tasks:**
- [ ] Design `ServiceDefinition` class for plugin services
- [ ] Implement service routing and middleware integration
- [ ] Create service dependency injection framework
- [ ] Build service health checking system

**Acceptance Criteria:**
- [ ] Services can be defined and registered through plugins
- [ ] Service dependencies are resolved correctly
- [ ] Health checks and metrics integration work

#### Week 3: Security & Middleware Integration

##### Day 1-3: Security Framework Integration
**Tasks:**
- [ ] Verify MMF security middleware meets Marty requirements
- [ ] Test JWT authentication with Marty's token format
- [ ] Validate rate limiting configuration for high-throughput services
- [ ] Ensure RBAC policies work with Marty's user roles

**Acceptance Criteria:**
- [ ] All Marty authentication patterns work with MMF security
- [ ] Rate limiting handles Marty's traffic patterns
- [ ] Security headers and policies are properly applied

##### Day 4-5: Observability Integration
**Tasks:**
- [ ] Validate metrics collection for Marty services
- [ ] Test distributed tracing across service boundaries
- [ ] Ensure log aggregation captures Marty-specific events
- [ ] Verify alerting rules work with Marty operational patterns

**Acceptance Criteria:**
- [ ] All Marty metrics are collected and exposed
- [ ] Distributed tracing works across all services
- [ ] Logs are properly structured and searchable

#### Week 4: Initial Plugin Implementation

##### Day 1-3: Marty Plugin Skeleton
**Tasks:**
- [ ] Create basic Marty plugin structure
- [ ] Implement `MartyTrustPKIPlugin` class
- [ ] Define all Marty service definitions
- [ ] Create plugin configuration schema

**Implementation Steps:**
```python
# Create marty_plugin/plugin.py
from mmf.plugins import MMFPlugin, PluginMetadata, PluginContext
from .services import (
    DocumentSignerService, TrustAnchorService, 
    PKDService, ConsistencyEngineService
)

class MartyTrustPKIPlugin(MMFPlugin):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="marty-trust-pki",
            version="2.0.0",
            description="Trust and PKI services for identity document verification",
            dependencies=["database", "security", "observability"]
        )
    
    async def initialize(self, context: PluginContext) -> None:
        self.context = context
        
        # Initialize Marty-specific components
        await self._init_trust_store()
        await self._init_pkd_client()
        await self._init_crypto_services()
    
    def get_service_definitions(self) -> List[ServiceDefinition]:
        return [
            ServiceDefinition(
                name="document-signer",
                handler_class=DocumentSignerService,
                routes=[
                    Route("/api/v1/sign", methods=["POST"]),
                    Route("/api/v1/verify", methods=["POST"])
                ],
                middleware=["authentication", "rate-limiting"],
                dependencies=["trust-anchor", "crypto-service"]
            ),
            ServiceDefinition(
                name="trust-anchor",
                handler_class=TrustAnchorService,
                routes=[
                    Route("/api/v1/trust/verify", methods=["POST"]),
                    Route("/api/v1/trust/entities", methods=["GET"])
                ],
                dependencies=["database"]
            ),
            # ... other services
        ]
```

**Acceptance Criteria:**
- [ ] Plugin loads successfully in MMF
- [ ] All service definitions are valid
- [ ] Plugin initialization completes without errors

##### Day 4-5: Integration Testing
**Tasks:**
- [ ] Test plugin loading and initialization
- [ ] Verify service registration works
- [ ] Test basic service functionality
- [ ] Validate configuration integration

**Acceptance Criteria:**
- [ ] Plugin integration tests pass
- [ ] Services respond to health checks
- [ ] Basic API endpoints are functional

### Phase 2: Service Migration (6 weeks)

#### Week 1-2: Core Services Migration

##### Trust Anchor Service Migration
**Tasks:**
- [ ] Refactor `TrustAnchor` class to use MMF patterns
- [ ] Migrate database models to use MMF repository pattern
- [ ] Update gRPC/REST endpoints to use MMF routing
- [ ] Integrate with MMF security and observability

**Acceptance Criteria:**
- [ ] Trust Anchor service uses MMF infrastructure exclusively
- [ ] All existing functionality preserved
- [ ] Performance within 5% of original implementation

##### Document Signer Service Migration
**Tasks:**
- [ ] Migrate cryptographic operations to use MMF configuration
- [ ] Update certificate management to use MMF security patterns
- [ ] Integrate with MMF event bus for audit logging
- [ ] Refactor API endpoints to use MMF routing

**Acceptance Criteria:**
- [ ] Document signing uses MMF security infrastructure
- [ ] Audit events are properly published to event bus
- [ ] Cryptographic operations maintain security standards

#### Week 3-4: Supporting Services Migration

##### PKD Service Migration
**Tasks:**
- [ ] Migrate PKD client to use MMF HTTP client patterns
- [ ] Update certificate storage to use MMF database patterns
- [ ] Integrate with MMF caching middleware
- [ ] Add MMF resilience patterns (circuit breaker, retry)

**Acceptance Criteria:**
- [ ] PKD service uses MMF HTTP client and caching
- [ ] Circuit breaker prevents cascade failures
- [ ] Certificate caching improves performance

##### Consistency Engine Migration
**Tasks:**
- [ ] Migrate event processing to use MMF event bus
- [ ] Update state management to use MMF database patterns
- [ ] Integrate with MMF workflow engine
- [ ] Add MMF monitoring and alerting

**Acceptance Criteria:**
- [ ] Event processing uses MMF event bus exclusively
- [ ] Workflow orchestration integrates with MMF patterns
- [ ] Consistency checks maintain data integrity

#### Week 5-6: Integration & Testing

##### End-to-End Testing
**Tasks:**
- [ ] Create comprehensive test suite for migrated services
- [ ] Test service interactions through MMF infrastructure
- [ ] Validate performance under load
- [ ] Test failure scenarios and recovery

**Acceptance Criteria:**
- [ ] All E2E tests pass
- [ ] Performance is within acceptable limits
- [ ] Failure recovery works correctly

### Phase 3: Infrastructure Consolidation (4 weeks)

#### Week 1-2: Deployment Migration

##### Kustomize Migration
**Tasks:**
- [ ] Convert Helm charts to Kustomize using MMF converter
- [ ] Create environment-specific overlays
- [ ] Validate manifest generation
- [ ] Test deployment to staging environment

**Implementation Steps:**
```bash
# Use MMF Helm to Kustomize converter
marty migrate helm-to-kustomize \
  --helm-chart-path ./helm/charts/document-signer \
  --output-path ./k8s/document-signer \
  --service-name document-signer \
  --values-file ./helm/values-dev.yaml \
  --values-file ./helm/values-prod.yaml \
  --validate
```

**Acceptance Criteria:**
- [ ] All Helm charts successfully converted to Kustomize
- [ ] Generated manifests are valid and deploy successfully
- [ ] Environment-specific customizations work correctly

##### CI/CD Migration
**Tasks:**
- [ ] Update GitHub Actions to use MMF reusable workflows
- [ ] Migrate build processes to use MMF patterns
- [ ] Update deployment scripts to use Kustomize
- [ ] Integrate with MMF quality gates

**Implementation Steps:**
```yaml
# Update .github/workflows/deploy.yml
name: Deploy Marty Plugin
on:
  push:
    branches: [main]

jobs:
  deploy:
    uses: marty-microservices-framework/.github/workflows/deploy-plugin.yml@main
    with:
      plugin-name: marty-trust-pki
      environment: ${{ github.ref == 'refs/heads/main' && 'production' || 'staging' }}
      kustomize-path: k8s/overlays
    secrets:
      DEPLOY_TOKEN: ${{ secrets.DEPLOY_TOKEN }}
```

**Acceptance Criteria:**
- [ ] CI/CD uses MMF reusable workflows exclusively
- [ ] Deployment process is fully automated
- [ ] Quality gates prevent bad deployments

#### Week 3-4: Final Cleanup

##### Infrastructure Code Removal
**Tasks:**
- [ ] Remove duplicate configuration management code
- [ ] Delete custom middleware implementations
- [ ] Remove Helm charts and deployment scripts
- [ ] Clean up database connection management

**Acceptance Criteria:**
- [ ] No duplicate infrastructure code remains in Marty
- [ ] All imports use MMF modules
- [ ] Repository structure matches plugin-only design

##### Documentation Update
**Tasks:**
- [ ] Update README with plugin architecture
- [ ] Create migration documentation
- [ ] Update API documentation
- [ ] Create operational runbooks

**Acceptance Criteria:**
- [ ] Documentation accurately reflects plugin architecture
- [ ] Migration guide helps other projects
- [ ] Operational procedures are updated

### Phase 4: Production Deployment (2 weeks)

#### Week 1: Staging Deployment

##### Blue-Green Deployment Setup
**Tasks:**
- [ ] Deploy plugin version to staging environment
- [ ] Configure traffic splitting between old and new versions
- [ ] Set up monitoring and alerting for both versions
- [ ] Create rollback procedures

**Acceptance Criteria:**
- [ ] Blue-green deployment configured and tested
- [ ] Traffic can be split between versions
- [ ] Rollback procedures validated

##### Performance & Load Testing
**Tasks:**
- [ ] Run load tests against plugin version
- [ ] Compare performance with original implementation
- [ ] Test scaling behavior under load
- [ ] Validate resource usage and efficiency

**Acceptance Criteria:**
- [ ] Performance meets or exceeds original implementation
- [ ] System handles expected load without degradation
- [ ] Resource usage is optimal

#### Week 2: Production Cutover

##### Traffic Migration
**Tasks:**
- [ ] Gradually shift traffic from old to new implementation
- [ ] Monitor system health and performance metrics
- [ ] Validate all functionality works correctly
- [ ] Complete traffic cutover

**Implementation Steps:**
```bash
# Gradual traffic shift
kubectl argo rollouts set weight marty-trust-pki 10  # 10% traffic
# Monitor for 30 minutes
kubectl argo rollouts set weight marty-trust-pki 50  # 50% traffic  
# Monitor for 30 minutes
kubectl argo rollouts promote marty-trust-pki         # 100% traffic
```

**Acceptance Criteria:**
- [ ] Traffic migration completed without incidents
- [ ] All services functioning normally
- [ ] No data loss or corruption

##### Legacy System Cleanup
**Tasks:**
- [ ] Remove old Marty deployment infrastructure
- [ ] Clean up unused resources and configurations
- [ ] Archive old deployment artifacts
- [ ] Update DNS and service discovery

**Acceptance Criteria:**
- [ ] All legacy infrastructure removed
- [ ] No unused resources consuming costs
- [ ] Service discovery points to new implementation

---

## Framework Enhancements

### Enhanced Kubernetes Manifests

#### Base Template Expansions

**Required Additions:**

```
microservice_project_template/k8s/base/
├── kustomization.yaml          # Enhanced with new resources
├── deployment.yaml             # Enhanced with security, probes, resources
├── service.yaml               # Current
├── configmap.yaml             # Current
├── serviceaccount.yaml        # NEW - RBAC support
├── servicemonitor.yaml        # NEW - Prometheus integration
├── podmonitor.yaml           # NEW - Pod-level metrics
├── hpa.yaml                  # NEW - Horizontal Pod Autoscaling
├── pdb.yaml                  # NEW - Pod Disruption Budget
├── networkpolicy.yaml        # NEW - Network security
└── configmap-generator.yaml  # NEW - For dynamic config generation
```

**Implementation Priority:** HIGH

#### Marty-Specific Overlays

```
microservice_project_template/k8s/overlays/
├── dev/                      # Current
├── prod/                     # Current
├── service-mesh/             # Current
├── marty-services/           # NEW - Marty migration overlay
│   ├── kustomization.yaml
│   ├── patch-complex-deployment.yaml
│   ├── migration-job.yaml
│   ├── pvc.yaml
│   └── database-config.yaml
├── database-services/        # NEW - For services with DB
│   └── postgres-overlay/
└── background-services/      # NEW - For async/batch services
```

**Implementation Priority:** HIGH

### Infrastructure as Code Templates

#### Reference Terraform Modules

```
marty-microservices-framework/devops/infrastructure/
├── terraform/
│   ├── modules/
│   │   ├── eks-cluster/          # EKS with best practices
│   │   ├── networking/           # VPC, subnets, security groups
│   │   ├── observability/        # Prometheus, Grafana, logging
│   │   ├── service-mesh/         # Istio/Linkerd setup
│   │   ├── databases/            # RDS, ElastiCache modules
│   │   └── security/             # IAM, KMS, security configs
│   ├── aws/
│   │   ├── complete-example/     # Full deployment example
│   │   └── minimal-example/      # Lightweight deployment
│   ├── azure/
│   │   └── aks-example/
│   ├── gcp/
│   │   └── gke-example/
│   └── multi-cloud/
│       └── hybrid-example/
└── docs/
    ├── INFRASTRUCTURE_GUIDE.md
    ├── TERRAFORM_BEST_PRACTICES.md
    └── CLOUD_DEPLOYMENT_PATTERNS.md
```

**Implementation Priority:** MEDIUM

### Reusable CI/CD Workflows

#### GitHub Actions Templates

```
marty-microservices-framework/.github/workflows/
├── reusable-ci.yml           # Quality gates, testing, linting
├── reusable-build.yml        # Container building with security
├── reusable-deploy.yml       # Kustomize deployment automation
├── reusable-security.yml     # Security scanning (Cosign, etc.)
├── reusable-integration.yml  # Integration test execution
└── reusable-release.yml      # Release automation
```

**Key Features Needed:**

1. **Matrix Build Support:**
   ```yaml
   inputs:
     services:
       description: 'JSON array of services to build'
       required: true
       type: string
     dockerfile-pattern:
       description: 'Pattern for dockerfile paths'
       default: 'docker/{service}.Dockerfile'
   ```

2. **Security Integration:**
   ```yaml
   - name: Sign container images
     uses: sigstore/cosign-installer@v2
   - name: Scan for vulnerabilities
     uses: aquasecurity/trivy-action@master
   ```

3. **Multi-environment Deployment:**
   ```yaml
   strategy:
     matrix:
       environment: [dev, staging, prod]
   ```

**Implementation Priority:** HIGH

### Migration Tooling

#### Helm to Kustomize Converter

```python
# scripts/helm_to_kustomize_converter.py
"""
Tool to convert Helm charts to Kustomize manifests
"""

class HelmToKustomizeConverter:
    def __init__(self, helm_chart_path: str, output_path: str):
        self.helm_chart_path = helm_chart_path
        self.output_path = output_path
    
    def convert_values_to_patches(self, values_file: str) -> List[Dict]:
        """Convert Helm values to Kustomize patches"""
        pass
    
    def generate_base_manifests(self) -> None:
        """Generate base Kustomize manifests from Helm templates"""
        pass
    
    def create_overlay_structure(self, environments: List[str]) -> None:
        """Create overlay directory structure"""
        pass
    
    def validate_conversion(self) -> bool:
        """Validate that converted manifests match Helm output"""
        pass
```

**Implementation Priority:** HIGH

---

## Testing & Validation

### Testing Strategy

#### Unit Testing with MMF Infrastructure

```python
# tests/unit/test_document_signer.py
import pytest
from unittest.mock import AsyncMock, MagicMock

from mmf.testing import PluginTestCase, mock_plugin_context
from marty_plugin.services import DocumentSignerService

class TestDocumentSignerService(PluginTestCase):
    async def setup_method(self):
        """Setup test with mocked MMF context."""
        self.context = await mock_plugin_context(
            config_overrides={
                "cryptographic": {
                    "signing": {
                        "algorithm": "ES256",
                        "key_id": "test-key"
                    }
                }
            }
        )
        self.service = DocumentSignerService(self.context)
    
    async def test_sign_document_success(self):
        """Test successful document signing."""
        # Setup mocks
        self.context.vault_client.get_signing_key = AsyncMock(return_value="test-key")
        self.context.database.get_repository = AsyncMock()
        
        # Create test request
        request = SigningRequest(
            document_id="test-doc",
            document=b"test document content"
        )
        
        # Execute
        response = await self.service.sign_document(request)
        
        # Verify
        assert response.signature is not None
        self.context.vault_client.get_signing_key.assert_called_once_with("test-key")
        self.context.event_bus.publish.assert_called_once()
```

#### Integration Testing

```python
# tests/integration/test_plugin_integration.py
import pytest
from mmf.testing import IntegrationTestCase
from marty_plugin import MartyTrustPKIPlugin

class TestMartyPluginIntegration(IntegrationTestCase):
    async def setup_method(self):
        """Setup integration test environment."""
        await self.setup_test_database()
        await self.setup_test_redis()
        await self.setup_test_vault()
        
        # Load plugin
        self.plugin = MartyTrustPKIPlugin()
        await self.plugin.initialize(self.test_context)
    
    async def test_complete_document_signing_flow(self):
        """Test complete document signing and verification flow."""
        # Sign document
        signing_response = await self.call_service_endpoint(
            "document-signer",
            "/api/v1/sign",
            method="POST",
            json={
                "document_id": "integration-test-doc",
                "document_type": "passport",
                "document_data": "test passport data"
            },
            headers={"Authorization": f"Bearer {self.test_jwt_token}"}
        )
        
        assert signing_response.status_code == 200
        signature_data = signing_response.json()
        
        # Verify trust
        trust_response = await self.call_service_endpoint(
            "trust-anchor",
            "/api/v1/trust/verify",
            method="POST",
            json={
                "entity_id": signature_data["signer_id"]
            }
        )
        
        assert trust_response.status_code == 200
        assert trust_response.json()["trusted"] is True
```

#### Performance Testing

```python
# tests/performance/test_load_handling.py
import asyncio
import time
import pytest

from mmf.testing import PerformanceTestCase

class TestMartyPluginPerformance(PerformanceTestCase):
    
    @pytest.mark.performance
    async def test_document_signing_throughput(self):
        """Test document signing throughput under load."""
        concurrent_requests = 100
        requests_per_second_target = 50
        
        async def sign_document():
            start_time = time.time()
            response = await self.call_service_endpoint(
                "document-signer",
                "/api/v1/sign",
                method="POST",
                json=self.generate_test_document()
            )
            end_time = time.time()
            
            return {
                "success": response.status_code == 200,
                "response_time": end_time - start_time,
                "timestamp": start_time
            }
        
        # Execute concurrent requests
        tasks = [sign_document() for _ in range(concurrent_requests)]
        results = await asyncio.gather(*tasks)
        
        # Analyze results
        successful_requests = sum(1 for r in results if r["success"])
        avg_response_time = sum(r["response_time"] for r in results) / len(results)
        
        total_duration = max(r["timestamp"] for r in results) - min(r["timestamp"] for r in results)
        actual_rps = successful_requests / total_duration
        
        # Assertions
        assert successful_requests >= concurrent_requests * 0.99  # 99% success rate
        assert avg_response_time < 0.5  # 500ms average response time
        assert actual_rps >= requests_per_second_target
```

### Validation & Quality Assurance

#### Migration Validation Checklist
```yaml
validation_steps:
  configuration:
    - [ ] All Marty configuration sections supported in MMF
    - [ ] Environment-specific overrides work correctly
    - [ ] No configuration validation errors
    - [ ] Backward compatibility maintained
  
  services:
    - [ ] All services migrated to plugin pattern
    - [ ] Service dependencies resolved correctly
    - [ ] Health checks pass for all services
    - [ ] API endpoints respond correctly
  
  database:
    - [ ] Service-specific databases work
    - [ ] Data migration completed successfully
    - [ ] Repository patterns use MMF base classes
    - [ ] Database connections pooled correctly
  
  security:
    - [ ] Authentication works with MMF middleware
    - [ ] Authorization policies applied correctly
    - [ ] Rate limiting functions properly
    - [ ] Security headers present
  
  observability:
    - [ ] Metrics collected and exposed
    - [ ] Logs structured and searchable
    - [ ] Distributed tracing works
    - [ ] Alerting rules functional
  
  performance:
    - [ ] Response times within acceptable limits
    - [ ] Throughput meets requirements
    - [ ] Resource usage optimized
    - [ ] No memory leaks detected
  
  infrastructure:
    - [ ] Kustomize deployments work
    - [ ] CI/CD pipelines functional
    - [ ] No duplicate infrastructure code
    - [ ] Rollback procedures tested
```

---

## Deployment Procedures

### Blue-Green Deployment Configuration

```yaml
# Configure blue-green deployment
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata:
  name: marty-trust-pki
spec:
  replicas: 3
  strategy:
    blueGreen:
      autoPromotionEnabled: false
      prePromotionAnalysis:
        templates:
        - templateName: success-rate
        args:
        - name: service-name
          value: marty-trust-pki
      scaleDownDelaySeconds: 30
  selector:
    matchLabels:
      app: marty-trust-pki
  template:
    metadata:
      labels:
        app: marty-trust-pki
    spec:
      containers:
      - name: marty-plugin
        image: marty/trust-pki-plugin:v2.0.0
```

### Rollback Procedures

```bash
# Emergency rollback procedure
kubectl argo rollouts abort marty-trust-pki
kubectl argo rollouts undo marty-trust-pki
kubectl scale deployment marty-legacy --replicas=3
```

### Infrastructure Cleanup

```bash
#!/bin/bash
# scripts/cleanup-infrastructure.sh

echo "🧹 Cleaning up duplicate infrastructure code..."

# Remove Marty-specific infrastructure directories
INFRASTRUCTURE_DIRS=(
    "terraform/"
    "helm/"
    "monitoring/"
    "docker/"
    "k8s/base/"
    "scripts/deployment/"
    ".github/workflows/"
)

for dir in "${INFRASTRUCTURE_DIRS[@]}"; do
    if [ -d "$dir" ]; then
        echo "Removing $dir..."
        rm -rf "$dir"
    fi
done

echo "✅ Infrastructure cleanup complete"
```

---

## Success Metrics

### Technical Metrics
- **Code Reduction**: 80%+ reduction in infrastructure code
- **Performance**: <5% degradation in response times
- **Reliability**: 99.9%+ uptime during migration
- **Security**: No security vulnerabilities introduced

### Operational Metrics  
- **Deployment Time**: 50%+ reduction in deployment time
- **Configuration Changes**: 70%+ reduction in config complexity
- **Incident Response**: 40%+ faster incident resolution
- **Onboarding Time**: 60%+ faster new developer onboarding

### Business Metrics
- **Feature Velocity**: 30%+ increase in feature delivery speed
- **Maintenance Cost**: 50%+ reduction in operational overhead
- **Team Productivity**: 25%+ increase in developer productivity
- **Innovation Time**: 40%+ more time spent on business logic vs infrastructure

### Migration Success Indicators
- [ ] Zero downtime migration to production
- [ ] All existing functionality preserved
- [ ] Performance parity or improvement
- [ ] Security posture maintained or improved
- [ ] 80%+ reduction in Marty infrastructure code
- [ ] All services running as MMF plugins
- [ ] Single deployment pipeline for all services
- [ ] Unified monitoring and observability

---

## Risk Mitigation

### Technical Risks
- **Performance Impact**: Mitigated by gradual migration with performance testing at each phase
- **Breaking Changes**: Mitigated by maintaining API compatibility and thorough integration testing
- **Data Migration**: Mitigated by schema compatibility testing and rollback procedures

### Operational Risks
- **Deployment Complexity**: Mitigated by blue-green deployment strategy and staged rollout
- **Knowledge Transfer**: Mitigated by comprehensive documentation and hands-on training sessions
- **Rollback Capability**: Mitigated by maintaining parallel deployment capability during transition

---

## Repository Structure After Migration

### Marty Repository (Domain Plugin Only)
```
marty/
├── pyproject.toml                 # Plugin dependencies only
├── README.md                      # Plugin documentation
├── src/
│   └── marty_plugin/
│       ├── __init__.py           # Plugin entry point
│       ├── plugin.py             # MartyTrustPKIPlugin implementation
│       ├── services/             # Domain services only
│       │   ├── trust_anchor.py
│       │   ├── document_signer.py
│       │   ├── pkd_service.py
│       │   └── crypto_services.py
│       ├── models/               # Domain models
│       ├── schemas/              # Business logic schemas
│       └── utils/                # Domain-specific utilities
├── config/
│   └── plugin-config.yaml        # Plugin-specific configuration
├── tests/                        # Plugin tests
└── docs/                         # Plugin documentation
```

### MMF Repository (Infrastructure Only)
```
marty-microservices-framework/
├── src/framework/
│   ├── plugins/                  # Plugin system
│   ├── config/                   # Configuration management
│   ├── database/                 # Database infrastructure
│   ├── security/                 # Security middleware
│   ├── messaging/                # Event bus & messaging
│   ├── deployment/               # Deployment automation
│   ├── observability/            # Monitoring & logging
│   └── service_mesh/             # Service mesh integration
├── k8s/                          # Kustomize base manifests
├── terraform/                    # Infrastructure modules
├── .github/workflows/            # Reusable CI/CD workflows
└── docs/                         # Framework documentation
```

---

## Conclusion

This comprehensive migration guide transforms Marty from an independent platform into a specialized domain plugin of MMF, achieving:

1. **Clean Separation of Concerns**: MMF handles infrastructure, Marty provides domain expertise
2. **Reduced Duplication**: Single source of truth for microservices infrastructure
3. **Improved Maintainability**: Focus on core competencies
4. **Enhanced Reliability**: Leverage proven infrastructure patterns
5. **Faster Innovation**: Accelerated development through reduced infrastructure overhead

The phased approach with clear milestones, validation gates, and rollback procedures ensures minimal risk while delivering maximum value through systematic migration of services, infrastructure, and operational processes. By following this guide, the migration will be completed with zero downtime, all functionality preserved, and significant improvements in development velocity and operational efficiency.
