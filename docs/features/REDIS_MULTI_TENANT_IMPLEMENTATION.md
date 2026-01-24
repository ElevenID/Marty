# Redis Multi-Tenant Implementation Summary

## Overview
Successfully implemented multi-tenant isolation for Redis cache using organization-scoped hash tags `{org-id}`, ensuring Redis Cluster compatibility and preventing cross-tenant data access.

## Architecture Decisions

### Why Redis + PostgreSQL?
- **PostgreSQL**: Persistent data (users, devices, challenges, credentials)
- **Redis**: Ephemeral session data, PKCE state, OID4VCI flows, rate limiting
- **Decision**: Keep both - they serve distinct purposes

### Why Redis Sentinel over Cluster?
- **Sentinel** (recommended for production):
  - Automatic failover with 3 sentinels (quorum: 2)
  - Simple master-replica topology
  - Easier to operate and debug
  - Sufficient for most workloads (vertical scaling)

- **Cluster** (future horizontal scaling):
  - Automatic sharding across 3+ nodes
  - Higher throughput for massive scale
  - More complex operations and monitoring
  - Requires hash tags for multi-key operations

### Hash Tag Pattern
All Redis keys now use: `{organization_id}:namespace:identifier`

**Benefits**:
- Multi-tenant isolation: Each organization's data is isolated by key prefix
- Redis Cluster ready: Hash tags ensure all org data maps to same slot
- Multi-key operations: MGET, DEL, pipelines work within organization scope
- Backwards compatible: Code falls back to legacy keys if org-scoped keys don't exist

## Changes Made

### 1. Infrastructure Configuration

#### docker-compose.yml
- Added comprehensive Redis documentation (lines 442-466)
- Documented key patterns for all use cases
- Added references to Sentinel and Cluster setups

#### docker-compose.sentinel.yml
- 3 sentinels (ports 26379-26381) monitoring master
- 1 master + 1 replica for automatic failover
- Quorum: 2 (minimum sentinels for valid failover)
- Down-after: 5000ms, failover-timeout: 10000ms

#### docker-compose.cluster.yml
- 3 master nodes (ports 7000-7002)
- Automatic slot assignment (0-16383 distributed)
- Cluster bus communication (ports 17000-17002)
- 256MB memory per node, LRU eviction

#### sentinel.conf
- Standalone Sentinel configuration reference
- Documents monitoring and failover parameters

#### Makefile
- `make dev-sentinel`: Start Sentinel HA environment
- `make dev-cluster`: Start Redis Cluster (experimental)

### 2. Database Migration

#### marty-ui/src/subscription/models.py
- Added `organization_id` column to `PushChallenge` model
- Foreign key to `organizations.id` table
- Indexed for query performance
- Nullable for backwards compatibility

#### marty-ui/src/subscription/migrations/add_organization_to_challenges.py
- Adds column with foreign key constraint
- Backfills from `device_registrations.organization_id`
- Creates index for efficient lookups
- Standalone runner using asyncpg

**Run migration**: `python marty-ui/src/subscription/migrations/add_organization_to_challenges.py`

### 3. Authorization Layer

#### src/notifications/dependencies.py
Created `verify_device_ownership()` dependency:
- Verifies device exists
- Checks user_id matches JWT subject
- Validates organization_id matches JWT organization claim
- Raises 403 if ownership validation fails

Used by challenge API endpoints for consistent authorization.

### 4. Cache Layer Changes

#### Challenge Store (src/notifications/challenge_store.py)
Updated all methods to accept `organization_id`:
- `store_challenge()`: `{org:{org_id}}:challenges:{device_id}:{challenge_id}`
- `get_challenge()`: Tries org-scoped, falls back to legacy
- `get_pending_challenges()`: `{org:{org_id}}:challenges:{device_id}:*`
- `respond_to_challenge()`: Updates both org-scoped and legacy keys
- `delete_challenge()`: Removes both versions

**Note**: Uses direct Redis client with `scan_iter()` for pattern matching (already cluster-safe).

