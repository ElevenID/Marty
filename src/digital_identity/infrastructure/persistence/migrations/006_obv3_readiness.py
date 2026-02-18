"""
Migration: Add OBv3 Readiness Fields

Adds fields to support Open Badge v3 readiness:
- PublishStatus enum for credential templates
- status field on credential_templates (DRAFT/PUBLISHED/ARCHIVED)
- compliance_profile_id FK on credential_templates
- application_template_id FK on credential_templates  
- issuer_certificate_chain_pem field
- issuer_did field
- issuance_protocol field on flows

Revision ID: 006_obv3_readiness
Revises: 005_add_revocation_batches
Create Date: 2026-02-10
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '006_obv3_readiness'
down_revision = '005_add_revocation_batches'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add OBv3 readiness fields."""
    
    # Create PublishStatus enum
    publish_status_enum = postgresql.ENUM(
        'DRAFT', 'PUBLISHED', 'ARCHIVED',
        name='publishstatus',
        create_type=True
    )
    publish_status_enum.create(op.get_bind(), checkfirst=True)
    
    # Add status column to credential_templates
    op.add_column(
        'digital_identity_credential_templates',
        sa.Column(
            'status',
            postgresql.ENUM('DRAFT', 'PUBLISHED', 'ARCHIVED', name='publishstatus'),
            nullable=False,
            server_default='DRAFT',
        )
    )
    op.create_index(
        'ix_credential_templates_status',
        'digital_identity_credential_templates',
        ['status']
    )
    
    # Add compliance_profile_id FK to credential_templates
    op.add_column(
        'digital_identity_credential_templates',
        sa.Column('compliance_profile_id', sa.String(36), nullable=True)
    )
    op.create_foreign_key(
        'fk_credential_templates_compliance_profile',
        'digital_identity_credential_templates',
        'digital_identity_compliance_profiles',
        ['compliance_profile_id'],
        ['id'],
        ondelete='RESTRICT'
    )
    op.create_index(
        'ix_credential_templates_compliance_profile_id',
        'digital_identity_credential_templates',
        ['compliance_profile_id']
    )
    
    # Add application_template_id FK to credential_templates    
    op.add_column(
        'digital_identity_credential_templates',
        sa.Column('application_template_id', sa.String(36), nullable=True)
    )
    op.create_foreign_key(
        'fk_credential_templates_application_template',
        'digital_identity_credential_templates',
        'digital_identity_application_templates',
        ['application_template_id'],
        ['id'],
        ondelete='SET NULL'
    )
    op.create_index(
        'ix_credential_templates_application_template_id',
        'digital_identity_credential_templates',
        ['application_template_id']
    )
    
    # Add issuer artifact fields
    op.add_column(
        'digital_identity_credential_templates',
        sa.Column('issuer_certificate_chain_pem', sa.Text, nullable=True)
    )
    op.add_column(
        'digital_identity_credential_templates',
        sa.Column('issuer_did', sa.String(500), nullable=True)
    )
    
    # Add issuance_protocol to flows
    op.add_column(
        'digital_identity_flows',
        sa.Column('issuance_protocol', sa.String(50), nullable=True)
    )
    op.create_index(
        'ix_flows_issuance_protocol',
        'digital_identity_flows',
        ['issuance_protocol']
    )


def downgrade() -> None:
    """Remove OBv3 readiness fields."""
    
    # Remove indexes
    op.drop_index('ix_flows_issuance_protocol', 'digital_identity_flows')
    op.drop_index('ix_credential_templates_application_template_id', 'digital_identity_credential_templates')
    op.drop_index('ix_credential_templates_compliance_profile_id', 'digital_identity_credential_templates')
    op.drop_index('ix_credential_templates_status', 'digital_identity_credential_templates')
    
    # Remove foreign keys
    op.drop_constraint('fk_credential_templates_application_template', 'digital_identity_credential_templates')
    op.drop_constraint('fk_credential_templates_compliance_profile', 'digital_identity_credential_templates')
    
    # Remove columns
    op.drop_column('digital_identity_flows', 'issuance_protocol')
    op.drop_column('digital_identity_credential_templates', 'issuer_did')
    op.drop_column('digital_identity_credential_templates', 'issuer_certificate_chain_pem')
    op.drop_column('digital_identity_credential_templates', 'application_template_id')
    op.drop_column('digital_identity_credential_templates', 'compliance_profile_id')
    op.drop_column('digital_identity_credential_templates', 'status')
    
    # Drop enum type
    op.execute('DROP TYPE publishstatus')
