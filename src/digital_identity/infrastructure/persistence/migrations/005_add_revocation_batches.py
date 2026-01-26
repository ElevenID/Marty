"""
Migration 005: Add Revocation Batches Table

Creates the digital_identity_revocation_batches table for tracking batch revocation operations.
This supports privacy-preserving credential revocation by batching updates at intervals (1h, 6h, 24h).

Changes:
- Create digital_identity_revocation_batches table with batch tracking fields
- Add indexes for efficient querying by organization, status, and scheduled_for
"""

from sqlalchemy import text


def upgrade(connection):
    """Apply migration changes."""
    
    # Create revocation_batches table
    connection.execute(text("""
        CREATE TABLE digital_identity_revocation_batches (
            id VARCHAR(36) PRIMARY KEY,
            organization_id VARCHAR(36) NOT NULL,
            credential_template_id VARCHAR(36) NOT NULL,
            credential_count INTEGER NOT NULL,
            credential_ids JSON DEFAULT '[]',
            status VARCHAR(20) NOT NULL DEFAULT 'queued',
            scheduled_for TIMESTAMP WITH TIME ZONE NOT NULL,
            completed_at TIMESTAMP WITH TIME ZONE,
            revocation_interval VARCHAR(10) NOT NULL,
            error_message TEXT,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
            version INTEGER NOT NULL DEFAULT 1
        );
    """))
    
    # Add indexes for efficient querying
    connection.execute(text("""
        CREATE INDEX idx_revocation_batches_org 
        ON digital_identity_revocation_batches(organization_id);
    """))
    
    connection.execute(text("""
        CREATE INDEX idx_revocation_batches_template 
        ON digital_identity_revocation_batches(credential_template_id);
    """))
    
    connection.execute(text("""
        CREATE INDEX idx_revocation_batches_status 
        ON digital_identity_revocation_batches(status);
    """))
    
    connection.execute(text("""
        CREATE INDEX idx_revocation_batches_scheduled 
        ON digital_identity_revocation_batches(scheduled_for);
    """))


def downgrade(connection):
    """Revert migration changes."""
    
    # Drop indexes
    connection.execute(text("""
        DROP INDEX IF EXISTS idx_revocation_batches_scheduled;
    """))
    
    connection.execute(text("""
        DROP INDEX IF EXISTS idx_revocation_batches_status;
    """))
    
    connection.execute(text("""
        DROP INDEX IF EXISTS idx_revocation_batches_template;
    """))
    
    connection.execute(text("""
        DROP INDEX IF EXISTS idx_revocation_batches_org;
    """))
    
    # Drop table
    connection.execute(text("""
        DROP TABLE IF EXISTS digital_identity_revocation_batches;
    """))
