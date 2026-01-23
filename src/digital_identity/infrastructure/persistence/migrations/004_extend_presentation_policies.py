"""
Migration 004: Extend Presentation Policies

Adds new fields to presentation policies for:
- Explicit issuer allowlist (allowed_issuers)
- Derived attribute preferences (derived_attribute_preferences)
- Credential ranking strategy (credential_ranking_strategy, credential_ranking_weights)

Changes:
- Add allowed_issuers JSON column
- Add derived_attribute_preferences JSON column
- Add credential_ranking_strategy VARCHAR(50) column
- Add credential_ranking_weights JSON column
"""

from sqlalchemy import text


def upgrade(connection):
    """Apply migration changes."""
    
    # Add allowed_issuers column
    connection.execute(text("""
        ALTER TABLE digital_identity_presentation_policies
        ADD COLUMN allowed_issuers JSON DEFAULT '[]';
    """))
    
    # Add derived_attribute_preferences column
    connection.execute(text("""
        ALTER TABLE digital_identity_presentation_policies
        ADD COLUMN derived_attribute_preferences JSON DEFAULT '{}';
    """))
    
    # Add credential_ranking_strategy column
    connection.execute(text("""
        ALTER TABLE digital_identity_presentation_policies
        ADD COLUMN credential_ranking_strategy VARCHAR(50) NOT NULL DEFAULT 'freshest_first';
    """))
    
    # Add credential_ranking_weights column
    connection.execute(text("""
        ALTER TABLE digital_identity_presentation_policies
        ADD COLUMN credential_ranking_weights JSON DEFAULT '{}';
    """))


def downgrade(connection):
    """Revert migration changes."""
    
    # Remove added columns
    connection.execute(text("""
        ALTER TABLE digital_identity_presentation_policies
        DROP COLUMN IF EXISTS allowed_issuers;
    """))
    
    connection.execute(text("""
        ALTER TABLE digital_identity_presentation_policies
        DROP COLUMN IF EXISTS derived_attribute_preferences;
    """))
    
    connection.execute(text("""
        ALTER TABLE digital_identity_presentation_policies
        DROP COLUMN IF EXISTS credential_ranking_strategy;
    """))
    
    connection.execute(text("""
        ALTER TABLE digital_identity_presentation_policies
        DROP COLUMN IF EXISTS credential_ranking_weights;
    """))
