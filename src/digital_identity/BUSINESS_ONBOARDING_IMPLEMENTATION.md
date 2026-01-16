# Business-Focused Identity Onboarding Implementation

## Overview

Implemented a business-focused onboarding flow that abstracts technical complexity from non-technical users while empowering technical users with advanced options. Instead of asking users about ICAO/AAMVA/EUDI trust frameworks, the system asks about **use cases** ("What will you issue?") and **who accepts them** ("Who will verify these?"), then auto-generates appropriate trust profiles.

## Completed Implementation

### 1. UI Components ✅

#### [UseCaseStep.js](marty-ui/ui/src/components/onboarding/steps/UseCaseStep.js)
- **Purpose**: Business-friendly credential type selection
- **Question**: "What will you issue?"
- **Options**: Travel Documents, Driver's Licenses, EU Digital Credentials, Employee IDs, Student IDs, Access Badges
- **Features**:
  - Card-based multi-select interface
  - Business-friendly descriptions (no mention of ICAO/AAMVA)
  - Icons and recommended badges
  - Stores selections as `use_case_tags`

#### [AcceptanceStep.js](marty-ui/ui/src/components/onboarding/steps/AcceptanceStep.js)
- **Purpose**: Context refinement based on selected use cases
- **Questions**: 
  - "Who will accept these credentials?" → Determines trust registries
  - "Where do you operate?" → Sets jurisdiction defaults
- **Options**: Airports, Border Control, Law Enforcement, Age-Restricted Venues, Employers, etc.
- **Features**:
  - Dynamic options based on previous selections
  - Grouped jurisdiction selector (North America, Europe, Asia Pacific, Global)
  - Contextual relevance filtering

#### [AdvancedConfigStep.js](marty-ui/ui/src/components/onboarding/steps/AdvancedConfigStep.js)
- **Purpose**: Escape hatch for technical users
- **Features**:
  - Collapsed by default with "Advanced Configuration" toggle
  - Manual trust profile editor with framework selection (ICAO/AAMVA/EUDI/Custom)
  - Framework-specific configuration fields (PKD URLs, trust anchors, certificates)
  - Add/delete/edit multiple profiles
  - Sets `manually_configured: true` flag

#### [OnboardingPage.js](marty-ui/ui/src/components/OnboardingPage.js) Updates
- **Integrated new steps** into vendor onboarding flow:
  1. Role Selection
  2. Create Organization
  3. **Use Cases** (new)
  4. **Acceptance Context** (new)
  5. Trust Profile (legacy, for advanced users)
  6. Verifier Identity
  7. Issuer Identity
  8. Trust Sources
  9. Review
  10. Complete
- **Added state management** for:
  - `selectedUseCases`
  - `selectedAcceptance`
  - `manualProfiles`
- **Updated handlers** with validation logic
- **"Set up later"** link on use case step for skipping trust setup

### 2. Backend Services ✅

