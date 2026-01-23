# Presentation Policy Implementation Summary

## Overview
Complete implementation of Presentation Policy support across all Marty platform components:
- Backend API (Python/FastAPI)
- Policy evaluation engine (Rust)
- Mobile wallet (Flutter/Dart)
- Verification app (Tauri)

## Architecture Decisions

### 1. Holder Sovereignty
**Decision**: Allow holders to decline required claims with prominent warning
- Rationale: Respects user autonomy; verification outcome will indicate policy non-compliance
- Implementation: UI shows warnings but allows proceeding with reduced disclosure

### 2. Policy Exposure
**Decision**: No third-party policy exposure at protocol level
- Rationale: Prevents privacy leaks and fingerprinting attacks
- Implementation: Policies cached locally on authorized devices only

### 3. Credential Ranking
**Decision**: Configurable ranking strategies with custom weights
- Strategies: FRESHEST_FIRST, HIGHEST_TRUST_FIRST, MINIMUM_CLAIMS_FIRST, CUSTOM
- Implementation: Rust-based ranking with pluggable strategies

## Components Implemented

### 1. Backend Extensions (Python/FastAPI)

#### Domain Model (`entities.py`)
```python
class PresentationPolicy:
    # Existing fields
    id: str
    name: str
    credential_types: list[str]
    required_claims: list[RequiredClaim]
    optional_claims: list[RequiredClaim]
    require_trust_profile: bool
    max_credential_age_days: Optional[int]
    
    # NEW FIELDS
    allowed_issuers: list[str]  # Issuer allowlist (empty = all allowed)
    derived_attribute_preferences: dict[str, str]  # Raw claim → derived mapping
    credential_ranking_strategy: CredentialRankingStrategy  # Ranking algorithm
    credential_ranking_weights: dict[str, float]  # Custom strategy weights
```

#### Value Objects (`value_objects.py`)
```python
class CredentialRankingStrategy(str, Enum):
    FRESHEST_FIRST = "FRESHEST_FIRST"           # Prefer newest credentials
    HIGHEST_TRUST_FIRST = "HIGHEST_TRUST_FIRST" # Prefer highest trust level
    MINIMUM_CLAIMS_FIRST = "MINIMUM_CLAIMS_FIRST" # Prefer fewest claims (data minimization)
    CUSTOM = "CUSTOM"                           # Use custom weights
```

#### REST API (`routers.py`)
**New Endpoint**: `GET /api/v1/identity/presentation-policies/sync`
- **Authentication**: Required (Bearer token)
- **Headers**: 
  - `If-Modified-Since` (optional) - RFC 2822 date for delta sync
  - `Last-Modified` (response) - Timestamp of latest policy update
- **Response**: 
  - 200 OK with policy list
  - 304 Not Modified if no updates
- **Purpose**: Authenticated policy distribution to authorized devices

### 2. Rust Policy Module (`marty-verification`)

#### Module Structure
```
marty-verification/src/policy/
├── mod.rs                  # PolicyEvaluator orchestrator
├── types.rs                # Core types and enums
├── claim_evaluator.rs      # Claim constraint checking
├── freshness.rs            # Credential age validation
├── issuer.rs               # Issuer allowlist checking
├── disclosure.rs           # Minimum disclosure resolution
└── ranking.rs              # Credential ranking strategies
```

#### Key Components

**PolicyEvaluator** (`mod.rs`)
- Orchestrates all constraint checks
- Returns `PolicyEvaluationResult` with violations and warnings
- Checks: claims, issuer, freshness, trust profile

**ClaimConstraintEvaluator** (`claim_evaluator.rs`)
- Validates all required claims are present
- Supports derived attribute preferences
- Returns missing claims list

**IssuerConstraintChecker** (`issuer.rs`)
- Checks issuer against allowlist
- Empty allowlist = all issuers allowed

**FreshnessChecker** (`freshness.rs`)
- Validates credential age against `max_credential_age_days`
- Uses Unix timestamp (i64) for issuance date

