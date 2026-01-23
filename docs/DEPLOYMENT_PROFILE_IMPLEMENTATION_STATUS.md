# Deployment Profile & Lane Implementation Status

## ✅ Completed Implementation

### Backend (Python/FastAPI)

#### 1. Domain Layer
- ✅ **Lane Entity** ([entities.py](../src/digital_identity/domain/entities.py))
  - Created Lane entity with device assignment methods
  - Updated DeploymentProfile to include `lanes: list[Lane]` field
  - Lane hierarchy: Organization → Site → DeploymentProfile → Lane(s) → Device(s)

- ✅ **Value Objects** ([value_objects.py](../src/digital_identity/domain/value_objects.py))
  - Added `signage_text: dict[str, str] | None` to UXConfig for multilingual signage
  - Added `rollout_ring: str | None` to UpdatePolicy for named rollout rings

- ✅ **Conceptual Model** ([Digital_Identity_model.md](Digital_Identity_model.md))
  - Updated to reflect Lane abstraction and hierarchy

#### 2. Application Layer
- ✅ **Lane Service** ([lane_service.py](../src/digital_identity/application/services/lane_service.py))
  - Full CRUD operations for lanes
  - Device assignment/unassignment
  - Event publishing on lane changes

- ✅ **Deployment Profile Service**
  - Removed 1:1 site_id uniqueness constraint to allow multiple profiles per site

#### 3. API Layer
- ✅ **Lane Schemas** ([schemas.py](../src/digital_identity/infrastructure/adapters/rest/schemas.py))
  - LaneCreate, LaneUpdate, LaneResponse, LaneDeviceAssignment
  - Updated UXConfigSchema with signage_text
  - Updated UpdatePolicySchema with rollout_ring

- ✅ **Lane Routes** ([routers.py](../src/digital_identity/infrastructure/adapters/rest/routers.py))
  - POST `/v1/identity/deployment-profiles/{profile_id}/lanes` - Create lane
  - GET `/v1/identity/deployment-profiles/{profile_id}/lanes` - List lanes
  - GET `/v1/identity/deployment-profiles/{profile_id}/lanes/{lane_id}` - Get lane
  - PATCH `/v1/identity/deployment-profiles/{profile_id}/lanes/{lane_id}` - Update lane
  - DELETE `/v1/identity/deployment-profiles/{profile_id}/lanes/{lane_id}` - Delete lane
  - POST `/v1/identity/deployment-profiles/{profile_id}/lanes/{lane_id}/assign-devices` - Assign devices

- ✅ **Device Config Endpoint** ([device_router.py](../src/digital_identity/infrastructure/adapters/rest/device_router.py))
  - GET `/v1/devices/{device_id}/config` - Fetch deployment profile, lane, and policies for a device

- ✅ **Dependencies** ([dependencies.py](../src/digital_identity/infrastructure/adapters/rest/dependencies.py))
  - Added `get_lane_service()` dependency injection

- ✅ **Test Configuration**
  - Updated test fixtures to include lane_router and device_router

---

### Verifier (Rust/Tauri)

#### 1. Schema Updates
- ✅ **Database Schema** ([schema.rs](../../marty-verifier/crates/marty-app-storage/src/schema.rs))
  - Added `deployment_profiles` table with network_mode, ux_config, update_policy
  - Added `lanes` table with FK to deployment_profiles
  - Added `device_config` table for current device assignment
  - Schema version bumped to 4

#### 2. Sync Provider
- ✅ **Profile Sync Provider** ([profile_sync.rs](../../marty-verifier/crates/marty-sync/src/profile_sync.rs))
  - `ProfileSyncProvider` with methods:
    - `fetch_device_config()` - Get complete device config from backend
    - `fetch_deployment_profile()` - Get profile by ID
    - `fetch_lanes()` - Get lanes for a profile
    - `should_apply_update()` - Rollout percentage check using device_id hash
  - Data structures: `DeploymentProfile`, `Lane`, `DeviceConfig`, `NetworkMode`, `UXConfig`, `UpdatePolicy`

#### 3. Policy Sync Updates
- ✅ **Policy Filtering** ([policy.rs](../../marty-verifier/crates/marty-sync/src/policy.rs))
  - Added `fetch_for_profile()` method to filter policies by deployment_profile_id
  - Internal `fetch_with_filter()` method supports optional profile filtering

#### 4. Runtime Configuration
- ✅ **Runtime Config Module** ([runtime_config.rs](../../marty-verifier/src-tauri/src/runtime_config.rs))
  - `RuntimeConfig` state manager with async read/write access
  - Methods:
    - `apply_deployment_profile()` - Apply profile settings
    - `apply_lane()` - Apply lane configuration
    - `get_network_mode()` - Get current network mode
    - `get_ux_config()` - Get UX settings
    - `get_active_policy_id()` - Priority: lane default > profile default
    - `get_offline_cache_ttl_hours()` - Get cache TTL
    - `is_biometric_required()` - Check biometric setting
    - `should_audit_all_events()` - Check audit setting
    - `snapshot()` - Get serializable config snapshot
  - Unit tests included

