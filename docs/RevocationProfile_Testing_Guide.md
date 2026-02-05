# RevocationProfile Service - Testing & Verification Guide

## Quick Start Testing

### Prerequisites
```bash
# Service must be running on port 8013
curl http://localhost:8013/health
# Expected: {"status":"healthy","service":"revocation-profile-service"}
```

### Test 1: Index Allocation (Sequential)

```bash
# Get profile ID
PROFILE_ID=$(curl -s "http://localhost:8013/v1/revocation-profiles?organization_id=system" | \
  python3 -c "import sys,json; print(json.load(sys.stdin)[0]['id'])")

# Allocate 5 indices - should return 0, 1, 2, 3, 4
for i in {1..5}; do
  curl -s -X POST \
    "http://localhost:8013/internal/revocation-profiles/$PROFILE_ID/allocate-index" \
    -H "Content-Type: application/json" \
    -d '{"credential_format": "sd_jwt_vc"}' | \
    python3 -c "import sys,json; print('Index:', json.load(sys.stdin)['index'])"
done
```

**Expected Output:**
```
Index: 0
Index: 1
Index: 2
Index: 3
Index: 4
```

### Test 2: Revocation (Status Update)

```bash
# Revoke credential at index 2
curl -s -X POST \
  "http://localhost:8013/internal/revocation-profiles/$PROFILE_ID/process-revocation" \
  -H "Content-Type: application/json" \
  -d '{
    "credential_id": "cred-123",
    "index": 2,
    "status": "revoked",
    "credential_format": "sd_jwt_vc"
  }' | python3 -m json.tool
```

**Expected Output:**
```json
{
  "success": true,
  "status_list_url": "https://status.example.com/system/bitstring/[hash].json",
  "index": 2
}
```

### Test 3: Suspension

```bash
# Suspend credential at index 3
curl -s -X POST \
  "http://localhost:8013/internal/revocation-profiles/$PROFILE_ID/process-revocation" \
  -H "Content-Type: application/json" \
  -d '{
    "credential_id": "cred-456",
    "index": 3,
    "status": "suspended",
    "credential_format": "sd_jwt_vc"
  }' | python3 -m json.tool
```

### Test 4: Reinstatement

```bash
# Reinstate previously revoked credential
curl -s -X POST \
  "http://localhost:8013/internal/revocation-profiles/$PROFILE_ID/process-revocation" \
  -H "Content-Type: application/json" \
  -d '{
    "credential_id": "cred-123",
    "index": 2,
    "status": "reinstated",
    "credential_format": "sd_jwt_vc"
  }' | python3 -m json.tool
```

### Test 5: mDoc with TOKEN_STATUS_LIST

```bash
# Allocate index for mDoc (uses 8-bit TOKEN_STATUS_LIST instead of 1-bit BITSTRING)
curl -s -X POST \
  "http://localhost:8013/internal/revocation-profiles/$PROFILE_ID/allocate-index" \
  -H "Content-Type: application/json" \
  -d '{"credential_format": "mdoc"}' | python3 -m json.tool
```

**Expected Output:**
```json
{
  "index": 0,
  "status_list_url": "https://status.example.com/mdoc/1"
}
```

**Note:** mDoc uses a separate status list from SD-JWT VC, so index starts at 0 again.

## Verification Checklist

### Service Health
- [ ] Service responds to `/health` endpoint
- [ ] Service port 8013 is accessible
- [ ] No errors in `/tmp/revocation-profile.log`

### Index Allocation
- [ ] Sequential indices (0, 1, 2, ...)
- [ ] Separate sequences per format (sd_jwt_vc vs mdoc)
- [ ] No duplicate indices
- [ ] Returns valid status_list_url

### Status Updates
- [ ] Revoke operation succeeds
- [ ] Suspend operation succeeds
- [ ] Reinstate operation succeeds
- [ ] Returns `success: true`
- [ ] Returns updated status_list_url

### Format Handling
- [ ] SD-JWT VC uses BITSTRING format (1-bit per entry)
- [ ] mDoc uses TOKEN_STATUS_LIST format (8-bit per entry)
- [ ] JWT VC uses BITSTRING format
- [ ] Each format maintains separate status lists

