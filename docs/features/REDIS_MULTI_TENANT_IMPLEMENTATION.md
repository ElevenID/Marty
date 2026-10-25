# Tenant-scoped cache ownership and acceptance

The former implementation summary described retired Python services, migration
runners, and deployment examples. Its completion labels did not establish
cross-tenant isolation, Redis Cluster support, or safe rollback. This note
preserves the feature requirements; it changes no runtime, schema, or data.

## Current owners

- Rust service repositories in [marty-ui](https://github.com/ElevenID/marty-ui/tree/main/rust/services)
  own authentication, issuance, and notification state and authorization.
- The [Rust auth cache repository](https://github.com/ElevenID/marty-ui/blob/main/rust/services/auth/src/cache_repository.rs)
  has configurable session/user-session/PKCE prefixes. Its presence does not
  prove the old `{organization_id}:namespace:identifier` key sketch is deployed.
- Shared cache interfaces belong to
  [MMF data infrastructure](https://github.com/ElevenID/marty-microservices-framework/tree/main/crates/mmf-data).
  Redis topology and configuration belong to the
  [deployment owner](https://github.com/ElevenID/marty-ui/blob/main/deploy-config/README.md).

PostgreSQL durable records and Redis ephemeral state serve different purposes.
The service owner must classify which sessions, challenges, PKCE state, tokens,
and offer indexes are cached, their authoritative store, and their loss/recovery
behavior. Ephemeral storage does not mean loss has no user or security impact.
Key-custody qualification belongs to the separate KMS owner and is not audited
by this cache-document cleanup.

## Acceptance requirements retained

- Derive organization/user/device binding from authenticated service context;
  validate device ownership and deny cross-organization reads, writes, responses,
  enumeration, and deletion. A key prefix alone is not authorization.
- Prove tenant/profile binding for challenge, session, pre-authorized-code,
  access-token, offer, and credential indexes, including stored model fields and
  references. Test two organizations with colliding local identifiers and
  malformed/missing organization context. Qualify needed schema/backfill work
  with real data before retiring migration logic.
- Define expiry, consumption, refresh, invalidation, and replay behavior for each
  cache type. Old 300-second PKCE, seven-day refresh, and one-hour ID-token values
  were examples, not current policy. Verify expiry and recovery at boundaries.
- Audit every legacy-key lookup/write/delete. Fallback to an unscoped key needs
  proven tenant binding; do not restore unconditional dual reads/writes as a
  compatibility shortcut. Qualify rollout, rollback, TTL transition, cache-hit
  monitoring, and explicit invalidation against the owning service.
- Use bounded cursor iteration rather than blocking keyspace enumeration where
  required. Qualify Redis Cluster scans across shards; using SCAN alone does not
  establish cluster compatibility. Multi-key operations and Lua scripts need
  compatible hash slots; cluster database and resharding behavior need tests.
- Qualify Sentinel or Cluster as deployment choices with the actual clients:
  authentication/TLS, reconnects, replica promotion, quorum, topology changes,
  slot coverage, simultaneous faults, and recovery under load. Old node counts,
  ports, memory settings, and Compose/Make commands are not deployment contracts.
- Observe hit/miss rate, latency distributions, failover duration, memory and
  evictions, replication lag, unavailable nodes, and slot changes. Establish
  alert thresholds and ownership through measured service requirements; the old
  ten-second failover, one-second lag, 90% memory, and ten-millisecond P99 numbers
  are unqualified targets, not demonstrated service levels.

No migration, Redis deployment change, legacy-key fallback, or production fault
injection should be inferred from this note. Isolation and topology acceptance
remain unproven until current service and deployment tests demonstrate them.