---

### Admin UI (React/TypeScript)

#### 1. Profile Management Component
- ✅ **DeploymentProfileManager** ([DeploymentProfileManager.tsx](../../marty-verifier/ui/src/components/DeploymentProfileManager.tsx))
  - List all deployment profiles with site_id and network_mode badges
  - Profile detail view with configuration sections:
    - Network Configuration (mode, cache TTL)
    - UX Configuration (language, theme, accessibility, signage text)
    - Update Policy (auto-update, channel, rollout percentage, ring)
    - Lanes list with device count and policy override indicators
  - Real-time profile and lane fetching from API
  - Error handling and loading states

- ✅ **Styling** ([DeploymentProfileManager.css](../../marty-verifier/ui/src/components/DeploymentProfileManager.css))
  - Responsive grid layout (profile list + details)
  - Visual hierarchy with sections and badges
  - Hover states and selection highlighting

- ✅ **Component Export** ([index.ts](../../marty-verifier/ui/src/components/index.ts))
  - Exported DeploymentProfileManager for use in application

---

## 📋 Remaining Integration Work

### 1. Verifier Runtime Integration
**Status:** Core modules implemented, integration pending

**Tasks:**
- [ ] Wire `RuntimeConfig` into main application state
- [ ] Call `ProfileSyncProvider::fetch_device_config()` on startup
- [ ] Store synced profiles/lanes in local database (schema.rs tables)
- [ ] Apply `network_mode` to sync engine behavior:
  - Online: Real-time API calls
  - Offline: Use cached data only
  - Hybrid: API with graceful fallback
- [ ] Apply `ux_config` to UI:
  - Set language/locale
  - Apply theme
  - Show/hide operator mode controls
  - Display signage_text based on selected language
- [ ] Use `active_policy_id` for default policy selection in verification flow
- [ ] Honor `offline_cache_ttl_hours` for trust anchor expiration

### 2. Update Manager Integration
**Status:** Rollout check implemented, integration pending

**Tasks:**
- [ ] Read `update_policy` from synced profile
- [ ] Check `should_apply_update(device_id, rollout_percentage)` before updates
- [ ] Respect `version_pinned` to block specific versions
- [ ] Log rollout decisions to audit trail

### 3. Admin UI Enhancement
**Status:** View-only component implemented, full CRUD pending

**Tasks:**
- [ ] Add "Create Profile" form with all configuration fields
- [ ] Add "Edit Profile" form with validation
- [ ] Add "Delete Profile" confirmation dialog
- [ ] Implement Lane CRUD UI:
  - Create lane modal
  - Edit lane inline
  - Delete lane with device reassignment warning
- [ ] Device assignment interface:
  - List all devices (fetch from API or local registry)
  - Drag-and-drop or multi-select assignment to lanes
  - Bulk operations
- [ ] Profile preview/test mode to simulate verifier UI with config

---

## 🧪 Testing Requirements
- ✅ **Lane Entity** ([entities.py](../src/digital_identity/domain/entities.py))
  - Created Lane entity with device assignment methods
  - Updated DeploymentProfile to include `lanes: list[Lane]` field
  - Lane hierarchy: Organization → Site → DeploymentProfile → Lane(s) → Device(s)

- ✅ **Value Objects** ([value_objects.py](../src/digital_identity/domain/value_objects.py))
  - Added `signage_text: dict[str, str] | None` to UXConfig for multilingual signage
  - Added `rollout_ring: str | None` to UpdatePolicy for named rollout rings

- ✅ **Conceptual Model** ([Digital_Identity_model.md](Digital_Identity_model.md))
  - Updated to reflect Lane abstraction and hierarchy

### 2. Application Layer
- ✅ **Lane Service** ([lane_service.py](../src/digital_identity/application/services/lane_service.py))
  - Full CRUD operations for lanes
  - Device assignment/unassignment
  - Event publishing on lane changes

- ✅ **Deployment Profile Service**
  - Removed 1:1 site_id uniqueness constraint to allow multiple profiles per site

### 3. API Layer
- ✅ **Lane Schemas** ([schemas.py](../src/digital_identity/infrastructure/adapters/rest/schemas.py))
  - LaneCreate, LaneUpdate, LaneResponse, LaneDeviceAssignment
  - Updated UXConfigSchema with signage_text
  - Updated UpdatePolicySchema with rollout_ring