**CredentialRanker** (`ranking.rs`)
- Implements 4 ranking strategies:
  1. **FRESHEST_FIRST**: Sort by issuance date (newest first)
  2. **HIGHEST_TRUST_FIRST**: Sort by trust level (highest first)
  3. **MINIMUM_CLAIMS_FIRST**: Sort by claim count (fewest first - data minimization)
  4. **CUSTOM**: Weighted combination of freshness, trust, claim count

**MinimumDisclosureResolver** (`disclosure.rs`)
- Returns only required claims for policy
- Used in UI to show minimum disclosure set

### 3. Policy Sync Infrastructure (`marty-sync`)

#### PolicySyncProvider (`policy.rs`)
```rust
impl PolicySyncProvider {
    pub async fn fetch_all(&self, auth_token: &str) -> Result<Vec<PresentationPolicy>>
    pub async fn fetch_delta(&self, auth_token: &str, since: DateTime<Utc>) -> Result<Vec<PresentationPolicy>>
}
```

**Features**:
- Authenticated HTTP requests with Bearer token
- If-Modified-Since support for delta sync
- Automatic JSON deserialization to `PresentationPolicy`
- Error handling with detailed error types

**Storage** (`marty-app-storage`)
- SQLite table: `presentation_policies`
- Columns: `id`, `policy_json TEXT`, `version INTEGER`, `synced_at TEXT`, `deployment_profile_id`

### 4. Flutter Integration (`marty-authenticator`)

#### Rust Bridge (`rust/src/api.rs`)
```rust
#[flutter_rust_bridge::frb]
pub async fn sync_policies(auth_token: String) -> Result<Vec<PresentationPolicy>>

#[flutter_rust_bridge::frb]
pub async fn evaluate_presentation_request(
    policy_id: String,
    presented_claims: HashMap<String, String>,
    issuer_id: String,
    issuance_date: i64,
    trust_verified: bool
) -> Result<PolicyEvaluationResult>

#[flutter_rust_bridge::frb]
pub async fn get_minimum_disclosure_set(policy_id: String) -> Result<Vec<ClaimRequirement>>

#[flutter_rust_bridge::frb]
pub async fn rank_matching_credentials(
    policy_id: String,
    credentials: Vec<MatchingCredential>
) -> Result<Vec<MatchingCredential>>

#[flutter_rust_bridge::frb]
pub async fn check_issuer_constraints(
    policy_id: String,
    issuer_id: String
) -> Result<bool>
```

#### Dart Service (`lib/services/policy_service.dart`)
```dart
class PolicyService extends ChangeNotifier {
  List<PresentationPolicy> _policies = [];
  
  Future<void> initialize() async
  Future<void> syncPolicies(String authToken) async
  PresentationPolicy? findPolicyByCredentialType(String credentialType)
  List<RequiredClaim> getMinimumDisclosureSet(PresentationPolicy policy)
  bool isClaimRequired(PresentationPolicy policy, String claimPath)
  String? getDerivedAttributePreference(PresentationPolicy policy, String rawClaim)
}
```

**Features**:
- Background sync every 6 hours
- FlutterSecureStorage for cached policies
- ChangeNotifier for reactive UI updates
- Automatic initialization on app start

#### UI Widget (`lib/widgets/policy_driven_disclosure_widget.dart`)
```dart
class PolicyDrivenDisclosureWidget extends StatefulWidget {
  final PresentationPolicy policy;
  final Map<String, dynamic> availableClaims;
  final Function(Set<String> selectedClaims) onSelectionChanged;
}
```

**Features**:
- Separates required vs optional claims
- Shows warning icon for required claims
- Displays derived attribute preferences
- Allows holder to decline required claims (with warning)
- Real-time selection feedback

### 5. Verifier Integration (`marty-verifier`)

#### Policy Evaluation in Verification Flow (`verification.rs`)
```rust
async fn load_cached_policies(state: &AppState) -> AppResult<Vec<PresentationPolicy>>

async fn evaluate_policy_constraints(
    request: &VerifyRequest,
    issuer_id: &str,
    trust_verified: bool,
    state: &AppState,
) -> Vec<String>  // Returns policy violation warnings
```