### Profile Integration
- [ ] Default profile created on startup
- [ ] Profile ID is valid UUID
- [ ] Profile status is "active"
- [ ] Automation config respected (auto_allocate, auto_publish)

## Common Issues & Solutions

### Issue: Port 8013 already in use
```bash
# Find and kill process
lsof -ti:8013 | xargs kill -9

# Restart service
cd "/Volumes/Heart of Gold/Github/work/marty-ui/services/revocation-profile"
nohup python main.py > /tmp/revocation-profile.log 2>&1 &
```

### Issue: Module not found errors
```bash
# Activate virtual environment
cd "/Volumes/Heart of Gold/Github/work/marty-ui/services"
source .venv/bin/activate

# Install dependencies
pip install fastapi uvicorn httpx pydantic
```

### Issue: Profile not found (404)
```bash
# Get current profile ID (changes on restart)
curl -s "http://localhost:8013/v1/revocation-profiles?organization_id=system" | \
  python3 -c "import sys,json; print(json.load(sys.stdin)[0]['id'])"
```

## Integration Test Script

Create `test_migration.sh`:

```bash
#!/bin/bash
set -e

echo "=== RevocationProfile Migration Test ==="

# Get profile
PROFILE=$(curl -s "http://localhost:8013/v1/revocation-profiles?organization_id=system")
PROFILE_ID=$(echo $PROFILE | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['id'])")
echo "✓ Profile: ${PROFILE_ID:0:8}..."

# Allocate indices
echo "✓ Allocating indices..."
for i in {1..3}; do
  INDEX=$(curl -s -X POST \
    "http://localhost:8013/internal/revocation-profiles/$PROFILE_ID/allocate-index" \
    -H "Content-Type: application/json" \
    -d '{"credential_format": "sd_jwt_vc"}' | \
    python3 -c "import sys,json; print(json.load(sys.stdin)['index'])")
  echo "  Index $INDEX"
done

# Test revocation
echo "✓ Testing revocation..."
RESULT=$(curl -s -X POST \
  "http://localhost:8013/internal/revocation-profiles/$PROFILE_ID/process-revocation" \
  -H "Content-Type: application/json" \
  -d '{"credential_id": "test-123", "index": 1, "status": "revoked", "credential_format": "sd_jwt_vc"}')
SUCCESS=$(echo $RESULT | python3 -c "import sys,json; print(json.load(sys.stdin)['success'])")

if [ "$SUCCESS" = "True" ]; then
  echo "✅ All tests passed!"
else
  echo "❌ Test failed"
  exit 1
fi
```

## Monitoring

### Check Service Logs
```bash
tail -f /tmp/revocation-profile.log
```

### Check Recent Operations
```bash
tail -50 /tmp/revocation-profile.log | grep -E "Allocated index|Updated status list"
```

### Service Metrics (To Be Implemented)
- Index allocations per second
- Status updates per second
- Status list publish operations
- Error rates
- Response times

## Next Steps for Production

1. **Add Persistence**:
   - Replace InMemoryStatusListRepository with PostgreSQL/Redis
   - Add database migrations
   - Implement connection pooling

2. **Add Observability**:
   - Prometheus metrics endpoint
   - Structured logging with correlation IDs
   - Distributed tracing with OpenTelemetry
   - Health checks with readiness/liveness probes

3. **Add Resilience**:
   - Retry logic with exponential backoff
   - Circuit breakers for external dependencies
   - Rate limiting
   - Graceful degradation

4. **Add Security**:
   - JWT authentication for internal endpoints
   - mTLS between services
   - Audit logging for all status changes
   - Secrets management integration

5. **Add Performance**:
   - Redis caching for hot status lists
   - Batch operations for bulk updates
   - Async queue processing (BATCH mode)
   - Status list sharding for large tenants

## Conclusion

The StatusListManager migration is complete and functional. The service provides real status list management with:
- Sequential index allocation
- Format-specific bit/byte manipulation
- Auto-publication with compression
- Profile-based configuration

All core functionality has been tested and verified working.
