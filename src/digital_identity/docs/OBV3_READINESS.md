# Open Badge v3 Readiness Implementation

## Overview

This implementation adds complete Open Badge v3 (OBv3) readiness to the Marty Digital Identity platform, following the checklist requirements for MVP-blocking features.

## Architecture

### Core Components

1. **System Compliance Profiles** - Read-only templates for OBv3 formats
2. **Publish State Management** - DRAFT → PUBLISHED → ARCHIVED workflow  
3. **OBv3 Field Validation** - Enforced required claims (achievement, criteria, issuer, issuedOn)
4. **OID4VCI Integration** - Pre-authorized code flow with QR generation
5. **Wallet Compatibility** - Derived from format + protocol + compliance profile

### Data Model Changes

#### CredentialTemplateModel

```python
class CredentialTemplateModel(Base):
    # New fields for OBv3 readiness
    status: PublishStatus  # DRAFT, PUBLISHED, ARCHIVED
    compliance_profile_id: FK  # Links to system OBv3 profiles
    application_template_id: FK  # Required for application-based issuance
    issuer_certificate_chain_pem: Text  # X.509 cert chain
    issuer_did: String  # DID for DID-based issuance
```

#### FlowModel

```python
class FlowModel(Base):
    # New field
    issuance_protocol: String  # OID4VCI_PRE_AUTH, etc.
```

## System Compliance Profiles

Three read-only system profiles are seeded on initialization:

### 1. OB3_JWT
- **Format**: VC-JWT
- **Use Case**: Open Badge v3 with JWT proofs
- **Signing**: RS256, ES256, EdDSA
- **Revocation**: StatusList2021, BitstringStatusList

### 2. OB3_JSONLD  
- **Format**: JSON-LD
- **Use Case**: Open Badge v3 with Data Integrity proofs
- **Signing**: Ed25519, ES256K, BLS12381G2
- **Revocation**: StatusList2021, RevocationList2020

### 3. OB2_COMPATIBILITY
- **Format**: OB2_JSON
- **Use Case**: Legacy Open Badge v2 (migration only)
- **Signing**: RSA-SHA256
- **Status**: Deprecated

## Usage

### 1. Seed System Profiles

```bash
python -m digital_identity.infrastructure.persistence.seed_system_compliance_profiles
```

This creates the three system OBv3 compliance profiles in the database.

### 2. Create Credential Template from System Profile

```python
# Clone OB3_JWT system profile
compliance_profile = await compliance_repo.get_by_code("OB3_JWT")

# Get suggested OBv3 claims schema
validator = OBv3ValidationService()
suggested_claims = validator.get_suggested_claims_schema("OB3_JWT")

# Create template
template = await credential_template_service.create(
    name="University Degree Badge",
    credential_type="UniversityDegreeBadge",
    compliance_profile_id=compliance_profile.id,
    claims=suggested_claims,
    format="VC_JWT",
    issuer_did="did:web:university.edu",
)
```

### 3. Validate and Publish

```python
# Validates OBv3 requirements, issuer artifacts, application template link
published_template = await credential_template_service.publish(template.id)
```

Validation checks:
- ✅ All OBv3 required claims present (achievement, criteria, issuer, issuedOn)
- ✅ Nested fields complete (achievement.type, achievement.name, etc.)
- ✅ Issuer artifacts configured (issuer_did OR issuer_key_id OR issuer_certificate_chain_pem)
- ✅ Application template linked (for application-based issuance)
- ✅ Compliance profile format matches template format

### 4. Create Flow with OID4VCI

```python
flow = await flow_service.create(
    name="University Badge Issuance",
    flow_type=FlowType.ISSUANCE,
    credential_template_id=published_template.id,
    issuance_protocol="OID4VCI_PRE_AUTH",
    deployment_profile_id=deployment_profile.id,
)
```

### 5. Issue Credential via Application Workflow

```python
# User submits application
application = await application_service.create(
    application_template_id=template.application_template_id,
    applicant_data={"name": "Jane Student", "email": "jane@university.edu"},
)

# Approve application → triggers OID4VCI offer
approved = await application_service.approve(application.id)

# QR code URL available
print(approved.oid4vci_offer_url)  # openid-credential-offer://...
```

## Wallet Compatibility

Compatibility is **derived** (not user-configurable) from:
- `credential_format` (VC_JWT, JSON_LD, SD_JWT_VC, MDOC)
- `issuance_protocol` (OID4VCI_PRE_AUTH)
- `compliance_profile_code` (OB3_JWT, OB3_JSONLD)

```python
from digital_identity.application.utils import get_wallet_compatibility

compat = get_wallet_compatibility(
    credential_format="VC_JWT",
    issuance_protocol="OID4VCI_PRE_AUTH",
    compliance_profile_code="OB3_JWT",
)

print(compat["description"])
# "Compatible with Open Badge v3 wallets supporting W3C Verifiable 
#  Credentials (JWT) and OID4VCI pre-authorized code flow"

print(compat["wallets"])
# ["1Edtech Open Badge Passport", "Learning Credentials Wallet", ...]
```

## Publish State Enforcement

Only `PUBLISHED` templates can be:
- Referenced in Presentation Policies
- Used in Flow definitions
- Returned from public issuance APIs