#### [profile_generator.py](src/digital_identity/application/services/profile_generator.py)
- **Purpose**: Auto-mapping service that converts business selections to trust profiles
- **Features**:
  - `generate_profiles()` - Main generation method
  - Use case → profile type mapping (Travel Documents → ICAO, Driver's Licenses → AAMVA, etc.)
  - Special handling for multi-profile use cases (Travel Documents creates both Passports-ICAO and DTC-ICAO)
  - Jurisdiction-specific configuration (state codes for AAMVA, EU member states for EUDI)
  - Compliance status calculation with certificate expiry and trust list age checks
  - Manual profile extraction for advanced mode
- **Supported Mappings**:
  ```python
  travel_documents → ICAO (Passports, DTC)
  driver_licenses → AAMVA (mDL)
  eu_credentials → EUDI (EU Wallet)
  employee_ids → CUSTOM (X.509)
  student_ids → CUSTOM (X.509)
  access_badges → CUSTOM (X.509)
  ```

### 3. Database Schema ✅

#### [Migration 002](src/digital_identity/infrastructure/persistence/migrations/002_add_organization_context.py)
- **New Columns**:
  - `organization_id` (UUID FK → organizations, CASCADE delete)
  - `display_name` (VARCHAR 255, NOT NULL) - Business-friendly name
  - `use_case_tags` (JSONB) - Business context tracking
  - `auto_generated` (BOOLEAN) - Wizard vs manual flag
  - `compliance_status` (VARCHAR 50) - COMPLIANT | NEEDS_ATTENTION | SETUP_REQUIRED
  - `manually_configured` (BOOLEAN) - Advanced mode flag

- **Constraints**:
  - Composite unique: `(organization_id, name)` - Unique names per org
  - Partial unique index: `(organization_id, profile_type) WHERE enabled AND profile_type != 'CUSTOM'` - One active profile per framework per org
  - Check constraint: compliance_status IN ('COMPLIANT', 'NEEDS_ATTENTION', 'SETUP_REQUIRED')

- **Indexes**:
  - `idx_trust_profile_organization_id` - Query performance
  - `idx_trust_profile_compliance_status` - Dashboard queries
  - `idx_trust_profile_use_case_tags` (GIN) - Tag filtering

#### [TrustProfile Entity](src/digital_identity/domain/entities.py) Updates
- Added organization scoping fields
- Updated docstring with business context explanation
- Compliance status integration
- Use case tags for business intent tracking

#### [TrustProfileModel](src/digital_identity/infrastructure/persistence/models.py) Updates
- Added all new columns with proper types
- Foreign key to organizations table
- JSONB columns for flexible data
- Table-level constraint documentation

## Design Decisions

### 1. Compliance Status Over Technical Details ✅
**Decision**: Show "✓ Travel Documents - Compliant" instead of "ICAO PKD: Connected"
**Rationale**: Non-technical users need to know if they're in compliance, not the underlying technical framework

### 2. Display Name Separate from Technical Name ✅
**Decision**: Store both `name` ("Passports-ICAO-US") and `display_name` ("Travel Documents")
**Rationale**: 
- Display name for UI (business-friendly)
- Technical name for internal references and uniqueness
- Visible names in simplified form, technical details in "Advanced" section only

### 3. Progressive Disclosure via Advanced Toggle ✅
**Decision**: Hide technical configuration behind collapsible "Advanced Configuration" section
**Rationale**:
- Default experience is business-focused wizard
- Technical users can access full control without friction
- Doesn't overwhelm non-technical users with ICAO/AAMVA jargon

### 4. Multi-Organization Scoping ✅
**Decision**: Add `organization_id` FK with composite unique constraints
**Rationale**:
- Real-world orgs issue multiple credential types (DMV: both mDL and passport-like DTC)
- Each org needs isolated trust profiles
- Allows org-scoped naming: "Travel Documents" per org without global conflicts

## User Experience Flow

### Non-Technical User Path
1. **Role Selection**: Choose "Vendor / Organization"
2. **Create Organization**: Enter org details
3. **Use Cases**: Select "Travel Documents" and "Driver's Licenses" (multi-select cards)
4. **Acceptance**: Pick "Border Control" + "Law Enforcement", jurisdiction "US"
5. **Auto-Generation**: System creates:
   - "Travel-Documents-ICAO-US" profile (display: "Travel Documents")
   - "DTC-ICAO-US" profile (display: "Digital Travel Credentials")
   - "Driver-Licenses-AAMVA-US" profile (display: "Driver's Licenses")
6. **Skip Advanced**: Continue without seeing ICAO/AAMVA details
7. **Completion**: Dashboard shows compliance badges

### Technical User Path
1-4. Same as above
5. **Advanced Toggle**: Click "Advanced Configuration"
6. **Manual Configuration**: 
   - See auto-generated profiles
   - Edit PKD URLs, trust anchors
   - Add custom X.509 profile with uploaded certificates
7. **Advanced Options**: Configure verifier/issuer identity manually
8. **Completion**: Full technical control maintained

## Next Steps (Not Implemented)

### 6. Compliance Indicators in VendorDashboard
**Status**: ⏳ Pending
**Requirements**:
- Badge per use case with status colors (✓ green, ⚠ amber, ✗ red)
- Actionable next steps on click
- Technical details in expandable "Advanced" section
- Compliance calculation logic (certificate expiry checks, trust list freshness)

## Testing Recommendations

1. **UI Component Tests**:
   - Test use case selection state
   - Verify acceptance filtering based on use cases
   - Confirm advanced toggle shows/hides correctly
   - Validate manual profile CRUD operations

2. **Backend Service Tests**:
   - Test profile generation for each use case
   - Verify multi-profile creation (Travel Documents → 2 profiles)
   - Test jurisdiction-specific configuration
   - Validate compliance status calculation

3. **Integration Tests**:
   - End-to-end onboarding flow
   - Verify profiles saved with correct organization_id
   - Test unique constraint enforcement
   - Confirm API receives use_case_tags and manual_profiles

4. **Migration Tests**:
   - Test upgrade/downgrade on sample database
   - Verify constraints created correctly
   - Test with existing data (if any)

## Files Created/Modified

### Created
- `marty-ui/ui/src/components/onboarding/steps/UseCaseStep.js`
- `marty-ui/ui/src/components/onboarding/steps/AcceptanceStep.js`
- `marty-ui/ui/src/components/onboarding/steps/AdvancedConfigStep.js`
- `src/digital_identity/application/services/profile_generator.py`
- `src/digital_identity/infrastructure/persistence/migrations/002_add_organization_context.py`

### Modified
- `marty-ui/ui/src/components/OnboardingPage.js` - Integrated new steps, added state management
- `src/digital_identity/domain/entities.py` - Added organization fields to TrustProfile
- `src/digital_identity/infrastructure/persistence/models.py` - Updated TrustProfileModel schema

## Architecture Alignment

This implementation aligns with the hexagonal architecture already in place:
- **Domain Layer**: Updated entities with new business concepts
- **Application Layer**: New service for profile generation logic
- **Infrastructure Layer**: Migration and model updates for persistence
- **UI Layer**: New React components following existing patterns
- **API Layer**: Ready to receive new fields in existing endpoints

The business-focused approach maintains separation of concerns while making the system accessible to non-technical users and powerful for technical users.
