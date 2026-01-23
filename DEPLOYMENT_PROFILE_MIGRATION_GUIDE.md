# Deployment Profile Migration Guide

This guide helps existing deployments migrate to the new deployment profile system.

## Overview

The deployment profile system centralizes device configuration that was previously scattered across:
- Device-specific config files
- Environment variables
- Hard-coded defaults
- Manual per-device setup

## Migration Path

### Phase 1: Inventory (Week 1)
Identify existing configuration sources and current device assignments.

#### Backend Audit
```bash
# List all sites
psql -d marty -c "SELECT id, name FROM sites;"

# Count devices per site (if tracked)
# Review existing device records
```

#### Verifier Audit
```bash
# For each deployed verifier, collect:
# - Device ID
# - Network mode (online/offline/air-gapped)
# - Update channel
# - Current version
# - Site location
# - Custom config settings

# Example collection script
ssh verifier-001 "cat ~/.marty-verifier/config.toml"
```

#### Configuration Inventory
Create spreadsheet with columns:
- Device ID
- Site ID
- Current network mode
- Current update channel
- Current theme
- Current locale
- Biometric setting
- Audit setting

### Phase 2: Profile Creation (Week 2)
Create deployment profiles that match current configuration groups.

#### Identify Configuration Groups
Group devices by common settings:
- All online devices at Site A → Profile A
- All offline devices at Site B → Profile B
- Air-gapped devices at Site C → Profile C

#### Create Profiles via API
```bash
# Create profile for online devices
curl -X POST "http://localhost:8000/v1/identity/deployment-profiles" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT" \
  -d '{
    "name": "Site A - Online Kiosks",
    "site_id": "site-a-123",
    "network_mode": "online",
    "ux_config": {
      "theme": "light",
      "locale": "en"
    },
    "update_policy": {
      "rollout_percentage": 100
    },
    "offline_cache_ttl_hours": 24,
    "biometric_required": false,
    "audit_all_events": true
  }'

# Save returned profile_id for next step
```

#### Create Lanes (Optional)
If you need sub-groups within a site:
```bash
# VIP lane with stricter policy
curl -X POST "http://localhost:8000/v1/identity/deployment-profiles/{profile_id}/lanes" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT" \
  -d '{
    "name": "VIP Entrance",
    "default_policy_id": "strict-policy-123",
    "metadata": {
      "zone": "vip",
      "priority": "high"
    }
  }'

# Standard lane with normal policy
curl -X POST "http://localhost:8000/v1/identity/deployment-profiles/{profile_id}/lanes" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT" \
  -d '{
    "name": "General Entrance",
    "default_policy_id": "normal-policy-456",
    "metadata": {
      "zone": "general"
    }
  }'
```

### Phase 3: Device Assignment (Week 3)
Assign devices to profiles/lanes without changing verifier behavior yet.

#### Assign Devices to Lanes
```bash
# Assign devices to VIP lane
curl -X POST "http://localhost:8000/v1/identity/lanes/{lane_id}/devices" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT" \
  -d '{
    "device_ids": ["dev-001", "dev-002"]
  }'

# Assign devices to general lane
curl -X POST "http://localhost:8000/v1/identity/lanes/{lane_id}/devices" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT" \
  -d '{
    "device_ids": ["dev-003", "dev-004", "dev-005"]
  }'
```

#### Verify Assignments
```bash
# Check device config endpoint
curl -X GET "http://localhost:8000/v1/devices/dev-001/config" \
  -H "Authorization: Bearer $JWT"

# Should return:
# {
#   "device_id": "dev-001",
#   "deployment_profile": {...},
#   "lane": {...},
#   "presentation_policies": [...],
#   "issuance_policies": [...]
# }
```

### Phase 4: Verifier Update (Week 4)
Deploy new verifier version with deployment profile support.

#### Pre-Deployment Checklist
- [ ] Backup verifier database: `~/.marty-verifier/marty.db`
- [ ] Document current config: `~/.marty-verifier/config.toml`
- [ ] Test rollback procedure
- [ ] Identify canary devices (10% of fleet)
- [ ] Schedule maintenance window
- [ ] Prepare communication for users