```python
# Attempting to use DRAFT template in policy
policy = await presentation_policy_service.create(
    name="Age Verification",
    accepted_credential_types=[draft_template.id],  # ❌ FAILS
)
# ValueError: Cannot use DRAFT template in Presentation Policy

# Publish first
published = await credential_template_service.publish(draft_template.id)

# Now works
policy = await presentation_policy_service.create(
    name="Age Verification",
    accepted_credential_types=[published.id],  # ✅ SUCCESS
)
```

## Bulk Issuance Constraint (MVP)

**Bulk issuance is EVENT-DRIVEN ONLY** for MVP and does NOT auto-create Application records.

### Supported (MVP)
- Application-based issuance (single or batch via approval workflow)
- Direct API issuance for pre-authorized scenarios
- Event-driven bulk issuance (via event handlers)

### NOT Supported (MVP)
- Bulk issuance with automatic Application record generation
- Bulk audit trail at per-recipient granularity
- CSV upload → auto-generate applications

### Rationale

Auto-generating Applications for bulk issuance requires:
1. Async job queue infrastructure
2. Application state machine for each recipient
3. Rollback/retry logic for partial failures
4. Complex audit correlation across services

This is deferred to post-MVP. Current bulk issuance via event handlers is sufficient for high-volume scenarios where granular per-recipient application records are not required.

### For Post-MVP

Future enhancement will add:
```python
POST /v1/issuance/bulk
{
  "credential_template_id": "...",
  "application_template_id": "...",
  "recipients": [
    {"email": "user1@example.com", "claims": {...}},
    {"email": "user2@example.com", "claims": {...}},
    ...
  ]
}
```

This will auto-generate Application records and track per-recipient lifecycle.

## Validation

### OBv3 Field Validation

```python
from digital_identity.application.validation import OBv3ValidationService

validator = OBv3ValidationService()

is_valid, errors = validator.validate_claims_schema(
    claims_schema=[...],
    compliance_profile_code="OB3_JWT",
)

if not is_valid:
    for error in errors:
        print(f"❌ {error}")
```

**Required OBv3 Claims:**

| Claim | Type | Nested Fields Required |
|-------|------|------------------------|
| `achievement` | object | type, name, description, criteria |
| `criteria` | object | narrative |
| `issuer` | object | type, name, id |
| `issuedOn` | datetime | (ISO 8601) |

### Publishing Validation

```python
# Automatically runs during publish()
published = await service.publish(template_id)

# Or manual validation
errors = await service._validate_for_publish(template)
```

## API Endpoints

### Credential Templates

```http
POST   /v1/credential-templates
GET    /v1/credential-templates
GET    /v1/credential-templates/{id}
PUT    /v1/credential-templates/{id}
DELETE /v1/credential-templates/{id}

POST   /v1/credential-templates/{id}/publish
POST   /v1/credential-templates/{id}/unpublish
GET    /v1/credential-templates/{id}/wallet-compatibility
```

### Compliance Profiles

```http
GET    /v1/compliance-profiles
GET    /v1/compliance-profiles/{id}
GET    /v1/compliance-profiles/code/{code}
```

System profiles are read-only (cannot POST/PUT/DELETE).

### Seeding

```http
POST   /v1/admin/seed/compliance-profiles
```

## Testing

### Integration Test

```python
async def test_obv3_end_to_end():
    # Seed profiles
    await seed_system_compliance_profiles(session)
    
    # Get OB3_JWT profile
    profile = await compliance_repo.get_by_code("OB3_JWT")
    
    # Create template
    template = await service.create(
        name="Test Badge",
        credential_type="TestBadge",
        compliance_profile_id=profile.id,
        claims=validator.get_suggested_claims_schema("OB3_JWT"),
        format="VC_JWT",
        issuer_did="did:web:test.edu",
        application_template_id=app_template.id,
    )
    
    # Validate claims
    is_valid, errors = validator.validate_full_template(template_dict, profile_dict)
    assert is_valid
    
    # Publish
    published = await service.publish(template.id)
    assert published.status == "PUBLISHED"
    
    # Create flow
    flow = await flow_service.create(
        name="Badge Issuance",
        credential_template_id=published.id,
        issuance_protocol="OID4VCI_PRE_AUTH",
    )
    
    # Issue credential
    application = await application_service.create(...)
    approved = await application_service.approve(application.id)
    assert approved.oid4vci_offer_url
```

## Migration

Run the database migration:

```bash
alembic upgrade head
```

This applies migration `006_obv3_readiness`:
- Adds `PublishStatus` enum
- Adds `status`, `compliance_profile_id`, `application_template_id` to credential_templates
- Adds `issuer_certificate_chain_pem`, `issuer_did` fields
- Adds `issuance_protocol` to flows
- Creates necessary indexes and foreign keys

## Rollback

```bash
alembic downgrade -1
```

Removes all OBv3 fields and restores previous schema.

## Dependencies

- SQLAlchemy 2.0+ (async ORM)
- Alembic (migrations)
- Pydantic (validation schemas)
- marty-core (crypto/verification via FFI)

## References

- [Open Badge v3 Specification](https://www.imsglobal.org/spec/ob/v3p0/)
- [W3C Verifiable Credentials Data Model](https://www.w3.org/TR/vc-data-model/)
- [OpenID for Verifiable Credential Issuance (OID4VCI)](https://openid.net/specs/openid-4-verifiable-credential-issuance-1_0.html)
- [Digital Identity Model White Paper](../../../docs/Digital_Identity_model.md)
