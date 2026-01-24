# Update Manager Integration with Deployment Profiles

This document describes how the update manager integrates with deployment profile update policies to control software update rollouts.

## Overview

The verifier's update manager now respects deployment profile update policies, enabling:
- **Gradual rollouts**: Control what percentage of devices receive updates
- **Version pinning**: Lock devices to specific software versions
- **Rollout rings**: Categorize devices for staged deployments

## Integration Points

### 1. Update Check (`check_for_updates`)
- **File**: `marty-verifier/src-tauri/src/commands/update.rs`
- **Behavior**: 
  - Checks for available updates via Tauri updater
  - Queries deployment profile update policy from RuntimeConfig
  - Calculates rollout eligibility using `check_rollout_eligibility()`
  - Returns `UpdateInfo` with `eligible_for_rollout` flag
  
### 2. Update Installation (`download_and_install_update`)
- **File**: `marty-verifier/src-tauri/src/commands/update.rs`
- **Behavior**:
  - Checks rollout eligibility before downloading
  - Blocks installation if device not in rollout percentage
  - Blocks installation if version doesn't match pinned version
  - Logs rollout decision for audit trail

### 3. Rollout Eligibility Check (`check_rollout_eligibility`)
- **File**: `marty-verifier/src-tauri/src/commands/update.rs`
- **Logic**:
  1. Get device_id from RuntimeConfig snapshot
  2. Get update_policy from deployment profile
  3. Check version pinning (if set)
  4. Calculate rollout group membership using `ProfileSyncProvider::should_apply_update()`
  5. Return boolean eligibility result

## Update Policy Fields

### UpdatePolicy Value Object
```rust
pub struct UpdatePolicy {
    pub rollout_percentage: Option<u8>,  // 0-100, default 100
    pub version_pinned: Option<String>,  // e.g. "1.2.3"
    pub rollout_ring: Option<String>,    // "canary", "prod", etc.
}
```

### Field Semantics
- **rollout_percentage**: Percentage of devices that receive updates
  - 0 = No devices receive updates (freeze)
  - 50 = Half of devices receive updates
  - 100 = All devices receive updates (default)
  
- **version_pinned**: Exact version string devices must run
  - If set, only this version will be installed
  - Updates to other versions are blocked
  - Useful for regulatory compliance or stability requirements
  
- **rollout_ring**: Category for staged rollouts
  - Not yet integrated with backend deployment logic
  - Future: Backend can target specific rings for early access
  - Examples: "canary", "beta", "prod"

## Rollout Algorithm

### Deterministic Hash-Based Distribution
```rust
fn should_apply_update(device_id: &str, rollout_percentage: u8) -> bool {
    use std::collections::hash_map::DefaultHasher;
    use std::hash::{Hash, Hasher};
    
    let mut hasher = DefaultHasher::new();
    device_id.hash(&mut hasher);
    let hash = hasher.finish();
    
    (hash % 100) < rollout_percentage as u64
}
```

### Properties
- **Deterministic**: Same device_id always gets same result
- **Stable**: Device doesn't flip in/out of rollout group
- **Uniform**: Approximately even distribution across device population
- **Predictable**: Can calculate membership without central coordination

### Example Rollout Groups
| device_id | Hash % 100 | 10% Rollout | 50% Rollout | 100% Rollout |
|-----------|------------|-------------|-------------|--------------|
| dev-001   | 23         | ❌ Skip     | ✅ Update   | ✅ Update    |
| dev-002   | 7          | ✅ Update   | ✅ Update   | ✅ Update    |
| dev-003   | 87         | ❌ Skip     | ❌ Skip     | ✅ Update    |
| dev-004   | 42         | ❌ Skip     | ✅ Update   | ✅ Update    |

## API Response Schema

### UpdateInfo
```typescript
interface UpdateInfo {
  version: string;              // Available version
  current_version: string;      // Installed version
  notes?: string;               // Release notes
  pub_date?: number;            // Unix timestamp
  channel: string;              // "stable", "beta", etc.
  eligible_for_rollout: boolean; // Whether device should update
}
```

## Usage Scenarios

