"""
Migration 002: Add Organization Context to Trust Profiles

Adds organization scoping, business context, and compliance tracking to trust profiles.
Enables multi-profile support per organization with business-friendly abstractions.

Changes:
- Add organization_id foreign key to trust_profile table
- Add display_name for user-friendly naming
- Add use_case_tags JSONB for business context tracking
- Add auto_generated boolean flag
- Add compliance_status enum
- Add manually_configured boolean flag
- Add composite unique constraint (organization_id, name)
- Add partial unique index (organization_id, profile_type) WHERE enabled AND profile_type != 'CUSTOM'
"""

from sqlalchemy import text


# Alembic-compatible migration
def upgrade(connection):
    """Apply migration changes."""
    
    # Add new columns
    connection.execute(text("""
        ALTER TABLE trust_profile
        ADD COLUMN organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
        ADD COLUMN display_name VARCHAR(255),
        ADD COLUMN use_case_tags JSONB DEFAULT '[]'::jsonb,
        ADD COLUMN auto_generated BOOLEAN DEFAULT false,
        ADD COLUMN compliance_status VARCHAR(50) DEFAULT 'SETUP_REQUIRED',
        ADD COLUMN manually_configured BOOLEAN DEFAULT false;
    """))
    
    # Create compliance status check constraint
    connection.execute(text("""
        ALTER TABLE trust_profile
        ADD CONSTRAINT trust_profile_compliance_status_check
        CHECK (compliance_status IN ('COMPLIANT', 'NEEDS_ATTENTION', 'SETUP_REQUIRED'));
    """))
    
    # Update existing rows to have default display_name
    connection.execute(text("""
        UPDATE trust_profile
        SET display_name = name
        WHERE display_name IS NULL;
    """))
    
    # Make display_name NOT NULL after setting defaults
    connection.execute(text("""
        ALTER TABLE trust_profile
        ALTER COLUMN display_name SET NOT NULL;
    """))
    
    # Drop old unique constraint on name (if exists)
    connection.execute(text("""
        ALTER TABLE trust_profile
        DROP CONSTRAINT IF EXISTS trust_profile_name_key;
    """))
    
    # Add composite unique constraint (organization_id, name)
    connection.execute(text("""
        ALTER TABLE trust_profile
        ADD CONSTRAINT trust_profile_org_name_unique
        UNIQUE (organization_id, name);
    """))
    
    # Add partial unique index for one active profile per framework per org
    # Excludes CUSTOM profiles to allow unlimited custom profiles
    connection.execute(text("""
        CREATE UNIQUE INDEX trust_profile_org_type_unique
        ON trust_profile (organization_id, profile_type)
        WHERE enabled = true AND profile_type != 'CUSTOM';
    """))
    
    # Add index on organization_id for query performance
    connection.execute(text("""
        CREATE INDEX idx_trust_profile_organization_id
        ON trust_profile (organization_id);
    """))
    
    # Add index on compliance_status for dashboard queries
    connection.execute(text("""
        CREATE INDEX idx_trust_profile_compliance_status
        ON trust_profile (compliance_status)
        WHERE enabled = true;
    """))
    
    # Add index on use_case_tags for filtering
    connection.execute(text("""
        CREATE INDEX idx_trust_profile_use_case_tags
        ON trust_profile USING gin (use_case_tags);
    """))


def downgrade(connection):
    """Revert migration changes."""
    
    # Drop indexes
    connection.execute(text("DROP INDEX IF EXISTS idx_trust_profile_use_case_tags;"))
    connection.execute(text("DROP INDEX IF EXISTS idx_trust_profile_compliance_status;"))
    connection.execute(text("DROP INDEX IF EXISTS idx_trust_profile_organization_id;"))
    connection.execute(text("DROP INDEX IF EXISTS trust_profile_org_type_unique;"))
    
    # Drop composite unique constraint
    connection.execute(text("""
        ALTER TABLE trust_profile
        DROP CONSTRAINT IF EXISTS trust_profile_org_name_unique;
    """))
    
    # Restore old unique constraint on name
    connection.execute(text("""
        ALTER TABLE trust_profile
        ADD CONSTRAINT trust_profile_name_key UNIQUE (name);
    """))
    
    # Drop check constraint
    connection.execute(text("""
        ALTER TABLE trust_profile
        DROP CONSTRAINT IF EXISTS trust_profile_compliance_status_check;
    """))
    
    # Drop new columns
    connection.execute(text("""
        ALTER TABLE trust_profile
        DROP COLUMN IF EXISTS manually_configured,
        DROP COLUMN IF EXISTS compliance_status,
        DROP COLUMN IF EXISTS auto_generated,
        DROP COLUMN IF EXISTS use_case_tags,
        DROP COLUMN IF EXISTS display_name,
        DROP COLUMN IF EXISTS organization_id;
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
                print("Running migration 002_add_organization_context...")
                await conn.run_sync(upgrade)
                print("Migration complete!")
            elif direction == "down":
                print("Reverting migration 002_add_organization_context...")
                await conn.run_sync(downgrade)
                print("Migration reverted!")
            else:
                print(f"Unknown direction: {direction}")
                sys.exit(1)
        
        await engine.dispose()
    
    if len(sys.argv) < 2:
        print("Usage: python 002_add_organization_context.py <database_url> [up|down]")
        print("Example: python 002_add_organization_context.py postgresql+asyncpg://user:pass@localhost/marty up")
        sys.exit(1)
    
    db_url = sys.argv[1]
    direction = sys.argv[2] if len(sys.argv) > 2 else "up"
    
    asyncio.run(run_migration(db_url, direction))