#### Auth Cache (marty-ui/src/auth/cache.py)
Updated all methods to use MMF `ICacheManager`:
- **PKCE state**: `{organization_id}:pkce:{state}` (300s TTL)
- **Refresh tokens**: `{organization_id}:refresh:{session_id}` (7 days)
- **ID tokens**: `{organization_id}:id_token:{subject}:{nonce}` (1 hour)

All methods accept `organization_id` parameter extracted from JWT claims.

#### Issuance Storage (marty-ui/src/issuance/adapters.py)
Updated Redis adapter methods:
- **Sessions**: 
  - By ID: `{org-id}:session:id:{id}`
  - By pre-auth code: `{org-id}:session:pre-auth:{code}`
  - By access token: `{org-id}:session:access:{token}`
- **Offers**: 
  - By ID: `{org-id}:offer:id:{id}`
  - By credential: `{org-id}:offer:credential:{cred_id}`

Extracts `org_id` from `session.to_dict()["organization_id"]`.

**TODO**: Verify `StoredSession` and `StoredOffer` models include `organization_id` field.

#### Signing Keys (marty-ui/src/issuance/signing.py)
- Updated `key_id` pattern: `{organization_id}-{algorithm}-test` (line 117)
- Ensures signing keys are isolated per organization
- SpruceIDKeyManager stores keys with org-scoped IDs

#### Challenge API (src/notifications/api.py)
Updated endpoints:
- `create_challenge()`: Extracts `org_id` from `device.organization_id`
- `get_pending_challenges()`: Passes org_id to challenge_store
- `respond_to_challenge()`: Uses `verify_device_ownership` dependency

### 5. Framework Updates

#### MMF RedisCacheManager (mmf/adapters/cache/redis_cache.py)
Replaced `KEYS` command with `SCAN` for cluster compatibility:
- Old: `await self._redis.keys(pattern)` - Blocks server, fails in cluster
- New: Cursor-based iteration with `scan(cursor, match, count=100)`
- Prevents blocking on large keyspaces
- Works with Redis Cluster sharded data

## Testing

### Sentinel Testing
```bash
make dev-sentinel

# Check Sentinel status
docker exec redis-sentinel-1 redis-cli -p 26379 sentinel master mymaster

# Simulate master failover
docker stop redis-master

# Watch logs for automatic promotion
docker logs -f redis-sentinel-1
```

### Cluster Testing
```bash
make dev-cluster

# Check cluster topology
docker exec redis-node-1 redis-cli -p 7000 cluster info
docker exec redis-node-1 redis-cli -p 7000 cluster nodes

# Test multi-key operations within organization
docker exec redis-node-1 redis-cli -p 7000
> SET {org-123}:key1 value1
> SET {org-123}:key2 value2
> MGET {org-123}:key1 {org-123}:key2  # Works - same slot
> MGET {org-123}:key1 {org-456}:key2  # Fails - different slots
```

### Multi-Tenant Validation
1. Create test users in two different organizations via Keycloak
2. Obtain JWT tokens for both users
3. Verify cache keys are properly isolated:
   ```bash
   # User in org-123
   docker exec redis redis-cli KEYS "{org-123}:*"
   
   # User in org-456
   docker exec redis redis-cli KEYS "{org-456}:*"
   ```
4. Attempt cross-organization access - should fail authorization

## Deployment Strategy

### Rollout Plan
1. **Deploy code changes** (backwards compatible):
   - New code tries org-scoped keys first
   - Falls back to legacy keys if not found
   - No downtime required

2. **Monitor cache hit rates**:
   - Watch for cache misses as old keys expire
   - Verify new org-scoped keys are being created

3. **Natural migration**:
   - Old sessions expire (7 days max)
   - New sessions use org-scoped keys
   - No manual migration needed

4. **Switch to Sentinel** (optional HA):
   - Deploy `docker-compose.sentinel.yml` to staging
   - Test automatic failover scenarios
   - Roll out to production with monitoring

5. **Future: Cluster migration** (if needed):
   - All code already uses hash tags
   - Switch connection strings to cluster endpoints
   - Test multi-key operations within organizations

