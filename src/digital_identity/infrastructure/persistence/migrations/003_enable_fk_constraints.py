"""
Migration 003: Enable Foreign Key Constraints

Enables FK constraints between Trust Profile tables:
- trust_framework_anchors.framework_id -> trust_frameworks.id
- organization_trust_profiles.organization_id -> organizations.id  
- organization_trust_profiles.framework_id -> trust_frameworks.id
- digital_identity_trust_profiles.organization_id -> organizations.id (legacy table)

Prerequisites:
- organizations table must exist
- trust_frameworks table must exist
- All referenced IDs must be valid

Changes:
- Add FK constraint on trust_framework_anchors.framework_id
- Add FK constraints on organization_trust_profiles (organization_id, framework_id)
- Add FK constraint on digital_identity_trust_profiles.organization_id
"""

from sqlalchemy import text


def upgrade(connection):
    """Apply migration changes."""
    
    # Enable FK for trust_framework_anchors.framework_id
    connection.execute(text("""
        ALTER TABLE trust_framework_anchors
        ADD CONSTRAINT trust_framework_anchors_framework_id_fkey
        FOREIGN KEY (framework_id) 
        REFERENCES trust_frameworks(id) 
        ON DELETE CASCADE;
    """))
    
    # Enable FK for organization_trust_profiles.organization_id
    connection.execute(text("""
        ALTER TABLE organization_trust_profiles
        ADD CONSTRAINT organization_trust_profiles_organization_id_fkey
        FOREIGN KEY (organization_id) 
        REFERENCES organizations(id) 
        ON DELETE CASCADE;
    """))
    
    # Enable FK for organization_trust_profiles.framework_id
    connection.execute(text("""
        ALTER TABLE organization_trust_profiles
        ADD CONSTRAINT organization_trust_profiles_framework_id_fkey
        FOREIGN KEY (framework_id) 
        REFERENCES trust_frameworks(id) 
        ON DELETE RESTRICT;
    """))
    
    # Enable FK for digital_identity_trust_profiles.organization_id (legacy table)
    connection.execute(text("""
        ALTER TABLE digital_identity_trust_profiles
        ADD CONSTRAINT digital_identity_trust_profiles_organization_id_fkey
        FOREIGN KEY (organization_id) 
        REFERENCES organizations(id) 
        ON DELETE CASCADE;
    """))


def downgrade(connection):
    """Revert migration changes."""
    
    # Drop FK constraints
    connection.execute(text("""
        ALTER TABLE digital_identity_trust_profiles
        DROP CONSTRAINT IF EXISTS digital_identity_trust_profiles_organization_id_fkey;
    """))
    
    connection.execute(text("""
        ALTER TABLE organization_trust_profiles
        DROP CONSTRAINT IF EXISTS organization_trust_profiles_framework_id_fkey;
    """))
    
    connection.execute(text("""
        ALTER TABLE organization_trust_profiles
        DROP CONSTRAINT IF EXISTS organization_trust_profiles_organization_id_fkey;
    """))
    
    connection.execute(text("""
        ALTER TABLE trust_framework_anchors
        DROP CONSTRAINT IF EXISTS trust_framework_anchors_framework_id_fkey;
    """))


# Standalone migration runner (for non-Alembic environments)
if __name__ == "__main__":
    import sys
    import asyncio
    from sqlalchemy.ext.asyncio import create_async_engine
    
    async def run_migration(database_url: str, direction: str = "up"):
        """Run migration directly."""
        engine = create_async_engine(database_url, echo=True)
        
        async with engine.begin() as conn:
            if direction == "up":
                print("Running migration 003_enable_fk_constraints...")
                await conn.run_sync(upgrade)
                print("Migration complete!")
            elif direction == "down":
                print("Reverting migration 003_enable_fk_constraints...")
                await conn.run_sync(downgrade)
                print("Migration reverted!")
            else:
                print(f"Unknown direction: {direction}")
                sys.exit(1)
        
        await engine.dispose()
    
    if len(sys.argv) < 2:
        print("Usage: python 003_enable_fk_constraints.py <database_url> [up|down]")
        print("Example: python 003_enable_fk_constraints.py postgresql+asyncpg://user:pass@localhost/marty up")
        sys.exit(1)
    
    db_url = sys.argv[1]
    direction = sys.argv[2] if len(sys.argv) > 2 else "up"
    
    asyncio.run(run_migration(db_url, direction))