**Integration Point**:
- Called after cryptographic verification succeeds
- Checks: issuer allowlist, trust profile requirement, freshness
- Appends warnings to `VerificationResult.warnings`
- Does NOT fail verification (informational only)

**Storage**:
- Policies synced to local SQLite database
- Filtered by `deployment_profile_id`
- JSON serialization for flexibility

## Test Coverage

### 1. Backend API Tests (`tests/test_presentation_policies.py`)
**Coverage**:
- ✅ Create policy (full and minimal)
- ✅ Invalid ranking strategy validation
- ✅ List all policies
- ✅ Get policy by ID
- ✅ Policy not found (404)
- ✅ Update policy
- ✅ Delete policy
- ✅ Sync endpoint without auth (401)
- ✅ Initial sync (no If-Modified-Since)
- ✅ Sync with If-Modified-Since (304 response)
- ✅ Sync after update (returns delta)
- ✅ Unauthorized access checks

### 2. Rust Policy Tests (`marty-verification/tests/policy_tests.rs`)
**Coverage**:
- ✅ Claim evaluator - all required present
- ✅ Claim evaluator - missing required claims
- ✅ Claim evaluator - derived attribute support
- ✅ Issuer checker - allowed issuer
- ✅ Issuer checker - not allowed issuer
- ✅ Issuer checker - empty allowlist (allows all)
- ✅ Freshness checker - fresh credential
- ✅ Freshness checker - stale credential
- ✅ Freshness checker - no constraint
- ✅ Minimum disclosure resolver
- ✅ Credential ranker - FRESHEST_FIRST
- ✅ Credential ranker - HIGHEST_TRUST_FIRST
- ✅ Credential ranker - MINIMUM_CLAIMS_FIRST
- ✅ Credential ranker - CUSTOM with weights
- ✅ Policy evaluator - full evaluation (all satisfied)
- ✅ Policy evaluator - untrusted issuer
- ✅ Policy evaluator - stale credential
- ✅ Policy evaluator - missing trust profile

### 3. Dart Service Tests (`marty-authenticator/test/services/policy_service_test.dart`)
**Coverage**:
- ✅ Initialize with empty policies
- ✅ Load cached policies from storage
- ✅ Handle missing cache gracefully
- ✅ Handle invalid JSON in cache
- ✅ Find policy by credential type
- ✅ Return null when policy not found
- ✅ Get minimum disclosure set
- ✅ Check if claim is required
- ✅ Get derived attribute preference
- ✅ Update policies and notify listeners
- ✅ Parse RequiredClaim from JSON
- ✅ Serialize RequiredClaim to JSON
- ✅ Parse PresentationPolicy from JSON
- ✅ Serialize PresentationPolicy to JSON

## Database Migration

### Migration File: `004_extend_presentation_policies.py`
```python
def upgrade():
    op.add_column('presentation_policies', sa.Column('allowed_issuers', sa.JSON(), nullable=True))
    op.add_column('presentation_policies', sa.Column('derived_attribute_preferences', sa.JSON(), nullable=True))
    op.add_column('presentation_policies', sa.Column('credential_ranking_strategy', sa.String(50), nullable=True))
    op.add_column('presentation_policies', sa.Column('credential_ranking_weights', sa.JSON(), nullable=True))
    
    # Set defaults for existing rows
    op.execute("""
        UPDATE presentation_policies 
        SET allowed_issuers = '[]',
            derived_attribute_preferences = '{}',
            credential_ranking_strategy = 'FRESHEST_FIRST',
            credential_ranking_weights = '{}'
        WHERE allowed_issuers IS NULL
    """)
    
    # Make columns non-nullable
    op.alter_column('presentation_policies', 'allowed_issuers', nullable=False)
    op.alter_column('presentation_policies', 'derived_attribute_preferences', nullable=False)
    op.alter_column('presentation_policies', 'credential_ranking_strategy', nullable=False)
    op.alter_column('presentation_policies', 'credential_ranking_weights', nullable=False)
```

**Note**: User opted to skip migration and restart services instead.

## Data Flow