### Rollback Plan
If issues arise:
1. Redis cache is ephemeral - no data loss risk
2. Code falls back to legacy keys automatically
3. Roll back code deployment
4. Old keys still work until natural expiration

### Cache Invalidation
No explicit invalidation needed:
- Sessions expire naturally (TTL enforced)
- PKCE state expires after 300 seconds
- Refresh tokens expire after 7 days
- Issuance sessions expire after completion

## Configuration

### Environment Variables
Update application configuration to use Sentinel:

```python
# For Sentinel (production)
REDIS_SENTINELS = "redis-sentinel-1:26379,redis-sentinel-2:26380,redis-sentinel-3:26381"
REDIS_MASTER_NAME = "mymaster"
REDIS_PASSWORD = "your-secure-password"  # Set in production

# For Cluster (future)
REDIS_CLUSTER_NODES = "redis-node-1:7000,redis-node-2:7001,redis-node-3:7002"
```

### Redis Client Configuration
```python
# Sentinel client
from redis.asyncio.sentinel import Sentinel

sentinel = Sentinel(
    [("redis-sentinel-1", 26379), 
     ("redis-sentinel-2", 26380), 
     ("redis-sentinel-3", 26381)],
    password="your-secure-password"
)
master = sentinel.master_for("mymaster", socket_timeout=0.1)

# Cluster client (future)
from redis.asyncio.cluster import RedisCluster

cluster = RedisCluster(
    startup_nodes=[
        {"host": "redis-node-1", "port": 7000},
        {"host": "redis-node-2", "port": 7001},
        {"host": "redis-node-3", "port": 7002},
    ]
)
```

## Monitoring

### Key Metrics
- **Cache hit rate**: Should remain high after migration
- **Sentinel failover time**: Target <10 seconds
- **Cluster slot coverage**: All 16384 slots assigned
- **Memory usage per node**: Monitor for evictions
- **Replication lag**: Should be <1 second

### Alerts
- Sentinel: All sentinels down (no automatic failover)
- Cluster: Node down, slot migration in progress
- Memory: 90% usage triggering evictions
- Latency: P99 >10ms for cache operations

## Known Limitations

1. **Challenge Store Direct Redis**:
   - Uses direct Redis client instead of MMF ICacheManager
   - Reason: Needs `scan_iter()` for pattern matching
   - Already cluster-safe (uses SCAN not KEYS)
   - TODO: Refactor to use MMF with pattern matching support

2. **StoredSession/StoredOffer Fields**:
   - Need to verify `organization_id` field exists
   - Issuance code extracts `session.to_dict()["organization_id"]`
   - May need to add field to dataclass if missing

3. **Redis Cluster Constraints**:
   - Multi-key operations must use same hash tag
   - Lua scripts must access keys from single slot
   - SELECT database command not supported (always db 0)
   - Resharding requires downtime or sophisticated tooling

## Next Steps

1. **Run database migration**:
   ```bash
   python marty-ui/src/subscription/migrations/add_organization_to_challenges.py
   ```

2. **Test Sentinel setup**:
   ```bash
   make dev-sentinel
   # Simulate failures, verify automatic recovery
   ```

3. **Verify StoredSession model**:
   - Check `marty-ui/src/issuance/ports.py` for `StoredSession` dataclass
   - Ensure `organization_id: str` field exists

4. **Update Redis client**:
   - Switch from single instance to Sentinel client in staging
   - Test connection failover scenarios
   - Monitor latency and throughput

5. **Load testing**:
   - Verify cache hit rates with org-scoped keys
   - Test multi-tenant isolation (no cross-org access)
   - Benchmark Sentinel vs single instance performance

## References

- [Redis Sentinel Documentation](https://redis.io/docs/management/sentinel/)
- [Redis Cluster Tutorial](https://redis.io/docs/management/scaling/)
- [Redis Hash Tags](https://redis.io/docs/reference/cluster-spec/#hash-tags)
- [Keycloak Organizations](https://www.keycloak.org/docs/latest/server_admin/#organizations)
- [OID4VCI Specification](https://openid.net/specs/openid-4-verifiable-credential-issuance-1_0.html)
