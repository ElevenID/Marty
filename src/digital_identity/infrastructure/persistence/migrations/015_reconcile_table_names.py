"""
Migration: Reconcile table names

Drops stale unprefixed tables created by migration 001 that were superseded
by the ``digital_identity_*`` prefixed ORM models.  Migration 001 created
bare ``trust_profiles``, ``credential_templates``, etc.  The actual ORM
models (and ``Base.metadata.create_all()``) create the ``digital_identity_*``
variants.  This migration cleans up the old schema remnants if they still
exist.

Also documents that ``Base.metadata.create_all()`` (called by
``initialize_database()``) is the authoritative schema creator for the
remaining 17 tables that have no explicit migration (organizations,
webhooks, subscriptions, api_keys, policy_sets, wallet_profiles,
device_registrations, applicants, reviewer_locks, vetting_checks,
biometric_enrollments, notification_payloads, issuance_records,
trust_frameworks, trust_framework_anchors, organization_trust_profiles,
organization_custom_anchors).  These tables are managed by SQLAlchemy
ORM metadata and do not require Alembic migrations.

Revision ID: 015_reconcile_table_names
Revises: 014_ob3_trust_anchors
Create Date: 2026-04-02
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '015_reconcile_table_names'
down_revision = '014_ob3_trust_anchors'
branch_labels = None
depends_on = None

# Tables created by migration 001 with bare (unprefixed) names.
# The ORM uses digital_identity_* prefixed equivalents.
_STALE_TABLES = [
    'flow_executions',
    'flows',
    'deployment_profiles',
    'presentation_policies',
    'credential_templates',
    'trust_profiles',
]

# Indexes created by migration 001 on the stale tables.
_STALE_INDEXES = [
    'ix_flow_executions_flow_status',
    'ix_credential_templates_trust_profile',
    'ix_presentation_policies_trust_profile',
]


def upgrade() -> None:
    """Drop stale unprefixed tables and their indexes if they exist."""
    conn = op.get_bind()

    for idx_name in _STALE_INDEXES:
        # Check if index exists before dropping
        result = conn.execute(sa.text(
            "SELECT 1 FROM pg_indexes WHERE indexname = :name"
        ), {"name": idx_name})
        if result.fetchone():
            op.drop_index(idx_name)

    for table_name in _STALE_TABLES:
        # Check if table exists before dropping (avoid error on fresh installs)
        result = conn.execute(sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = :name"
        ), {"name": table_name})
        if result.fetchone():
            op.drop_table(table_name)


def downgrade() -> None:
    """Re-create the stale unprefixed tables (from migration 001 schema).

    This is provided for rollback safety but should rarely be needed —
    the prefixed tables are the canonical schema.
    """
    op.create_table(
        'trust_profiles',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('type', sa.String(50), nullable=False),
        sa.Column('config', sa.JSON(), server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('version', sa.Integer(), server_default='1'),
    )

    op.create_table(
        'credential_templates',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('credential_type', sa.String(100), nullable=False),
        sa.Column('claims', sa.JSON(), server_default='{}'),
        sa.Column('trust_profile_id', sa.String(36), sa.ForeignKey('trust_profiles.id')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        'presentation_policies',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('required_credentials', sa.JSON(), server_default='[]'),
        sa.Column('requested_claims', sa.JSON(), server_default='[]'),
        sa.Column('trust_profile_id', sa.String(36), sa.ForeignKey('trust_profiles.id')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        'deployment_profiles',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('trust_profile_id', sa.String(36), sa.ForeignKey('trust_profiles.id')),
        sa.Column('credential_template_ids', sa.JSON(), server_default='[]'),
        sa.Column('presentation_policy_ids', sa.JSON(), server_default='[]'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        'flows',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('flow_type', sa.String(50), nullable=False),
        sa.Column('deployment_profile_id', sa.String(36), sa.ForeignKey('deployment_profiles.id')),
        sa.Column('steps', sa.JSON(), server_default='[]'),
        sa.Column('approval_strategy', sa.String(50), server_default='auto'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        'flow_executions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('flow_id', sa.String(36), sa.ForeignKey('flows.id', ondelete='CASCADE')),
        sa.Column('status', sa.String(50), nullable=False),
        sa.Column('context', sa.JSON(), server_default='{}'),
        sa.Column('step_results', sa.JSON(), server_default='[]'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index('ix_flow_executions_flow_status', 'flow_executions', ['flow_id', 'status'])
    op.create_index('ix_credential_templates_trust_profile', 'credential_templates', ['trust_profile_id'])
    op.create_index('ix_presentation_policies_trust_profile', 'presentation_policies', ['trust_profile_id'])