### Policy Creation Flow
1. Administrator creates policy via backend API
2. Policy stored in PostgreSQL database
3. Policy available via sync endpoint with authentication

### Policy Distribution Flow
1. Mobile wallet/verifier authenticates with backend
2. Calls `/api/v1/identity/presentation-policies/sync`
3. Backend returns all policies (or delta if If-Modified-Since provided)
4. Client caches policies in local SQLite/FlutterSecureStorage
5. Background sync every 6 hours keeps policies up-to-date

### Credential Selection Flow (Mobile Wallet)
1. Presentation request arrives
2. PolicyService finds applicable policy by credential type
3. UI shows required vs optional claims
4. Holder selects claims to disclose (can decline required with warning)
5. Rust evaluates disclosure against policy
6. Warnings shown if policy not fully satisfied
7. Holder confirms and presents selected claims

### Verification Flow (Verifier App)
1. Credential received for verification
2. Cryptographic verification performed first
3. If crypto verification passes, load cached policies
4. Find applicable policy by credential type
5. Evaluate policy constraints:
   - Issuer allowlist check
   - Trust profile requirement check
   - Freshness check (if configured)
6. Append policy violations to result warnings
7. Return verification result with warnings

## Key Design Principles

1. **Separation of Concerns**
   - Cryptographic verification independent of policy checks
   - Policy violations are warnings, not hard failures
   - Allows for "verify then evaluate" pattern

2. **Performance**
   - Rust implementation for performance-critical evaluation
   - Local caching to support offline verification
   - Delta sync to minimize bandwidth

3. **Privacy**
   - No third-party policy exposure
   - Holder can always see what's required/optional
   - Derived attributes prevent raw data disclosure

4. **Flexibility**
   - Multiple ranking strategies
   - Custom weights for organization-specific priorities
   - Optional fields default gracefully

5. **Security**
   - Authenticated sync endpoint
   - Bearer token authentication
   - Policy version tracking for audit trail

## Configuration Example

```python
{
    "name": "Government ID Verification - High Security",
    "credential_types": ["emrtd"],
    "required_claims": [
        {
            "claim_path": "credentialSubject.firstName",
            "constraints": {},
            "display_name": "First Name"
        },
        {
            "claim_path": "credentialSubject.lastName",
            "constraints": {},
            "display_name": "Last Name"
        },
        {
            "claim_path": "credentialSubject.dateOfBirth",
            "constraints": {"max_age": 18},
            "display_name": "Date of Birth"
        }
    ],
    "optional_claims": [
        {
            "claim_path": "credentialSubject.address",
            "constraints": {},
            "display_name": "Address"
        }
    ],
    "allowed_issuers": [
        "did:gov:usa:state-dept",
        "did:gov:usa:dmv"
    ],
    "derived_attribute_preferences": {
        "dateOfBirth": "age_over_18"
    },
    "require_trust_profile": true,
    "max_credential_age_days": 90,
    "credential_ranking_strategy": "CUSTOM",
    "credential_ranking_weights": {
        "freshness": 0.5,
        "trust_level": 0.4,
        "claims_count": 0.1
    }
}
```

## Future Enhancements

### Short Term
1. Add claim constraint validation (beyond just presence)
   - Example: age > 18, country in ["USA", "CAN"]
2. Implement credential expiration checks
3. Add policy versioning UI for administrators

### Medium Term
1. Policy template library for common use cases
2. A/B testing support for policy effectiveness
3. Analytics on policy compliance rates
4. Policy impact simulation before deployment

### Long Term
1. Machine learning-based anomaly detection in verification patterns
2. Federated policy learning across deployments
3. Automated policy recommendation based on verification history
4. Zero-knowledge proof integration for advanced privacy

## Files Modified/Created

### Backend (Python)
- ✅ `src/digital_identity/domain/entities.py`
- ✅ `src/digital_identity/domain/value_objects.py`
- ✅ `src/digital_identity/infrastructure/adapters/rest/schemas.py`
- ✅ `src/digital_identity/infrastructure/persistence/models.py`
- ✅ `src/digital_identity/infrastructure/adapters/rest/routers.py`
- ✅ `src/digital_identity/infrastructure/persistence/migrations/004_extend_presentation_policies.py`
- ✅ `tests/test_presentation_policies.py` (NEW)