#### Update Canary Devices First
```bash
# Set environment variables
export MARTY_API_ENDPOINT="https://api.example.com"
export MARTY_LICENSE_JWT="..."

# Update verifier binary
scp marty-verifier verifier-001:/tmp/
ssh verifier-001 "systemctl stop marty-verifier"
ssh verifier-001 "cp /tmp/marty-verifier /usr/local/bin/"
ssh verifier-001 "systemctl start marty-verifier"

# Monitor logs
ssh verifier-001 "journalctl -u marty-verifier -f"

# Look for:
# - "Syncing device configuration on startup"
# - "Device configuration synced successfully"
```

#### Verify Canary Behavior
```bash
# Check runtime config via Tauri command
# (requires UI or direct API call)

# Verify network mode applied
# Verify UX config applied
# Verify policy selection correct
# Test update check respects rollout percentage
```

#### Roll Out to Remaining Devices
After 24-48 hours of canary monitoring:
```bash
# Update all devices
for device in $(cat device-list.txt); do
  echo "Updating $device..."
  scp marty-verifier $device:/tmp/
  ssh $device "systemctl stop marty-verifier && \
               cp /tmp/marty-verifier /usr/local/bin/ && \
               systemctl start marty-verifier"
done
```

### Phase 5: Validation (Week 5)
Verify all devices correctly using deployment profiles.

#### Validation Checklist
- [ ] All devices reporting correct profile_id
- [ ] Network modes applied correctly
- [ ] UX themes visible in UI
- [ ] Update rollout percentages working
- [ ] Policy overrides functioning
- [ ] Offline cache TTL respected
- [ ] Biometric requirements enforced

#### Validation Script
```python
#!/usr/bin/env python3
import requests
import json

API_BASE = "https://api.example.com"
JWT = "..."

def check_device(device_id):
    resp = requests.get(
        f"{API_BASE}/v1/devices/{device_id}/config",
        headers={"Authorization": f"Bearer {JWT}"}
    )
    config = resp.json()
    
    print(f"Device: {device_id}")
    print(f"  Profile: {config['deployment_profile']['name']}")
    print(f"  Network: {config['deployment_profile']['network_mode']}")
    print(f"  Lane: {config.get('lane', {}).get('name', 'None')}")
    print()

# Check all devices
devices = ["dev-001", "dev-002", "dev-003"]  # ... all devices
for device_id in devices:
    check_device(device_id)
```

### Phase 6: Cleanup (Week 6)
Remove old configuration methods.

#### Remove Device-Specific Configs
```bash
# Remove old config files
ssh verifier-001 "rm ~/.marty-verifier/device-config.json"

# Remove environment variable overrides
ssh verifier-001 "sed -i '/MARTY_NETWORK_MODE/d' /etc/environment"

# Update systemd service to not pass config flags
ssh verifier-001 "systemctl edit marty-verifier"
```

#### Update Documentation
- [ ] Update deployment runbooks
- [ ] Update troubleshooting guides
- [ ] Update operator training materials
- [ ] Archive old config documentation

## Rollback Procedure

If issues occur during migration:

### Quick Rollback (Emergency)
```bash
# Stop new verifier
systemctl stop marty-verifier

# Restore old verifier binary
cp /opt/backup/marty-verifier-old /usr/local/bin/marty-verifier

# Restore old database
cp /opt/backup/marty.db ~/.marty-verifier/

# Restore old config
cp /opt/backup/config.toml ~/.marty-verifier/

# Start old verifier
systemctl start marty-verifier
```

### Gradual Rollback (Controlled)
1. Stop assigning new devices to profiles
2. Continue operating devices on new system
3. Identify root cause of issues
4. Fix issues in backend/verifier
5. Resume migration

## Configuration Mapping

Map old configuration to new profile fields:

### Environment Variables → DeploymentProfile
```bash
# Old: MARTY_NETWORK_MODE=offline
# New: deployment_profile.network_mode = "offline"

# Old: MARTY_THEME=dark
# New: deployment_profile.ux_config.theme = "dark"

# Old: MARTY_UPDATE_CHANNEL=beta
# New: deployment_profile.update_policy.rollout_ring = "beta"

# Old: MARTY_CACHE_TTL_HOURS=48
# New: deployment_profile.offline_cache_ttl_hours = 48

# Old: MARTY_REQUIRE_BIOMETRIC=true
# New: deployment_profile.biometric_required = true
```

### Config File → DeploymentProfile
```toml
# Old: config.toml
# [verifier]
# network_mode = "offline"
# theme = "dark"
# locale = "en"
# 
# [update]
# channel = "stable"
# auto_update = true

# New: Deployment Profile
{
  "network_mode": "offline",
  "ux_config": {
    "theme": "dark",
    "locale": "en"
  },
  "update_policy": {
    "rollout_ring": "stable",
    "rollout_percentage": 100
  }
}
```

