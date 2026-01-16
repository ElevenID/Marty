"""
Alembic Migration for Digital Identity Tables

Creates the core tables for the Digital Identity module:
- trust_profiles
- credential_templates
- presentation_policies
- deployment_profiles
- flows
- flow_executions

Revision ID: 001_digital_identity_initial
Revises: (depends on existing migrations if any)
Create Date: 2025-01-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '001_digital_identity_initial'
down_revision = None  # Set to previous migration if exists
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create Digital Identity tables."""
    
    # Create trust_profiles table
    op.create_table(
        'trust_profiles',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False, unique=True, index=True),
        sa.Column('type', sa.String(50), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('config', postgresql.JSONB, nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('version', sa.Integer, nullable=False, server_default='1'),
    )
    
    # Create credential_templates table
    op.create_table(
        'credential_templates',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False, unique=True, index=True),
        sa.Column('credential_type', sa.String(100), nullable=False, index=True),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('claims', postgresql.JSONB, nullable=False, server_default='[]'),
        sa.Column('trust_profile_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('revocation_policy', postgresql.JSONB, nullable=True),
        sa.Column('time_policy', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('version', sa.Integer, nullable=False, server_default='1'),
        sa.ForeignKeyConstraint(['trust_profile_id'], ['trust_profiles.id'], ondelete='SET NULL'),
    )
    
    # Create presentation_policies table
    op.create_table(
        'presentation_policies',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False, unique=True, index=True),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('required_credentials', postgresql.JSONB, nullable=False, server_default='[]'),
        sa.Column('requested_claims', postgresql.JSONB, nullable=False, server_default='[]'),
        sa.Column('trust_profile_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('constraints', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('version', sa.Integer, nullable=False, server_default='1'),
        sa.ForeignKeyConstraint(['trust_profile_id'], ['trust_profiles.id'], ondelete='SET NULL'),
    )
    
    # Create deployment_profiles table
    op.create_table(
        'deployment_profiles',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False, unique=True, index=True),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('trust_profile_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('credential_template_ids', postgresql.JSONB, nullable=False, server_default='[]'),
        sa.Column('presentation_policy_ids', postgresql.JSONB, nullable=False, server_default='[]'),
        sa.Column('environment_config', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('version', sa.Integer, nullable=False, server_default='1'),
        sa.ForeignKeyConstraint(['trust_profile_id'], ['trust_profiles.id'], ondelete='SET NULL'),
    )
    
    # Create flows table
    op.create_table(
        'flows',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False, unique=True, index=True),
        sa.Column('flow_type', sa.String(50), nullable=False, index=True),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('deployment_profile_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('steps', postgresql.JSONB, nullable=False, server_default='[]'),
        sa.Column('hooks', postgresql.JSONB, nullable=False, server_default='{}'),
        sa.Column('approval_strategy', sa.String(50), nullable=False, server_default="'AUTO'"),
        sa.Column('timeout_seconds', sa.Integer, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('version', sa.Integer, nullable=False, server_default='1'),
        sa.ForeignKeyConstraint(['deployment_profile_id'], ['deployment_profiles.id'], ondelete='SET NULL'),
    )
    
    # Create flow_executions table
    op.create_table(
        'flow_executions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('flow_id', postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column('status', sa.String(50), nullable=False, server_default="'PENDING'", index=True),
        sa.Column('current_step', sa.String(100), nullable=True),
        sa.Column('context', postgresql.JSONB, nullable=False, server_default='{}'),
        sa.Column('step_results', postgresql.JSONB, nullable=False, server_default='{}'),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('version', sa.Integer, nullable=False, server_default='1'),
        sa.ForeignKeyConstraint(['flow_id'], ['flows.id'], ondelete='CASCADE'),
    )
    
    # Create indexes for common queries
    op.create_index(
        'ix_flow_executions_flow_status',
        'flow_executions',
        ['flow_id', 'status']
    )
    op.create_index(
        'ix_credential_templates_trust_profile',
        'credential_templates',
        ['trust_profile_id']
    )
    op.create_index(
        'ix_presentation_policies_trust_profile',
        'presentation_policies',
        ['trust_profile_id']
    )


def downgrade() -> None:
    """Remove Digital Identity tables."""
    
    # Drop indexes first
    op.drop_index('ix_presentation_policies_trust_profile', table_name='presentation_policies')
    op.drop_index('ix_credential_templates_trust_profile', table_name='credential_templates')
    op.drop_index('ix_flow_executions_flow_status', table_name='flow_executions')
    
    # Drop tables in reverse order (respecting foreign keys)
    op.drop_table('flow_executions')
    op.drop_table('flows')
    op.drop_table('deployment_profiles')
    op.drop_table('presentation_policies')
    op.drop_table('credential_templates')
    op.drop_table('trust_profiles')
