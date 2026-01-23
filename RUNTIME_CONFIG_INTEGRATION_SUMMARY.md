# Runtime Configuration Integration - Summary

This document summarizes the integration of deployment profile runtime configuration into the verifier application.

## What Was Done

### 1. Tauri Commands Registration
- **File**: `marty-verifier/src-tauri/src/commands/mod.rs`
- **Changes**: Added `pub mod profile_sync;` to expose profile sync commands

### 2. Command Handler Registration
- **File**: `marty-verifier/src-tauri/src/main.rs`
- **Changes**: 
  - Added `commands::profile_sync::sync_device_config` to invoke_handler
  - Added `commands::profile_sync::get_runtime_config` to invoke_handler
  - Added startup sync that calls `sync_device_config_impl()` on app initialization

### 3. Profile Sync Command Implementation
- **File**: `marty-verifier/src-tauri/src/commands/profile_sync.rs`
- **Functions**:
  - `sync_device_config()`: Tauri command wrapper
  - `sync_device_config_impl()`: Shared implementation for both command and startup sync
  - `get_runtime_config()`: Returns current runtime config snapshot as JSON
  - `store_deployment_profile()`: Persists profile to SQLite with JSON serialization
  - `store_lane()`: Persists lane to SQLite with device_ids and metadata as JSON
  - `store_device_config()`: Updates device assignment record

## Integration Flow

### Application Startup
1. **App initialization** (`main.rs`)
   - AppState created with RuntimeConfig instance
   - Storage and RuntimeConfig cloned for startup sync

2. **Background sync task spawned**
   - Calls `sync_device_config_impl(storage, runtime_config)`
   - Fetches device config from backend API via ProfileSyncProvider
   - Stores profile/lane in local SQLite database
   - Applies profile and lane to RuntimeConfig state
   - Logs sync status (success/failure)

3. **Configuration applied**
   - Network mode available via `RuntimeConfig::get_network_mode()`
   - UX config available via `RuntimeConfig::get_ux_config()`
   - Active policy ID selected with priority: lane > explicit > profile

### Manual Sync (via Tauri command)
- Frontend can call `syncDeviceConfig(device_id)` 
- Command fetches fresh config from API
- Updates local database and runtime state
- Returns `DeviceConfigSyncResult` with sync status

### Config Retrieval (via Tauri command)
- Frontend can call `getRuntimeConfig()`
- Returns snapshot of current runtime configuration as JSON
- Includes device_id, profile, lane, active_policy_id

## Environment Configuration

The startup sync uses environment variables for initial configuration:
- `MARTY_API_ENDPOINT`: Backend API URL (default: `http://localhost:8000`)
- `MARTY_LICENSE_JWT`: License token for API authentication

**TODO**: Replace env vars with proper config/license integration once available in startup context.

## Database Schema

### deployment_profiles table
```sql
CREATE TABLE deployment_profiles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    site_id TEXT NOT NULL,
    network_mode TEXT NOT NULL,
    key_access_mode TEXT,
    ux_config TEXT, -- JSON
    update_policy TEXT, -- JSON
    offline_cache_ttl_hours INTEGER,
    biometric_required INTEGER,
    audit_all_events INTEGER,
    synced_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

### lanes table
```sql
CREATE TABLE lanes (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    deployment_profile_id TEXT NOT NULL,
    default_policy_id TEXT,
    device_ids TEXT, -- JSON array
    metadata TEXT, -- JSON object
    synced_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (deployment_profile_id) REFERENCES deployment_profiles(id)
);
```

### device_config table
```sql
CREATE TABLE device_config (
    id TEXT PRIMARY KEY DEFAULT 'current',
    device_id TEXT NOT NULL,
    deployment_profile_id TEXT,
    lane_id TEXT,
    assigned_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (deployment_profile_id) REFERENCES deployment_profiles(id),
    FOREIGN KEY (lane_id) REFERENCES lanes(id)
);
```

## API Endpoints Used

### Backend API
- **GET** `/v1/devices/{device_id}/config`
  - Returns device assignment with profile, lane, and policies
  - Response: `DeviceConfigResponse { device_id, deployment_profile?, lane?, presentation_policies, issuance_policies }`

## RuntimeConfig API

### State Management
- `RuntimeConfig::new()` - Create new instance
- `set_device_id(device_id)` - Set device ID
- `get_device_id()` - Get current device ID
- `apply_deployment_profile(profile)` - Apply profile settings
- `apply_lane(lane)` - Apply lane settings with policy override
- `snapshot()` - Get current config as `RuntimeConfigSnapshot`

### Configuration Retrieval
- `get_network_mode()` - Returns `NetworkMode` (Online/Offline/AirGapped)
- `get_ux_config()` - Returns optional `UXConfig` with theme, locale, signage_text
- `get_active_policy_id()` - Returns policy ID with priority: lane > explicit > profile

## Next Steps

1. **Update Manager Integration**
   - Read `update_policy` from synced profile
   - Check `should_apply_update()` before applying updates
   - Respect `version_pinned` setting
   - Log rollout decisions

2. **UI Integration**
   - Call `getRuntimeConfig()` on app load
   - Apply `ux_config.theme` to UI
   - Display `ux_config.signage_text` based on locale
   - Use `active_policy_id` as default in policy selection

3. **Network Mode Integration**
   - Apply `network_mode` to sync engine behavior
   - Disable online features in Offline mode
   - Block all network in AirGapped mode

4. **Admin UI Enhancement**
   - Create profile management interface
   - Add lane CRUD operations
   - Build device assignment UI
   - Profile preview and testing

## Testing Checklist

- [ ] Startup sync executes without errors
- [ ] Profile and lane stored in database correctly
- [ ] RuntimeConfig state updated after sync
- [ ] Manual sync command works via Tauri
- [ ] Config snapshot returns correct JSON
- [ ] Network mode applied to sync behavior
- [ ] UX config applied to UI theme
- [ ] Active policy ID selected correctly
- [ ] Update rollout percentage calculation works
- [ ] Offline cache TTL respected

## Files Modified

### Verifier (Rust/Tauri)
- `src-tauri/src/commands/mod.rs` - Added profile_sync module
- `src-tauri/src/commands/profile_sync.rs` - Created sync commands and storage helpers
- `src-tauri/src/main.rs` - Registered commands, added startup sync
- `src-tauri/src/runtime_config.rs` - Already had device_id methods
- `src-tauri/src/state.rs` - Already had runtime_config field (added previously)

### Documentation
- `RUNTIME_CONFIG_INTEGRATION_SUMMARY.md` - This file