- ✅ **Lane Routes** ([routers.py](../src/digital_identity/infrastructure/adapters/rest/routers.py))
  - POST `/v1/identity/deployment-profiles/{profile_id}/lanes` - Create lane
  - GET `/v1/identity/deployment-profiles/{profile_id}/lanes` - List lanes
  - GET `/v1/identity/deployment-profiles/{profile_id}/lanes/{lane_id}` - Get lane
  - PATCH `/v1/identity/deployment-profiles/{profile_id}/lanes/{lane_id}` - Update lane
  - DELETE `/v1/identity/deployment-profiles/{profile_id}/lanes/{lane_id}` - Delete lane
  - POST `/v1/identity/deployment-profiles/{profile_id}/lanes/{lane_id}/assign-devices` - Assign devices

- ✅ **Dependencies** ([dependencies.py](../src/digital_identity/infrastructure/adapters/rest/dependencies.py))
  - Added `get_lane_service()` dependency injection

- ✅ **Test Configuration**
  - Updated test fixtures to include lane_router

---

## Remaining Verifier Implementation

### 1. Schema Updates
**File:** `marty-verifier/crates/marty-app-storage/src/schema.rs`

**Current state:** 
- `presentation_policies` table has `deployment_profile_id` column
- No deployment_profile or lane tables

**Needed:**
```rust
-- Add deployment profiles cache
CREATE TABLE IF NOT EXISTS deployment_profiles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    site_id TEXT,
    network_mode TEXT NOT NULL, -- 'online', 'offline', 'hybrid'
    ux_config TEXT NOT NULL, -- JSON
    offline_cache_ttl_hours INTEGER NOT NULL DEFAULT 24,
    synced_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Add lanes cache
CREATE TABLE IF NOT EXISTS lanes (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    deployment_profile_id TEXT NOT NULL,
    default_policy_id TEXT,
    device_ids TEXT NOT NULL, -- JSON array of device IDs
    metadata TEXT, -- JSON
    synced_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (deployment_profile_id) REFERENCES deployment_profiles(id)
);

CREATE INDEX IF NOT EXISTS idx_lanes_deployment_profile 
    ON lanes(deployment_profile_id);

-- Add device_config storage
CREATE TABLE IF NOT EXISTS device_config (
    id TEXT PRIMARY KEY DEFAULT 'current',
    device_id TEXT,
    lane_id TEXT,
    deployment_profile_id TEXT,
    assigned_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

### 2. Sync Provider Extension
**File:** `marty-verifier/crates/marty-sync/src/profile_sync.rs` (new file)

**Purpose:** Fetch deployment profile and lane configuration from backend

```rust
pub struct ProfileSyncProvider {
    client: Client,
    endpoint: String,
    license_jwt: String,
}

impl ProfileSyncProvider {
    pub async fn fetch_device_config(
        &self,
        device_id: &str
    ) -> Result<DeviceConfig, SyncError> {
        // GET /api/v1/devices/{device_id}/config
        // Returns: deployment_profile + lane + policies
    }
}

