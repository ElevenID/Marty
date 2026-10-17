# Database ownership and migration requirements

The old Python database bootstrap and development launchers are retired.
They referenced absent service trees, Compose resources and Alembic commands;
the bootstrap also looked below `scripts/src/services` instead of the project
source root. Its database names, schema inventory and sample credentials are
not current deployment configuration.

Current service database provisioning, migrations and operational commands
belong to the [marty-ui stack](https://github.com/ElevenID/marty-ui) and its
[development setup](https://github.com/ElevenID/marty-ui/blob/main/DEVELOPMENT_SETUP.md).
Use the migration entry points and configuration shipped by the selected
release, including their ordering and health/readiness checks.

The published Python
[service database API](../packages/marty-common/marty_common/service_database.py)
and [configuration manager](../packages/marty-common/marty_common/config_manager.py)
remain intact. Their existence does not establish that historical Python
service deployments or a separate database for every current Rust service
have been qualified.

## Acceptance requirements

The old database-per-service proposal still requires owner review against the
current architecture. Before implementing or changing a database boundary:

- Assign schema/data and migration ownership to each service; document shared
  dependencies and the intended physical database or schema isolation.
- Validate per-service connection configuration, least-privilege access and
  tenant isolation against the real database, including negative access tests.
- Plan migration from shared state, data continuity, application compatibility
  and the order of upgrades, rollback or recovery across dependent services.
- Exercise provisioning and migrations in disposable CI databases; verify
  connection health, schema version, repeat execution and partial failure.
- Provide per-service monitoring and an operational recovery procedure.
  Qualify migration and restoration behavior before applying it to live data.

These are retained requirements, not a completed database migration. The
retired commands for deleting migration history or resetting Docker volumes
are not operational recovery procedures. Follow the current owner workflows
for the selected environment.

The old demo database initializer also contained unique trust, credential,
revocation and audit scenarios. Preserve and qualify them through the
[demo data requirements](features/demo-data-qualification.md); the remaining
Python seeder is not a demonstrated schema or behavior replacement.
