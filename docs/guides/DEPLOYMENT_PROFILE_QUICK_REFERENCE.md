# Deployment Profile Quick Reference

Quick reference for working with deployment profiles across the stack.

## Backend API Endpoints

### Profiles
```bash
# List all profiles
GET /v1/identity/deployment-profiles

# Create profile
POST /v1/identity/deployment-profiles
{
  "name": "Main Lobby",
  "site_id": "site-123",
  "network_mode": "online",
  "ux_config": {"theme": "light", "locale": "en"},
  "update_policy": {"rollout_percentage": 100},
  "offline_cache_ttl_hours": 24,
  "biometric_required": false,
  "audit_all_events": true
}

# Get profile
GET /v1/identity/deployment-profiles/{profile_id}

# Update profile
PUT /v1/identity/deployment-profiles/{profile_id}

# Delete profile
DELETE /v1/identity/deployment-profiles/{profile_id}
```

### Lanes
```bash
# List lanes for profile
GET /v1/identity/deployment-profiles/{profile_id}/lanes

# Create lane
POST /v1/identity/deployment-profiles/{profile_id}/lanes
{
  "name": "VIP Lane",
  "default_policy_id": "policy-456",
  "metadata": {"zone": "vip"}
}

# Get lane
GET /v1/identity/deployment-profiles/{profile_id}/lanes/{lane_id}

# Update lane
PUT /v1/identity/deployment-profiles/{profile_id}/lanes/{lane_id}

# Delete lane
DELETE /v1/identity/deployment-profiles/{profile_id}/lanes/{lane_id}

# Assign devices to lane
POST /v1/identity/lanes/{lane_id}/devices
{
  "device_ids": ["dev-001", "dev-002"]
}
```

### Device Config
```bash
# Get device configuration
GET /v1/devices/{device_id}/config
```

## Verifier Tauri Commands

```typescript
// Sync device configuration from backend
interface DeviceConfigSyncResult {
  device_id: string;
  profile_synced: boolean;
  lane_synced: boolean;
  profile_id?: string;
  lane_id?: string;
}

await invoke<DeviceConfigSyncResult>('sync_device_config', {
  deviceId: 'dev-001'
});

// Get current runtime configuration
interface RuntimeConfigSnapshot {
  device_id?: string;
  deployment_profile?: DeploymentProfile;
  lane?: Lane;
  active_policy_id?: string;
}

const config = await invoke<RuntimeConfigSnapshot>('get_runtime_config');
```

## Python Service Usage

```python
from domain.services.deployment_profile_service import DeploymentProfileService
from domain.services.lane_service import LaneService

# Create deployment profile
profile = await deployment_profile_service.create(
    name="Airport Security",
    site_id="site-456",
    network_mode=NetworkMode.OFFLINE,
    ux_config=UXConfig(theme="dark", locale="en"),
    update_policy=UpdatePolicy(rollout_percentage=10),
    offline_cache_ttl_hours=48,
    biometric_required=True,
    audit_all_events=True,
)

# Create lane
lane = await lane_service.create(
    name="Express Lane",
    deployment_profile_id=profile.id,
    default_policy_id="policy-789",
)

# Assign devices to lane
await lane_service.assign_devices(
    lane_id=lane.id,
    device_ids=["dev-003", "dev-004", "dev-005"],
)
```

## Rust RuntimeConfig Usage

```rust
use crate::runtime_config::RuntimeConfig;

// Create runtime config
let runtime_config = RuntimeConfig::new();

// Set device ID
runtime_config.set_device_id("dev-001".to_string()).await;

// Apply deployment profile
runtime_config.apply_deployment_profile(profile).await;

// Apply lane (overrides profile policy)
runtime_config.apply_lane(lane).await;

// Get network mode
let network_mode = runtime_config.get_network_mode().await;
match network_mode {
    NetworkMode::Online => { /* allow network */ },
    NetworkMode::Offline => { /* cache only */ },
    NetworkMode::AirGapped => { /* no network */ },
}

// Get UX config
if let Some(ux_config) = runtime_config.get_ux_config().await {
    apply_theme(ux_config.theme);
    set_locale(ux_config.locale);
}

// Get active policy ID (lane > explicit > profile)
let policy_id = runtime_config.get_active_policy_id().await;

// Get full snapshot
let snapshot = runtime_config.snapshot().await;
```

## React UI Integration

```typescript
import React, { useEffect, useState } from 'react';
import { invoke } from '@tauri-apps/api/tauri';

function DeviceConfigStatus() {
  const [config, setConfig] = useState(null);

  useEffect(() => {
    // Load config on mount
    invoke('get_runtime_config').then(setConfig);
  }, []);

  if (!config) return <div>Loading...</div>;

  return (
    <div>
      <h2>Device Configuration</h2>
      <p>Device ID: {config.device_id}</p>
      {config.deployment_profile && (
        <>
          <p>Profile: {config.deployment_profile.name}</p>
          <p>Network: {config.deployment_profile.network_mode}</p>
          <p>Theme: {config.deployment_profile.ux_config.theme}</p>
        </>
      )}
      {config.lane && (
        <p>Lane: {config.lane.name}</p>
      )}
      {config.active_policy_id && (
        <p>Policy: {config.active_policy_id}</p>
      )}
    </div>
  );
}

// Trigger manual sync
async function syncConfig(deviceId: string) {
  const result = await invoke('sync_device_config', { deviceId });
  console.log('Sync result:', result);
}
```