## Testing Strategies

### Pre-Migration Testing
1. **Create test profile** with known settings
2. **Assign test device** to profile
3. **Sync config** and verify applied
4. **Test update rollout** with low percentage
5. **Test policy override** via lane
6. **Verify offline behavior** in air-gapped mode

### During Migration Testing
1. **Monitor sync success rate** across fleet
2. **Track config application errors** in logs
3. **Measure update rollout accuracy** (hash distribution)
4. **Validate policy selection** matches expectations
5. **Test network mode enforcement** in each mode

### Post-Migration Testing
1. **Create new profile** and assign devices
2. **Update existing profile** and verify propagation
3. **Test lane device reassignment**
4. **Verify rollout percentage changes** affect updates
5. **Test version pinning** blocks unwanted updates

## Common Issues

### Issue: Devices not syncing config
**Symptoms**: Config changes not appearing on devices

**Diagnosis**:
```bash
# Check verifier logs
journalctl -u marty-verifier | grep sync

# Check API endpoint reachable
curl https://api.example.com/health

# Verify device_id set
sqlite3 ~/.marty-verifier/marty.db "SELECT * FROM device_config;"
```

**Solutions**:
- Ensure `MARTY_API_ENDPOINT` set correctly
- Verify license JWT valid and not expired
- Check network connectivity (firewall, DNS)
- Manually trigger sync: `invoke('sync_device_config', {deviceId: '...'})`

### Issue: Wrong profile applied
**Symptoms**: Device shows config from different profile

**Diagnosis**:
```bash
# Check device assignment
curl "http://localhost:8000/v1/devices/{device_id}/config"

# Verify local storage
sqlite3 ~/.marty-verifier/marty.db "SELECT * FROM deployment_profiles;"
```

**Solutions**:
- Verify device assigned to correct lane
- Check profile_id in device_config table
- Re-sync device config
- Verify no duplicate device_ids across lanes

### Issue: Updates not respecting rollout percentage
**Symptoms**: Wrong percentage of devices updating

**Diagnosis**:
```bash
# Calculate expected group membership
python3 -c "
import hashlib
device_ids = ['dev-001', 'dev-002', 'dev-003']
rollout = 50
for did in device_ids:
    h = int(hashlib.sha256(did.encode()).hexdigest(), 16)
    eligible = (h % 100) < rollout
    print(f'{did}: {eligible}')
"
```

**Solutions**:
- Verify `update_policy.rollout_percentage` set correctly
- Check `ProfileSyncProvider::should_apply_update()` logic
- Ensure device_id hashing consistent
- Review update manager logs for rollout decisions

## Security Considerations

### API Authentication
- All profile operations require valid license JWT
- Verify JWT contains appropriate claims
- Rotate license keys periodically

### Network Isolation
- Air-gapped devices cannot sync profiles automatically
- Use USB import for profile updates in air-gapped mode
- Ensure network_mode=air-gapped blocks all network

### Configuration Tampering
- Profiles stored in backend database with access controls
- Local verifier database read-only by application
- Profile sync uses HTTPS with certificate validation

## Performance Impact

### API Load
- Each device syncs config on startup (one-time)
- Background sync every 24 hours (configurable)
- Minimal impact: ~1KB payload per sync

### Storage Impact
- Deployment profiles: ~1KB per profile
- Lanes: ~500 bytes per lane
- Device config: ~200 bytes per device
- Total: < 100KB for 100 devices

### Startup Time
- Profile sync adds ~200ms to startup
- Parallel with license validation
- Negligible user-visible impact

## Support and Troubleshooting

### Logs to Collect
```bash
# Verifier logs
journalctl -u marty-verifier --since "1 hour ago" > verifier.log

# Backend API logs
docker logs marty-api > api.log

# Database state
sqlite3 ~/.marty-verifier/marty.db ".dump deployment_profiles lanes device_config" > db-state.sql
```

### Debug Commands
```bash
# Check current runtime config
curl localhost:1420/api/runtime_config

# Force sync
curl -X POST localhost:1420/api/sync_device_config \
  -d '{"deviceId": "dev-001"}'

# Check update eligibility
curl localhost:1420/api/check_for_updates
```

### Contact Support
- Email: support@example.com
- Slack: #marty-deployment-profiles
- Docs: https://docs.example.com/deployment-profiles