pub struct DeviceConfig {
    pub device_id: String,
    pub deployment_profile: Option<DeploymentProfile>,
    pub lane: Option<Lane>,
    pub network_mode: NetworkMode,
    pub ux_config: UXConfig,
    pub offline_cache_ttl_hours: u32,
}
```

### 3. Policy Sync Update
**File:** `marty-verifier/crates/marty-sync/src/policy.rs`

**Current:** Fetches all policies
**Needed:** Filter policies by deployment_profile_id during sync

```rust
pub async fn fetch_for_profile(
    &self,
    deployment_profile_id: &str
) -> Result<Vec<PresentationPolicy>, SyncError> {
    let url = format!(
        "{}/api/v1/identity/presentation-policies/sync?deployment_profile_id={}",
        self.endpoint, deployment_profile_id
    );
    // ... rest of implementation
}
```

### 4. Runtime Configuration
**File:** `marty-verifier/src-tauri/src/state.rs` or config module

**Needed:** Apply deployment profile settings at runtime
- Read `network_mode` from synced profile to control online/offline behavior
- Apply `ux_config` (language, theme, accessibility, signage_text) to UI
- Use lane's `default_policy_id` for verification policy selection
- Honor `offline_cache_ttl_hours` for trust anchor caching

### 5. Update Logic
**File:** `marty-verifier/crates/marty-license/src/update.rs` or update module

**Current:** Uses license-gated update channels
**Needed:** Check rollout percentage before applying updates

```rust
fn should_apply_update(
    device_id: &str,
    rollout_percentage: u8
) -> bool {
    use std::collections::hash_map::DefaultHasher;
    use std::hash::{Hash, Hasher};
    
    let mut hasher = DefaultHasher::new();
    device_id.hash(&mut hasher);
    let hash = hasher.finish();
    
    (hash % 100) < (rollout_percentage as u64)
}
```

---

## Remaining UI Implementation

### Admin UI for Deployment Profiles & Lanes
**Location:** `marty-verifier/ui/` (or admin dashboard)

**Components Needed:**

1. **DeploymentProfileList.tsx/dart**
   - List all deployment profiles
   - Filter by site_id, network_mode
   - Actions: Create, Edit, Delete

2. **DeploymentProfileForm.tsx/dart**
   - Form fields:
     - Name, Site ID, Description
     - Network Mode selector (online/offline/hybrid)
     - UX Config:
       - Language selector
       - Theme selector
       - Signage text (multi-language key-value editor)
       - Operator mode toggle
       - Accessibility toggle
     - Update Policy:
       - Auto-update toggle
       - Update channel selector
       - Rollout percentage slider (0-100)
       - Rollout ring input
     - Offline cache TTL
     - Key access mode selector

3. **LaneManager.tsx/dart**
   - Nested within deployment profile detail view
   - List lanes for the profile
   - Add/Edit/Delete lanes
   - Assign devices to lanes via drag-and-drop or multi-select

4. **DeviceAssignment.tsx/dart**
   - View all devices
   - Show current lane assignments
   - Bulk assign/reassign devices to lanes

5. **ProfilePreview.tsx/dart**
   - Preview how UX config affects verifier UI
   - Test signage text display in different languages

---

## Testing Requirements

### Backend Tests
- [ ] Lane CRUD integration tests
- [ ] Device assignment tests
- [ ] Profile with multiple lanes tests
- [ ] Site with multiple profiles tests

### Verifier Tests
- [ ] Profile sync tests
- [ ] Lane assignment application tests
- [ ] Network mode switching tests
- [ ] UX config application tests
- [ ] Rollout percentage calculation tests

### E2E Tests
- [ ] Create profile → create lane → assign device → verify sync
- [ ] Update profile UX config → verify applied on device
- [ ] Multi-lane scenario with different policies per lane

---

## Migration Strategy (Not Needed)
Per user request, no database migrations are required. The backend schema is designed to be backwards-compatible, and the verifier will create tables on first run with the new schema.

---

## Deployment Checklist

### Backend Deployment
- [x] Deploy updated entities, services, and API routes
- [x] Verify API endpoints are accessible
- [ ] Create sample deployment profiles for testing

### Verifier Deployment
- [ ] Update schema.rs with new tables
- [ ] Implement profile_sync.rs
- [ ] Update policy sync to use deployment_profile_id
- [ ] Implement runtime config application
- [ ] Test offline behavior with cached profiles
- [ ] Update documentation

### UI Deployment
- [ ] Build admin UI components
- [ ] Integrate with backend API
- [ ] User acceptance testing
- [ ] Operator training materials

---

## Next Steps

1. **Immediate:** Implement verifier schema updates and sync provider
2. **Short-term:** Build admin UI for profile/lane management
3. **Medium-term:** Production testing with real devices
4. **Long-term:** Telemetry and monitoring for profile usage

---

## API Usage Examples

### Create a Deployment Profile
```bash
POST /v1/identity/deployment-profiles
{
  "name": "Airport Terminal 1",
  "site_id": "YYZ-T1",
  "network_mode": "hybrid",
  "ux_config": {
    "language": "en",
    "theme": "airport",
    "signage_text": {
      "en": "Please present your ID",
      "fr": "Veuillez présenter votre pièce d'identité"
    },
    "accessibility_enabled": true
  },
  "update_policy": {
    "auto_update": true,
    "update_channel": "stable",
    "rollout_percentage": 25,
    "rollout_ring": "canary"
  }
}
```

### Create a Lane
```bash
POST /v1/identity/deployment-profiles/{profile_id}/lanes
{
  "name": "Gate 12",
  "default_policy_id": "policy-gate-priority",
  "metadata": {
    "zone": "international",
    "capacity": 4
  }
}
```

### Assign Devices to Lane
```bash
POST /v1/identity/deployment-profiles/{profile_id}/lanes/{lane_id}/assign-devices
{
  "device_ids": ["device-001", "device-002", "device-003"]
}
```

### Device Sync Endpoint (to be implemented)
```bash
GET /v1/devices/{device_id}/config
Authorization: Bearer <license_jwt>

Response:
{
  "device_id": "device-001",
  "deployment_profile": {
    "id": "...",
    "name": "Airport Terminal 1",
    "network_mode": "hybrid",
    "ux_config": { ... },
    "offline_cache_ttl_hours": 24
  },
  "lane": {
    "id": "...",
    "name": "Gate 12",
    "default_policy_id": "policy-gate-priority"
  },
  "policies": [ ... ]
}
```
