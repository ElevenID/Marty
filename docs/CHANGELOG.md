# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **FREE Subscription Tier Key Vault Access**: FREE tier can now use service key vault with weekly rotation
  - Weekly (7-day) mandatory key rotation for FREE tier
  - More aggressive rotation than DEVS tier to prevent long-term free usage
  - Service-managed key vault access (HashiCorp Vault)
  - Per-organization key isolation
- **DEVS Subscription Tier**: New developer tier with service key vault access for development and testing
  - Service-managed key vault access (HashiCorp Vault)
  - Biweekly (14-day) mandatory key rotation
  - 10,000 API calls/month, 5 API keys, 3 webhook endpoints
  - Per-organization key isolation
- **Tier-Based Signing Service**: New `SigningService` for cryptographic signing with subscription enforcement
  - Automatic tier-based access control
  - Service key vault for FREE and DEVS tiers (weekly and biweekly rotation respectively)
  - Remote signing requirement for production tiers (STARTER, PROFESSIONAL, ENTERPRISE)
  - Key rotation enforcement and tracking per tier
  - Comprehensive error handling (`KeyRotationRequired`, `RemoteSigningRequired`, `UnauthorizedKeyVaultAccess`)
- **Key Rotation Enforcement**: Automatic rotation for FREE and DEVS tiers
  - FREE tier: 7-day rotation (weekly)
  - DEVS tier: 14-day rotation (biweekly)
  - Signing operations blocked after rotation deadline
  - Automated rotation workflow with versioned keys
  - Per-key rotation tracking
- **Subscription Plan Limits**: Extended `PlanLimits` with key vault access fields
  - `can_use_service_key_vault`: Control service vault access per tier
  - `requires_remote_signing`: Enforce remote signing for production tiers
- **Comprehensive Test Suite**: 26 test cases for tier-based signing (`tests/subscription/test_tier_based_signing.py`)
  - FREE tier weekly rotation tests
  - DEVS tier biweekly rotation tests
  - Remote signing enforcement tests
  - Access control validation tests
- **Documentation**: Complete developer and user documentation
  - DEVS Tier Key Vault Guide (`docs/DEVS_TIER_KEY_VAULT_GUIDE.md`)
  - Tier-Based Signing Implementation Summary (`docs/TIER_BASED_SIGNING_IMPLEMENTATION.md`)
  - Test suite documentation (`tests/subscription/README.md`)
  - Working code examples (`examples/tier_based_signing_example.py`)

### Changed

- **Subscription Tiers**: Updated tier structure
  - FREE tier now uses service key vault with 7-day rotation
  - DEVS tier uses service key vault with 14-day rotation
  - Production tiers (STARTER, PROFESSIONAL, ENTERPRISE) require remote signing
- **Plan Configuration**: All tiers now include key vault access control flags

### Security

- **Key Isolation**: Organization-scoped key IDs prevent cross-organization access
- **Zero-Knowledge Architecture**: Production tiers never expose private keys to service
- **Rotation Enforcement**: Automatic key rotation prevents long-term key compromise risk
  - Weekly rotation for FREE tier prevents abuse
  - Biweekly rotation for DEVS tier balances security and usability
- **Access Control**: Tier-based enforcement ensures proper key management practices

## [1.0.0] - 2025-10-03

### Added

- **Semver'd Protobuf Namespaces**: Migrated all protobuf packages to versioned namespaces following `marty.<service>.v1` convention
- **Breaking Change Detection**: Added Buf-based CI workflow for automated breaking change detection in protobuf APIs
- **Versioning Policy**: Established formal protobuf versioning and breaking change policy in architecture documentation
- **Architecture Documentation**: Created comprehensive architecture.md with protobuf versioning guidelines

### Changed

- **BREAKING**: All protobuf packages renamed from simple names to versioned namespaces:
  - `passport` → `marty.passport.v1`
  - `mdoc` → `marty.mdoc.v1`  
  - `trust` → `marty.trust.v1`
  - `common_services` → `marty.common.v1`
  - `biometric_service` → `marty.biometric.v1`
  - `cmc_engine` → `marty.cmc.v1`
  - `csca_service` → `marty.csca.v1`
  - `data_lifecycle` → `marty.lifecycle.v1`
  - `document_signer` → `marty.signer.v1`
  - `dtc_engine` → `marty.dtc.v1`
  - `inspection_system` → `marty.inspection.v1`
  - `mdl_engine` → `marty.mdl.v1`
  - `pkd_service` → `marty.pkd.v1`
  - `rfid_service` → `marty.rfid.v1`
  - `storage_policy` → `marty.storage.v1`
  - `td2_service` → `marty.td2.v1`
  - `visa_service` → `marty.visa.v1`
- **Version Bump**: Project version increased from 0.1.0 to 1.0.0 to reflect breaking protobuf changes
- **GitHub Actions**: Enhanced proto-validation.yml workflow with Buf breaking change detection

### Infrastructure

- **Buf Configuration**: Added buf.yaml for protobuf linting and breaking change detection
- **Protobuf Compilation**: Regenerated all Python stubs with new package structure
- **CI/CD**: Updated GitHub Actions workflows to include breaking change validation

### Migration Guide

This is a breaking change that requires updating any external clients consuming the gRPC APIs:

1. **Update Protobuf Imports**: Change any direct .proto imports to use new package names
2. **Regenerate Client Stubs**: Regenerate client code from updated .proto files
3. **Update Service References**: Update any hardcoded service or message type references
4. **Test Integration**: Thoroughly test all integrations after migration

### Technical Details

- All protobuf type references now use fully qualified names (e.g., `marty.common.v1.ApiError`)
- Python import statements remain unchanged (still use `src.proto.service_pb2`)
- Cross-service type references updated to use new qualified names
- Buf breaking change detection configured for future API evolution

## [0.1.0] - 2025-09-XX

### Added

- Initial release with basic microservices architecture
- Core protobuf definitions for passport, mDoc, trust anchor, and other services
- gRPC service implementations
- Basic CI/CD pipelines

### Features

- Electronic passport processing
- Mobile driving license support
- Digital travel credential handling
- Trust anchor and PKI management
- Document signing services
- Biometric data processing
- RFID operations
- Data lifecycle management

---

**Note**: This changelog follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) format. For detailed technical information about the protobuf versioning policy and migration procedures, see [docs/architecture.md](docs/architecture.md).