### Scenario 1: Gradual Rollout
```json
{
  "update_policy": {
    "rollout_percentage": 10,
    "version_pinned": null,
    "rollout_ring": "prod"
  }
}
```
- 10% of devices receive updates immediately
- Remaining 90% wait for admin to increase percentage
- Admin can monitor first 10% for issues before expanding

### Scenario 2: Version Freeze
```json
{
  "update_policy": {
    "rollout_percentage": 100,
    "version_pinned": "1.2.3",
    "rollout_ring": "prod"
  }
}
```
- All devices locked to version 1.2.3
- No updates will be applied even if available
- Useful for regulatory compliance or during incident response

### Scenario 3: Canary Deployment
```json
{
  "update_policy": {
    "rollout_percentage": 5,
    "version_pinned": null,
    "rollout_ring": "canary"
  }
}
```
- 5% canary group receives updates first
- Production ring kept at 0% initially
- After canary validation, increase production percentage

## Logging and Observability

### Log Events
```rust
// Rollout eligibility check
tracing::info!(
    device_id = %device_id,
    rollout_percentage = rollout_percentage,
    version = update_version,
    "Device not in rollout group"
);

// Version pinning rejection
tracing::info!(
    current = update_version,
    pinned = pinned_version,
    "Update rejected: version pinned"
);

// Update available but not eligible
tracing::info!(
    version = %update.version,
    "Update available but device not eligible for rollout"
);
```

### Metrics to Track
- Updates checked vs updates installed ratio
- Rollout percentage distribution
- Version pinning rejections
- Time to full rollout (0% → 100%)

## Integration Testing

### Test Cases
1. **No deployment profile**: Updates allowed
2. **No device ID**: Updates allowed
3. **rollout_percentage = 0**: All updates blocked
4. **rollout_percentage = 100**: All updates allowed
5. **rollout_percentage = 50**: ~50% of devices update
6. **version_pinned set**: Only matching version updates
7. **version_pinned mismatch**: Update blocked

### Manual Testing Steps
1. Create deployment profile with rollout_percentage = 10
2. Assign 100 test devices to profile
3. Trigger update check on all devices
4. Verify ~10 devices receive update
5. Verify same 10 devices always selected (deterministic)
6. Increase to 50%, verify additional devices update
7. Set version_pinned, verify only that version installs

## Future Enhancements

### Backend Rollout Ring Targeting
- Admin can publish updates to specific rings only
- Canary ring gets new version first
- Prod ring gets stable version after validation
- Requires backend API changes to `/updates/{ring}/...`

### Rollout Schedule
```json
{
  "rollout_schedule": [
    {"percentage": 10, "delay_hours": 0},
    {"percentage": 50, "delay_hours": 24},
    {"percentage": 100, "delay_hours": 72}
  ]
}
```

### Rollout Telemetry
- Track update success/failure rate per device
- Auto-pause rollout if failure rate exceeds threshold
- Send telemetry to backend for centralized monitoring

### Emergency Rollback
```json
{
  "update_policy": {
    "rollback_to_version": "1.2.2",
    "rollback_reason": "Critical bug in 1.2.3"
  }
}
```

## Files Modified

- `marty-verifier/src-tauri/src/commands/update.rs`
  - Added `ProfileSyncProvider` import
  - Added `eligible_for_rollout` field to `UpdateInfo`
  - Added rollout check to `check_for_updates()`
  - Added rollout gate to `download_and_install_update()`
  - Added `check_rollout_eligibility()` function

## Dependencies

- `RuntimeConfig` snapshot for device_id and deployment_profile
- `ProfileSyncProvider::should_apply_update()` for rollout calculation
- Tauri plugin updater for update checking and installation

## Related Documentation

- [RUNTIME_CONFIG_INTEGRATION_SUMMARY.md](./RUNTIME_CONFIG_INTEGRATION_SUMMARY.md)
- [DEPLOYMENT_PROFILE_IMPLEMENTATION_STATUS.md](./DEPLOYMENT_PROFILE_IMPLEMENTATION_STATUS.md)
- [marty-sync ProfileSyncProvider](../marty-verifier/crates/marty-sync/src/profile_sync.rs)