## Database Queries

### Backend (PostgreSQL via SQLAlchemy)
```python
# Get profile with lanes
profile = await session.execute(
    select(DeploymentProfile)
    .options(selectinload(DeploymentProfile.lanes))
    .where(DeploymentProfile.id == profile_id)
)

# Find profile by site
profiles = await session.execute(
    select(DeploymentProfile)
    .where(DeploymentProfile.site_id == site_id)
)
```

### Verifier (SQLite via rusqlite)
```rust
// Get deployment profile
let profile: DeploymentProfile = conn.query_row(
    "SELECT id, name, site_id, network_mode, ux_config, update_policy 
     FROM deployment_profiles WHERE id = ?1",
    params![profile_id],
    |row| {
        Ok(DeploymentProfile {
            id: row.get(0)?,
            name: row.get(1)?,
            site_id: row.get(2)?,
            network_mode: serde_json::from_str(&row.get::<_, String>(3)?).unwrap(),
            ux_config: serde_json::from_str(&row.get::<_, String>(4)?).unwrap(),
            update_policy: serde_json::from_str(&row.get::<_, String>(5)?).unwrap(),
            // ...
        })
    },
)?;

// Get device config
let device_config = conn.query_row(
    "SELECT device_id, deployment_profile_id, lane_id 
     FROM device_config WHERE id = 'current'",
    [],
    |row| {
        Ok((
            row.get::<_, String>(0)?,
            row.get::<_, Option<String>>(1)?,
            row.get::<_, Option<String>>(2)?,
        ))
    },
)?;
```

## Environment Variables

### Verifier
```bash
# API endpoint for device config sync
export MARTY_API_ENDPOINT="https://api.example.com"

# License JWT for authentication
export MARTY_LICENSE_JWT="eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9..."
```

## Common Patterns

### Profile-Level Defaults
```json
{
  "deployment_profile": {
    "default_policy_id": "profile-policy-123",
    "update_policy": {
      "rollout_percentage": 50
    }
  }
}
```

### Lane-Level Overrides
```json
{
  "lane": {
    "default_policy_id": "lane-policy-456",
    "metadata": {
      "zone": "vip",
      "priority": "high"
    }
  }
}
```

### Policy Selection Priority
1. Lane's `default_policy_id` (highest priority)
2. Explicitly set policy via API
3. Profile's `default_policy_id` (lowest priority)

### Rollout Percentage Examples
- `0` = Freeze all updates
- `10` = Canary deployment (10% of devices)
- `50` = Half rollout
- `100` = Full deployment (default)

### Version Pinning
```json
{
  "update_policy": {
    "version_pinned": "1.2.3"
  }
}
```
Blocks all updates except version 1.2.3.

## Debugging

### Check Sync Status
```bash
# Verifier logs
tail -f ~/.marty-verifier/logs/verifier.log | grep "sync"

# Look for:
# - "Syncing device configuration"
# - "Device configuration synced successfully"
# - "Failed to sync device config"
```

### Verify Local Storage
```bash
# Open verifier database
sqlite3 ~/.marty-verifier/marty.db

# Check tables
.tables

# View deployment profile
SELECT * FROM deployment_profiles;

# View lanes
SELECT * FROM lanes;

# View device config
SELECT * FROM device_config;
```

### Test API Endpoints
```bash
# Test device config endpoint
curl -X GET "http://localhost:8000/v1/devices/dev-001/config" \
  -H "Authorization: Bearer $LICENSE_JWT"

# Test profile list
curl -X GET "http://localhost:8000/v1/identity/deployment-profiles" \
  -H "Authorization: Bearer $LICENSE_JWT"
```

## Troubleshooting

### Profile Not Syncing
1. Check device_id is set: `get_runtime_config()`
2. Verify API endpoint configured
3. Check license JWT is valid
4. Review sync logs for errors
5. Test `/v1/devices/{id}/config` manually

### Update Not Installing
1. Check `eligible_for_rollout` in `UpdateInfo`
2. Verify `rollout_percentage` setting
3. Calculate expected group: `hash(device_id) % 100`
4. Check `version_pinned` not blocking
5. Review update manager logs

### Config Not Applied
1. Verify `RuntimeConfig` has profile set
2. Check `apply_deployment_profile()` was called
3. Inspect `snapshot()` output
4. Ensure `get_network_mode()` returns correct value
5. Test `get_ux_config()` returns data

## Best Practices

1. **Start with 100% rollout** for new profiles
2. **Use lanes for granular control** when needed
3. **Test with canary devices** before full rollout
4. **Pin versions during incidents** for stability
5. **Monitor rollout metrics** to detect issues early
6. **Document metadata fields** for lane organization
7. **Use descriptive names** for profiles and lanes
8. **Sync regularly** to keep config up to date
