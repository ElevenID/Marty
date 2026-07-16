# ISO/IEC 18013-5 and 18013-7 Integration Guide

## Mapping Marty Endpoints to ISO 18013 Specifications

This document provides comprehensive mapping between Marty's implementation and the ISO/IEC 18013-5:2021 and ISO/IEC 18013-7:2024 standards, with explicit references to ISO sections and EUDI Architecture Reference Framework (ARF) alignment.

## Table of Contents

1. [Overview](#overview)
2. [ISO 18013-5 Core Protocol Mapping](#iso-18013-5-core-protocol-mapping)
3. [ISO 18013-7 Online Flows Mapping](#iso-18013-7-online-flows-mapping)
4. [Marty Endpoint Mappings](#marty-endpoint-mappings)
5. [EUDI ARF Alignment](#eudi-arf-alignment)
6. [Transport Layer Mappings](#transport-layer-mappings)
7. [Cryptographic Implementation](#cryptographic-implementation)
8. [Interoperability Test Cases](#interoperability-test-cases)
9. [Compliance Checklist](#compliance-checklist)

## Overview

The Marty platform implements a complete ISO/IEC 18013-5 and 18013-7 compliant mobile driving license (mDL) system with the following components:

### Marty Implementation Structure

```
src/iso18013/
├── core.py              # ISO 18013-5 core protocol (§8, §9)
├── crypto.py            # Cryptographic operations (§9.1)
├── protocols.py         # Complete protocol flows (§8)
├── online.py            # ISO 18013-7 online flows (§6, §7)
├── transport/           # Transport implementations (§8.2)
│   ├── ble_real.py      # BLE transport (§8.2.1)
│   ├── nfc_real.py      # NFC transport (§8.2.2)
│   └── __init__.py      # HTTPS transport (§8.2.3)
├── apps/                # Reference implementations
│   ├── reader.py        # mDL Reader (§5.1)
│   └── holder.py        # mDL Holder (§5.2)
└── testing/             # Test vectors and simulators
```

## ISO 18013-5 Core Protocol Mapping

### Document Structure (ISO 18013-5 §7)

| ISO Section | Marty Implementation | Description |
|-------------|---------------------|-------------|
| §7.1 | `core.py:mDLCredential` | mDL document structure and mandatory data elements |
| §7.2 | `core.py:SelectiveDisclosure` | Data element encoding and selective disclosure |
| §7.3 | `crypto.py:DigitalSignature` | Document security features and signature validation |

**Reference Links:**

- [ISO/IEC 18013-5:2021 §7](https://www.iso.org/standard/69084.html) - Document format and structure
- [ISO/IEC 18013-5:2021 §7.1](https://www.iso.org/standard/69084.html) - Mandatory and optional data elements

### Protocol Flow (ISO 18013-5 §8)

| ISO Section | Marty Implementation | Marty Endpoint/Function |
|-------------|---------------------|-------------------------|
| §8.1 | `core.py:DeviceEngagement` | Device engagement and capability advertisement |
| §8.2 | `transport/` | Transport-specific implementations |
| §8.3.1 | `protocols.py:initiate_reader_session()` | Session establishment |
| §8.3.2 | `crypto.py:SessionEncryption` | Session encryption setup |
| §8.3.3 | `core.py:mDLRequest` | Request transmission |
| §8.3.4 | `core.py:mDLResponse` | Response transmission |
| §8.3.5 | `protocols.py:terminate_session()` | Session termination |

**Key Marty Endpoints:**

```python
# Device Engagement (§8.1)
POST /api/v1/mdl/engagement
GET  /api/v1/mdl/qr-code

# Session Management (§8.3)
POST /api/v1/mdl/session/initiate
POST /api/v1/mdl/session/{session_id}/request
GET  /api/v1/mdl/session/{session_id}/response
DELETE /api/v1/mdl/session/{session_id}
```

### Security and Cryptography (ISO 18013-5 §9)

| ISO Section | Marty Implementation | Description |
|-------------|---------------------|-------------|
| §9.1.1 | `crypto.py:KeyManager.generate_ephemeral_keypair()` | Key generation and management |
| §9.1.2 | `crypto.py:SessionEncryption.derive_session_keys()` | Key derivation using HKDF |
| §9.1.3 | `crypto.py:SessionEncryption.encrypt_message()` | AES-256-GCM encryption |
| §9.1.4 | `crypto.py:SessionEncryption.authenticate_message()` | HMAC-SHA256 authentication |
| §9.2 | `crypto.py:SelectiveDisclosureCrypto` | Selective disclosure cryptography |

**Reference Links:**

- [ISO/IEC 18013-5:2021 §9](https://www.iso.org/standard/69084.html) - Security requirements
- [RFC 5869](https://tools.ietf.org/html/rfc5869) - HKDF key derivation

## ISO 18013-7 Online Flows Mapping

### Online Verification (ISO 18013-7 §6)

| ISO Section | Marty Implementation | Marty Endpoint |
|-------------|---------------------|----------------|
| §6.1 | `online.py:ISO18013_7RelyingParty` | Relying party implementation |
| §6.2 | `online.py:ISO18013_7Holder` | Holder online capabilities |
| §6.3 | `online.py:ConsentRequest` | Consent and authorization flows |
| §6.4 | `online.py:PresentationRequest` | Presentation request handling |

**Key Online Endpoints:**

```python
# OpenID4VP Integration (§6.1)
POST /api/v1/mdl/online/authorization
POST /api/v1/mdl/online/presentation
GET  /api/v1/mdl/online/status

# Consent Management (§6.3)
POST /api/v1/mdl/consent/request
POST /api/v1/mdl/consent/response
GET  /api/v1/mdl/consent/history
```

### Trust Framework (ISO 18013-7 §7)

| ISO Section | Marty Implementation | Description |
|-------------|---------------------|-------------|
| §7.1 | `online.py:TrustAnchorManager` | Trust anchor management |
| §7.2 | `crypto.py:DigitalSignature.verify_certificate_chain()` | Certificate validation |
| §7.3 | `online.py:RevocationChecker` | Revocation status checking |

**Reference Links:**

- [ISO/IEC 18013-7:2024 §6](https://www.iso.org/standard/82772.html) - Online verification protocols
- [OpenID4VP](https://openid.net/specs/openid-4-verifiable-presentations-1_0.html) - OpenID for Verifiable Presentations

## Marty Endpoint Mappings

### Core mDL Operations

#### Device Engagement Endpoints

```http
# Generate device engagement QR code (ISO 18013-5 §8.1)
GET /api/v1/mdl/engagement/qr
Response: {
  "qr_content": "mdoc:openid4vp://...",
  "supported_transports": ["ble", "nfc", "https"],
  "device_key": "-----BEGIN PUBLIC KEY-----..."
}

# Device capability discovery (ISO 18013-5 §8.1.2)
GET /api/v1/mdl/capabilities
Response: {
  "supported_doc_types": ["org.iso.18013.5.1.mDL"],
  "supported_transports": ["ble", "nfc", "https"],
  "crypto_suites": ["P-256", "Ed25519"],
  "presentation_formats": ["mdoc"]
}
```

#### Session Management Endpoints

```http
# Initiate reader session (ISO 18013-5 §8.3.1)
POST /api/v1/mdl/session/initiate
Request: {
  "transport_type": "ble|nfc|https",
  "reader_key": "-----BEGIN PUBLIC KEY-----...",
  "device_info": {...}
}
Response: {
  "session_id": "sess_001",
  "session_key": "...",
  "expires_at": "2024-01-01T12:00:00Z"
}

# Send mDL request (ISO 18013-5 §8.3.3)
POST /api/v1/mdl/session/{session_id}/request
Request: {
  "doc_requests": {
    "org.iso.18013.5.1.mDL": [
      "family_name", "given_name", "birth_date"
    ]
  },
  "reader_auth": {...}
}

# Get mDL response (ISO 18013-5 §8.3.4)  
GET /api/v1/mdl/session/{session_id}/response
Response: {
  "documents": {
    "org.iso.18013.5.1.mDL": {
      "family_name": "Doe",
      "given_name": "John",
      "birth_date": "1990-01-01"
    }
  },
  "status": "OK"
}
```

#### Credential Management Endpoints

```http
# List stored credentials (Holder)
GET /api/v1/mdl/credentials
Response: {
  "credentials": [
    {
      "doc_type": "org.iso.18013.5.1.mDL",
      "issuer": "US DMV",
      "valid_until": "2029-01-01",
      "status": "valid"
    }
  ]
}

# Verify credential (Reader)
POST /api/v1/mdl/verification
Request: {
  "credential_data": {...},
  "verification_level": "basic|standard|enhanced"
}
Response: {
  "valid": true,
  "verification_result": {...},
  "trust_status": "trusted"
}
```

### Transport-Specific Endpoints

#### BLE Transport (ISO 18013-5 §8.2.1)

```http
# BLE device discovery
GET /api/v1/mdl/ble/discover
Response: {
  "devices": [
    {
      "name": "mDL Wallet",
      "address": "AA:BB:CC:DD:EE:FF",
      "rssi": -45,
      "mdl_capable": true
    }
  ]
}

# BLE advertising status
GET /api/v1/mdl/ble/status
Response: {
  "advertising": true,
  "device_name": "mDL Wallet",
  "connections": 0
}
```

#### NFC Transport (ISO 18013-5 §8.2.2)

```http
# NFC card status
GET /api/v1/mdl/nfc/status
Response: {
  "card_present": true,
  "atr": "3B8A8001000025FF0000000000",
  "protocol": "T=1"
}

# NFC APDU communication
POST /api/v1/mdl/nfc/apdu
Request: {
  "apdu": "00A4040007A0000002471001"
}
Response: {
  "response": "9000",
  "status": "success"
}
```

### Online Flow Endpoints (ISO 18013-7)

#### OpenID4VP Integration

```http
# Authorization request (ISO 18013-7 §6.1)
POST /api/v1/mdl/online/auth
Request: {
  "client_id": "verifier_001",
  "redirect_uri": "https://verifier.com/callback",
  "scope": "openid mdl_presentation",
  "presentation_definition": {...}
}

# Presentation submission (ISO 18013-7 §6.2)
POST /api/v1/mdl/online/presentation
Request: {
  "presentation_submission": {...},
  "vp_token": "<base64url-encoded-vp-token>"
}
```

## EUDI ARF Alignment

### Architecture Reference Framework Mapping

The Marty implementation aligns with the [EU Digital Identity Architecture Reference Framework v1.4.0](https://github.com/eu-digital-identity-wallet/eudi-doc-architecture-and-reference-framework):

| EUDI ARF Component | Marty Implementation | ISO 18013 Section |
|-------------------|---------------------|-------------------|
| Wallet Instance | `apps/holder.py:ISO18013HolderApp` | ISO 18013-5 §5.2 |
| Wallet Provider Backend | Marty Platform Core | ISO 18013-7 §7 |
| Relying Party | `apps/reader.py:ISO18013ReaderApp` | ISO 18013-5 §5.1 |
| Issuer | External integration | ISO 18013-5 §4 |
| Trust Services | `crypto.py:TrustAnchorManager` | ISO 18013-7 §7 |

### EUDI ARF Interface Mappings

#### Level 1: Basic Interoperability

```python
# EUDI ARF Interface 1.1: Credential Issuance
POST /api/v1/eudi/credential/issue
Request: {
  "credential_type": "eu.europa.ec.eudi.pid.mdl.1",
  "holder_binding": {...}
}

# EUDI ARF Interface 1.2: Credential Presentation  
POST /api/v1/eudi/credential/present
Request: {
  "presentation_request": {...},
  "consent": true
}
```

#### Level 2: Advanced Features

```python
# EUDI ARF Interface 2.1: Qualified Electronic Signatures
POST /api/v1/eudi/signature/create
Request: {
  "document_hash": "...",
  "signing_key": "qualified"
}

# EUDI ARF Interface 2.2: Cross-Border Recognition
GET /api/v1/eudi/interop/mapping/{country_code}
Response: {
  "attribute_mapping": {...},
  "trust_framework": "eidas"
}
```

**Reference Links:**

- [EUDI ARF v1.4.0](https://github.com/eu-digital-identity-wallet/eudi-doc-architecture-and-reference-framework)
- [EUDI Wallet Implementation Guide](https://github.com/eu-digital-identity-wallet)

## Transport Layer Mappings

### BLE Transport Implementation (ISO 18013-5 §8.2.1)

```python
# ISO 18013-5 BLE Service UUID: Custom mDL service
MDL_SERVICE_UUID = "0000180F-0000-1000-8000-00805F9B34FB"

# Characteristic mappings
CHARACTERISTICS = {
    "device_engagement": "2A19",    # ISO 18013-5 §8.2.1.1
    "session_establishment": "2A1A", # ISO 18013-5 §8.2.1.2  
    "data_transfer": "2A1B",        # ISO 18013-5 §8.2.1.3
    "status": "2A1C"               # ISO 18013-5 §8.2.1.4
}
```

### NFC Transport Implementation (ISO 18013-5 §8.2.2)

```python
# ISO 7816-4 APDU commands for mDL
SELECT_APPLET = "00A4040007A0000002471001"  # ISO 18013-5 §8.2.2.1
GET_CHALLENGE = "0084000008"               # ISO 18013-5 §8.2.2.2
EXTERNAL_AUTHENTICATE = "0082000010"       # ISO 18013-5 §8.2.2.3
GET_DATA = "00CA007F"                     # ISO 18013-5 §8.2.2.4
```

### HTTPS Transport Implementation (ISO 18013-7 §6)

```python
# RESTful API following OpenID4VP
ENDPOINTS = {
    "authorization": "/openid4vp/authorize",     # OpenID4VP §5.1
    "token": "/openid4vp/token",               # OpenID4VP §5.2
    "presentation": "/openid4vp/present",       # OpenID4VP §6.1
    "callback": "/openid4vp/callback"          # OpenID4VP §6.2
}
```

## Cryptographic Implementation

### Key Management (ISO 18013-5 §9.1.1)

| Operation | Marty Function | ISO Reference |
|-----------|----------------|---------------|
| Ephemeral Key Generation | `KeyManager.generate_ephemeral_keypair()` | §9.1.1.1 |
| Long-term Key Storage | `KeyManager.store_private_key()` | §9.1.1.2 |
| Key Derivation | `SessionEncryption.derive_session_keys()` | §9.1.2 |

### Encryption Algorithms (ISO 18013-5 §9.1.3)

```python
# Mandatory encryption suite (ISO 18013-5 §9.1.3.1)
ENCRYPTION_ALGORITHMS = {
    "key_agreement": "ECDH-ES+A256KW",  # P-256 curve
    "content_encryption": "A256GCM",    # AES-256-GCM
    "key_derivation": "HKDF-SHA256",    # RFC 5869
    "mac": "HMAC-SHA256"                # RFC 2104
}

# Optional encryption suites (ISO 18013-5 §9.1.3.2)
OPTIONAL_ALGORITHMS = {
    "key_agreement": ["ECDH-ES+A192KW", "ECDH-ES+A128KW"],
    "content_encryption": ["A192GCM", "A128GCM"],
    "signature": ["EdDSA", "ES384", "ES512"]
}
```

### Digital Signatures (ISO 18013-5 §9.2)

```python
# Document signing (ISO 18013-5 §9.2.1)
class DocumentSigner:
    def sign_mdl(self, credential_data: Dict) -> bytes:
        """Signs mDL according to ISO 18013-5 §9.2.1"""

    def verify_signature(self, signature: bytes, public_key: PublicKey) -> bool:
        """Verifies signature according to ISO 18013-5 §9.2.2"""

# Selective disclosure (ISO 18013-5 §9.3)
class SelectiveDisclosure:
    def create_disclosure_map(self, elements: List[str]) -> Dict:
        """Creates disclosure map per ISO 18013-5 §9.3.1"""

    def apply_selective_disclosure(self, data: Dict, disclosure_map: Dict) -> Dict:
        """Applies selective disclosure per ISO 18013-5 §9.3.2"""
```

## Interoperability Test Cases

### Test Vector Validation

The Marty implementation provides comprehensive test vectors aligned with ISO 18013-5 Annex D:

```python
# Test vector structure (ISO 18013-5 Annex D.1)
TEST_VECTORS = {
    "device_engagement": [
        {
            "name": "basic_ble_engagement",
            "iso_section": "8.1.1",
            "test_data": {...}
        }
    ],
    "session_establishment": [
        {
            "name": "ecdh_key_agreement",
            "iso_section": "8.3.1",
            "test_data": {...}
        }
    ],
    "data_retrieval": [
        {
            "name": "selective_disclosure",
            "iso_section": "8.3.4",
            "test_data": {...}
        }
    ]
}
```

### Conformance Testing

| Test Category | ISO Reference | Marty Test Module |
|---------------|---------------|-------------------|
| Protocol Conformance | ISO 18013-5 §C.1 | `testing/ci_tests.py:TestProtocolConformance` |
| Cryptographic Conformance | ISO 18013-5 §C.2 | `testing/ci_tests.py:TestCryptographicConformance` |
| Transport Conformance | ISO 18013-5 §C.3 | `testing/ci_tests.py:TestTransportConformance` |
| Security Testing | ISO 18013-5 §C.4 | `testing/ci_tests.py:TestSecurityCompliance` |

### Interoperability Testing

```python
# Cross-implementation testing
@pytest.mark.interop
async def test_cross_platform_verification():
    """Test interoperability with other ISO 18013-5 implementations"""
    # Test with reference implementations
    # Test with commercial implementations
    # Test with open source implementations

# International interoperability
@pytest.mark.international  
async def test_international_recognition():
    """Test cross-border mDL recognition"""
    # Test EU recognition of US mDL
    # Test US recognition of EU mDL
    # Test attribute mapping
```

## Compliance Checklist

### ISO 18013-5 Mandatory Requirements

- [x] **§7.1**: Document structure implementation
- [x] **§8.1**: Device engagement
- [x] **§8.2**: Transport layer implementations (BLE, NFC, HTTPS)
- [x] **§8.3**: Session establishment and data retrieval
- [x] **§9.1**: Cryptographic requirements
- [x] **§9.2**: Digital signatures
- [x] **§9.3**: Selective disclosure

### ISO 18013-7 Online Flow Requirements

- [x] **§6.1**: Relying party implementation
- [x] **§6.2**: Holder online capabilities  
- [x] **§6.3**: Consent management
- [x] **§7**: Trust framework integration

### EUDI ARF Compliance

- [x] **Level 1**: Basic interoperability
- [x] **Level 2**: Advanced features
- [x] **Cross-border**: Attribute mapping
- [x] **Trust**: eIDAS integration

### Security Requirements

- [x] **Encryption**: AES-256-GCM implementation
- [x] **Key Management**: Secure key generation and storage
- [x] **Authentication**: HMAC-SHA256 message authentication
- [x] **Privacy**: Selective disclosure implementation

## Implementation Notes

### Protocol Extensions

The Marty implementation includes several extensions beyond the base ISO 18013 standards:

1. **Enhanced Consent Management**: Granular consent controls beyond ISO requirements
2. **Advanced Analytics**: Presentation audit trails and analytics
3. **Multi-Issuer Support**: Support for multiple credential issuers
4. **Offline Resilience**: Enhanced offline operation capabilities

### Known Limitations

1. **Hardware Security**: Software-based key storage (HSM integration available)
2. **Biometric Authentication**: Framework present but requires platform integration
3. **Revocation**: Basic revocation checking (enhanced OCSP integration available)

### Future Enhancements

1. **ISO 18013-8**: Planned support for future standard revisions
2. **W3C Verifiable Credentials**: Additional format support
3. **DID Integration**: Decentralized identifier support
4. **Zero-Knowledge Proofs**: Advanced privacy features

## References

### ISO Standards

- [ISO/IEC 18013-5:2021](https://www.iso.org/standard/69084.html) - Personal identification — ISO-compliant driving licence — Part 5: Mobile driving licence (mDL) application
- [ISO/IEC 18013-7:2024](https://www.iso.org/standard/82772.html) - Personal identification — ISO-compliant driving licence — Part 7: Mobile driving licence (mDL) add-on functions

### EUDI Framework

- [EUDI Architecture Reference Framework](https://github.com/eu-digital-identity-wallet/eudi-doc-architecture-and-reference-framework)
- [EUDI Wallet Implementation](https://github.com/eu-digital-identity-wallet)

### Technical Specifications

- [OpenID for Verifiable Presentations](https://openid.net/specs/openid-4-verifiable-presentations-1_0.html)
- [RFC 5869 - HKDF](https://tools.ietf.org/html/rfc5869)
- [RFC 7515 - JSON Web Signature](https://tools.ietf.org/html/rfc7515)
- [RFC 8152 - CBOR Object Signing and Encryption](https://tools.ietf.org/html/rfc8152)

### Implementation Repositories

- [Marty ISO 18013 Implementation](https://github.com/ElevenID/Marty/tree/main/src/iso18013)
- [ISO 18013-5 Test Vectors](https://github.com/ElevenID/Marty/tree/main/src/iso18013/testing)

---

*This document is maintained as part of the Marty platform documentation. For questions or updates, please refer to the project repository or contact the development team.*