### Rust Core (marty-verification)
- ✅ `marty-verification/src/policy/mod.rs` (NEW)
- ✅ `marty-verification/src/policy/types.rs` (NEW)
- ✅ `marty-verification/src/policy/claim_evaluator.rs` (NEW)
- ✅ `marty-verification/src/policy/freshness.rs` (NEW)
- ✅ `marty-verification/src/policy/issuer.rs` (NEW)
- ✅ `marty-verification/src/policy/disclosure.rs` (NEW)
- ✅ `marty-verification/src/policy/ranking.rs` (NEW)
- ✅ `marty-verification/src/lib.rs`
- ✅ `marty-verification/tests/policy_tests.rs` (NEW)

### Rust Sync (marty-sync)
- ✅ `marty-sync/src/policy.rs` (NEW)
- ✅ `marty-sync/src/lib.rs`
- ✅ `marty-sync/Cargo.toml`

### Rust Storage (marty-app-storage)
- ✅ `marty-app-storage/src/schema.rs`

### Flutter (marty-authenticator)
- ✅ `rust/src/api.rs`
- ✅ `rust/Cargo.toml`
- ✅ `lib/services/policy_service.dart` (NEW)
- ✅ `lib/widgets/policy_driven_disclosure_widget.dart` (NEW)
- ✅ `test/services/policy_service_test.dart` (NEW)

### Verifier (marty-verifier)
- ✅ `src-tauri/src/commands/verification.rs`
- ✅ `Cargo.toml`

## Deployment Checklist

### Backend Deployment
- [ ] Run database migration: `alembic upgrade head`
- [ ] Restart backend services
- [ ] Verify sync endpoint: `curl -H "Authorization: Bearer <token>" https://api.example.com/api/v1/identity/presentation-policies/sync`

### Mobile Wallet Deployment
- [ ] Build Flutter app with updated Rust bridge: `flutter pub run flutter_rust_bridge_codegen`
- [ ] Run tests: `flutter test`
- [ ] Build release: `flutter build apk/ios`
- [ ] Deploy to app stores

### Verifier App Deployment
- [ ] Build Tauri app: `cd marty-verifier && npm run tauri build`
- [ ] Test policy evaluation with cached policies
- [ ] Deploy to distribution channels

### Testing Verification
1. Create test policy via API
2. Sync policy to mobile wallet
3. Present credential to verifier
4. Verify policy constraints appear in verification warnings
5. Test with non-compliant credential (untrusted issuer, stale, etc.)

## Support & Documentation

### API Documentation
- OpenAPI spec: `/api/v1/docs`
- Sync endpoint authentication: Bearer token from OAuth2 flow

### Developer Resources
- Rust policy module docs: `cargo doc --open --package marty-verification`
- Flutter service docs: Dart docs in source code

### Troubleshooting

**Issue**: Policies not syncing to mobile wallet
- Check authentication token validity
- Verify network connectivity
- Check FlutterSecureStorage permissions

**Issue**: Policy violations not appearing in verifier
- Verify policies cached in SQLite: `SELECT * FROM presentation_policies;`
- Check deployment_profile_id matches
- Verify policy evaluation logs in Tauri console

**Issue**: UI not showing policy-driven disclosure
- Verify PolicyService initialized
- Check policy exists for credential type
- Verify background sync running

## Conclusion

Complete implementation of Presentation Policy support across all Marty platform components. The system now supports:

✅ Configurable presentation policies with rich constraint types  
✅ Authenticated policy distribution to authorized devices  
✅ Offline policy evaluation in Rust  
✅ Mobile wallet policy-driven disclosure UI  
✅ Verifier policy constraint checking  
✅ Comprehensive test coverage  
✅ Holder sovereignty with informed consent  
✅ Privacy-preserving architecture  

The implementation follows security and privacy best practices while maintaining flexibility for different organizational requirements.
