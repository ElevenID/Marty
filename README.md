# Marty Trust PKI Plugin

[![CI](https://github.com/burdettadam/Marty/workflows/Marty%20CI/badge.svg)](https://github.com/burdettadam/Marty/actions)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: Educational Use Only](https://img.shields.io/badge/License-Educational%20Use%20Only-red.svg)](#license)
[![MMF Plugin](https://img.shields.io/badge/MMF-Plugin-green.svg)](https://github.com/burdettadam/marty-microservices-framework)

## Overview

� **Marty Trust PKI Plugin for MMF** - Enterprise-grade PKI and trust services for secure digital identity document management

🎓 **Educational Portfolio Project - ICAO Standards Learning Implementation**

> ⚠️ **EDUCATIONAL USE ONLY** - This project is developed for learning ICAO standards and portfolio demonstration purposes. Not intended for production use.

Marty is a comprehensive learning project that implements ICAO PKI standards for electronic passport (eMRTD) issuance and verification, mobile driving licenses (mDL), and digital travel credentials (DTC). Implemented as a plugin for the [Marty Microservices Framework (MMF)](./marty-microservices-framework/), this project demonstrates modern plugin architecture while exploring international digital identity standards.

## 🏗️ Architecture

Marty operates as an **MMF Plugin**, leveraging the framework's infrastructure for:

- **Microservices Infrastructure**: Service discovery, configuration, monitoring via MMF
- **Plugin System**: Clean separation between framework and domain logic
- **Trust & PKI Services**: Domain-specific trust anchor, PKD, document signing, and CSCA services
- **Configuration Management**: Environment-aware configuration through MMF
- **Observability**: Built-in metrics, tracing, and health monitoring

## 🚀 Quick Start

### Prerequisites

1. **MMF Framework**: Install and configure the [Marty Microservices Framework](./marty-microservices-framework/)
2. **Python 3.10+**: Required for plugin execution
3. **Poetry or uv**: For dependency management

### Installation

```bash
# Install Marty as an MMF plugin
pip install marty-trust-pki-plugin

# Or for development
git clone https://github.com/burdettadam/Marty.git
cd Marty
uv install -e .
```

### Configuration

Create plugin configuration in your MMF deployment:

```yaml
# config/plugins/marty.yaml
name: marty
enabled: true
config:
  trust_anchor_url: "https://trust.example.com"
  pkd_url: "https://pkd.example.com"
  document_signer_url: "https://signer.example.com"
  csca_service_url: "https://csca.example.com"
```

### Usage

```python
# Example plugin usage through MMF
from marty_msf import PluginManager

# Load Marty plugin
plugin_manager = PluginManager()
marty_plugin = await plugin_manager.load_plugin("marty")

# Access trust services
trust_service = marty_plugin.get_service("trust_anchor")
pkd_service = marty_plugin.get_service("pkd")
```

## 🧩 Plugin Services

The Marty plugin provides four core services through the MMF framework:

- **🔒 Trust Anchor Service**: Root certificate management and trust chain validation
- **📁 PKD Service**: Public Key Directory for certificate discovery and validation
- **✍️ Document Signer Service**: Digital signature creation and verification for travel documents  
- **🏛️ CSCA Service**: Country Signing Certificate Authority management and validation

## 🎯 Educational Goals

This project was developed to:

- **Learn ICAO Standards**: Practical implementation of ICAO Doc 9303 and ISO/IEC 18013-5
- **Plugin Architecture**: Showcase modern plugin-based microservices design
- **Portfolio Demonstration**: Demonstrate separation of concerns between infrastructure and domain logic
- **Standards Exploration**: Deep dive into international digital identity document specifications
- **Security Learning**: Hands-on experience with PKI, certificate management, and cryptographic protocols

## 🔑 Key Features (Educational Implementation)

- **ICAO Compliant**: Educational implementation of ICAO Doc 9303 and ISO/IEC 18013-5 standards
- **Plugin Architecture**: Learning-focused plugin-based design patterns with MMF framework integration
- **Cryptographic Implementation**: Educational exploration of PKI and certificate management
- **Multi-Document Support**: Academic study of eMRTDs, mDLs, mDocs, and Digital Travel Credentials
- **Modern Development Practices**: Portfolio demonstration using Python 3.10+, gRPC, Docker, PostgreSQL
- **Standards Research**: Comprehensive documentation and implementation notes

### 🚀 Recent Platform Enhancements

- **Ultra-DRY Architecture**: 60-90% code reduction through service factory patterns and shared components
- **Enterprise Monitoring**: Prometheus metrics, health checks, and Grafana dashboards for all services
- **Production Security**: HashiCorp Vault integration, mTLS authentication, RBAC, and audit logging
- **Strong Typing**: MyPy strict mode with comprehensive type annotations and protocol interfaces
- **Resilience Framework**: Circuit breakers, retry mechanisms, and failure injection for reliability testing
- **EUDI Bridge**: European Digital Identity Wallet compatibility and cross-border verification
- **OpenID4VC Integration**: Full OIDC4VCI/OID4VP support with Sphereon compatibility testing

## 🏗️ Plugin Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                 MMF Framework Host                          │
│                                                             │
│  ┌─────────────────┐    ┌─────────────────────────────────┐ │
│  │  Configuration  │    │         Plugin Manager         │ │
│  │   Management    │    │                                 │ │
│  └─────────────────┘    └─────────────┬───────────────────┘ │
│                                       │                     │
│  ┌─────────────────┐    ┌─────────────▼───────────────────┐ │
│  │  Observability  │    │      Marty Trust PKI Plugin    │ │
│  │   Framework     │    │                                 │ │
│  └─────────────────┘    │  ┌─────────────────────────────┐ │ │
│                         │  │    Plugin Services          │ │ │
│  ┌─────────────────┐    │  │                             │ │ │
│  │     Service     │    │  │ • Trust Anchor Service      │ │ │
│  │    Discovery    │    │  │ • PKD Service               │ │ │
│  └─────────────────┘    │  │ • Document Signer Service   │ │ │
│                         │  │ • CSCA Service              │ │ │
│                         │  └─────────────────────────────┘ │ │
│                         │                                 │ │
│                         │  ┌─────────────────────────────┐ │ │
│                         │  │   Domain Logic Integration │ │ │
│                         │  │                             │ │ │
│                         │  │ • ICAO Doc 9303 (eMRTD)    │ │ │
│                         │  │ • ISO/IEC 18013-5 (mDL)    │ │ │
│                         │  │ • PKI & Certificate Mgmt   │ │ │
│                         │  │ • Trust Chain Validation   │ │ │
│                         │  └─────────────────────────────┘ │ │
│                         └─────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘

                                    │
                        ┌───────────▼───────────┐
                        │     Client Access     │
                        │                       │
                        │ • gRPC Services       │
                        │ • REST APIs           │
                        │ • Plugin SDK          │
                        └───────────────────────┘
```

                          ┌─────────▼─────────┐
                          │   PostgreSQL      │
                          │ (Certificate DB)  │
                          │   Port 5432       │
                          └───────────────────┘
                                    │
                          ┌─────────▼─────────┐
                          │     OpenXPKI      │
                          │  (External PKI)   │
                          └───────────────────┘

```

## 📁 Project Structure

The project follows a modular plugin architecture:

- `/src/mmf_plugin/` - MMF plugin implementation and service wrappers
- `/src/trust_anchor/` - Trust anchor management and validation logic  
- `/src/pkd_service/` - PKD and certificate discovery services
- `/src/services/` - Core service implementations (document signer, CSCA)
- `/src/marty_common/` - Shared library and utilities
- `/src/proto/` - Generated Python code from protobuf definitions
- `/proto/` - Protocol buffer definition files (.proto)
- `/config/` - Configuration schemas and examples
- `/marty-microservices-framework/` - MMF framework for plugin hosting
- `/tests/` - Test suites for plugin functionality
- `/docs/` - Documentation and API specifications

## 🚀 Quick Start & Demo

Get Marty MMF plugin running in under 5 minutes:

### Installation

```bash
# Clone the repository
git clone https://github.com/burdettadam/Marty.git
cd Marty

# Set up the development environment (installs dependencies)
uv install -e .
```

### Demo: Plugin Integration

Test the Marty plugin integration with MMF:

```bash
# Run the plugin demo
python demo_mmf_integration.py

# Test plugin services individually  
python -c "from src.mmf_plugin.plugin import MartyPlugin; p=MartyPlugin(); print(f'Plugin: {p.get_metadata()}')"

# Run the test suite
uv run pytest tests/
```

**🎯 Verify installation**: The demo will show plugin discovery, service initialization, and health checks.

### What the Demo Shows

#### Plugin Discovery
```
🔍 Plugin Discovery Demo
==================================================
✅ Discovered plugin: marty
   Version: 1.0.0
   Description: Marty Trust PKI services for ICAO compliance
   Services: 4 services
```

#### Service Lifecycle  
```
🔄 Plugin Lifecycle Demo
==================================================
🚀 Initializing plugin...
✅ Started trust_anchor service
✅ Started pkd service  
✅ Started document_signer service
✅ Started csca service
```

#### Health Monitoring
```
❤️  Checking health status...
   Overall status: healthy
   - trust_anchor: healthy
   - pkd: healthy
   - document_signer: healthy
   - csca: healthy
```

### Available Plugin Services

The Marty plugin exposes four core trust and PKI services:

- **Trust Anchor Service**: Root certificate management and trust validation
- **PKD Service**: Public Key Directory synchronization and certificate discovery
- **Document Signer Service**: Digital signature creation for travel documents
- **CSCA Service**: Country Signing Certificate Authority management

> **💡 Tip**: Use the MMF framework to deploy Marty as a plugin in production environments.

## 🚀 Getting Started with Development

### Development Setup

This project provides plugin development tools:

```bash
# Setup development environment
uv install -e .

# Code quality and formatting
uv run ruff check .
uv run mypy src/

# Run tests
uv run pytest tests/                # Complete test suite
uv run pytest tests/unit/          # Unit tests only
uv run pytest tests/integration/   # Integration tests

# Test plugin integration
python demo_mmf_integration.py     # Plugin demo

# Show plugin services
python -c "from src.mmf_plugin import MartyPlugin; p=MartyPlugin(); print(p.get_services())"
```

### Plugin Configuration

Marty as an MMF plugin uses **framework-provided configuration** with plugin-specific settings:

#### Plugin Configuration Structure

```yaml
# Example: config/plugins/marty.yaml (in MMF deployment)
name: marty
enabled: true
config:
  trust_anchor:
    url: "${TRUST_ANCHOR_URL:-https://trust.example.com}"
    validation_enabled: true
  pkd:
    url: "${PKD_URL:-https://pkd.example.com}"
    sync_interval_hours: 24
  document_signer:
    url: "${SIGNER_URL:-https://signer.example.com}"
    algorithms: ["RSA-SHA256", "ECDSA-SHA256"]
  csca:
    url: "${CSCA_URL:-https://csca.example.com}"
    certificate_validation: true
```

#### Integrating with MMF

```python
# Example: Using Marty plugin in MMF application
from marty_msf import PluginManager

async def setup_marty_services():
    plugin_manager = PluginManager()
    
    # Load Marty plugin
    marty_plugin = await plugin_manager.load_plugin("marty")
    
    # Access trust services
    trust_service = marty_plugin.get_service("trust_anchor")
    pkd_service = marty_plugin.get_service("pkd")
    
    # Initialize and start services
    await trust_service.initialize(config)
    await trust_service.start()
    
    return marty_plugin
```

### Creating Plugin Extensions

To extend Marty with additional services:

```python
# Example: Adding a new service to the plugin
from src.mmf_plugin.services import PluginService

class CustomService(PluginService):
    def __init__(self):
        super().__init__("custom-service", "1.0.0")
        
    async def initialize(self, config):
        # Service initialization logic
        pass
        
    async def start(self):
        # Service startup logic  
        pass
```

#### Environment Variables

Set the environment using the `MARTY_ENV` variable:

```bash
export MARTY_ENV=development  # Uses config/development.yaml + service configs
export MARTY_ENV=production   # Uses config/production.yaml + service configs
```

## Testing

### Comprehensive Test Strategy

The project includes multiple testing layers:

```bash
# Core test categories
make test-unit                    # Unit tests for individual components
make test-integration            # Service integration testing
make test-e2e                    # End-to-end workflow validation
make test-cert-validator         # Certificate validation testing

# Protocol-specific testing
make test-openid4vp              # OpenID4VC presentation flows
make test-presentations          # mDL/mDoc presentation testing

# Comprehensive testing
make test                        # All standard tests
make test-comprehensive          # Includes advanced protocol tests
```

### Integration Testing

The project includes comprehensive integration tests adapted from industry-standard libraries:

**ICAO Standards Testing** (from ZeroPass/pymrtd):

- Basic infrastructure: ElementaryFile, DataGroup functionality
- MRZ and DG1: Machine Readable Zone processing
- Security: SOD, DG14/DG15, Active Authentication

**OCR and Image Processing** (from PassportEye):

- MRZ extraction from passport images
- OCR functionality validation
- PDF image extraction

**Certificate Validation** (from wbond/certvalidator):

- X.509 certificate validation
- Path building and validation
- Certificate revocation (CRL/OCSP)
- NIST and OpenSSL test suites

### Performance and Security Testing

```bash
# Plugin testing
python demo_mmf_integration.py     # Plugin integration demo
uv run pytest tests/               # Complete test suite

# Security analysis
uv run bandit -r src/              # Security scan
uv run safety check               # Dependency vulnerability check
```

## Running Plugin in Development

The plugin can be tested locally through the demo integration:

```bash
# Test plugin discovery and services
python demo_mmf_integration.py

# Test individual plugin components
python -c "from src.mmf_plugin.services import TrustAnchorService; print('Service ready')"
```

Plugin services are configured through MMF framework configuration in the host deployment.

---

**🌟 Educational Portfolio Project** - This implementation demonstrates modern approaches to international digital identity standards, plugin architecture, and secure certificate management in a comprehensive, well-documented MMF plugin.

For questions about educational use or portfolio review, please contact the repository owner.

## 📚 Documentation

Comprehensive documentation is available in the [docs/](docs/) directory:

### Core Documentation
- **[ISO 18013-5 Architecture](docs/iso18013/ARCHITECTURE.md)** - ISO 18013-5 architecture and performance analysis
- **[ISO 18013-5 Build Guide](docs/iso18013/BUILD_GUIDE.md)** - Build instructions and Python-to-Rust migration guide
- **[ISO 18013 Interoperability](docs/iso18013/INTEROPERABILITY_GUIDE.md)** - Standards compliance and API mappings
- **[ISO 18013 Implementation](docs/iso18013/IMPLEMENTATION_SUMMARY.md)** - Complete mDL/mDoc implementation overview

### Migration & Integration
- **[MMF Migration Guide](docs/migration/MMF_MIGRATION_GUIDE.md)** - Comprehensive guide for migrating to MMF plugin architecture
- **[Certificate Management Migration](docs/guides/CERTIFICATE_MANAGEMENT_MIGRATION_PLAN.md)** - Certificate framework migration plan

### Operational Guides
- **[Docker Guide](docs/guides/DOCKER.md)** - Docker development setup and deployment
- **[Native Development](docs/guides/NATIVE_DEVELOPMENT.md)** - Hybrid TDD development environment
- **[Push Notification Guide](docs/guides/PUSH_NOTIFICATION_GUIDE.md)** - Firebase/SSE notification infrastructure
- **[Configuration Consolidation](docs/guides/CONFIGURATION_CONSOLIDATION_GUIDE.md)** - Unified configuration system migration
- **[Deployment Profile Migration](docs/guides/DEPLOYMENT_PROFILE_MIGRATION_GUIDE.md)** - Deployment profile migration steps
- **[Deployment Profile Reference](docs/guides/DEPLOYMENT_PROFILE_QUICK_REFERENCE.md)** - Quick reference for deployment profiles

### Architecture & Features
- **[Certificate Management Framework](docs/architecture/CERTIFICATE_MANAGEMENT_FRAMEWORK_DESIGN.md)** - Certificate management architecture design
- **[Presentation Policy](docs/features/PRESENTATION_POLICY_IMPLEMENTATION.md)** - Presentation policy implementation
- **[Redis Multi-Tenant](docs/features/REDIS_MULTI_TENANT_IMPLEMENTATION.md)** - Multi-tenant Redis implementation
- **[Update Manager Integration](docs/features/UPDATE_MANAGER_INTEGRATION.md)** - Update manager and deployment profiles
- **[Quality Gates](docs/features/QUALITY_GATES_IMPLEMENTATION.md)** - Quality gates and reliability implementation

### Additional Resources
For more documentation, see the [docs/](docs/) directory which contains 50+ additional guides covering API documentation, testing strategies, security practices, and more.

---

## License

This project is provided under an Educational Use Only license for learning and portfolio demonstration. Commercial or production use is not permitted. See the LICENSE file for full terms.
