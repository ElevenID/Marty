"""
Migration: Persistence Alignment

Adds missing columns to models for full entity↔model round-trip fidelity:
- CredentialTemplate: organization_id, issuer_key_id, issuer_algorithm,
  key_access_mode, revocation_profile_id, privacy_posture, auto_generate_artifacts
- TrustProfile: revocation_profile_id
- PresentationPolicy: fallback_policy, supported_circuits
- DeploymentProfile: organization_id, lanes
- ApplicationTemplate: organization_id, form_fields, claim_collection_rules,
  notifications, ui_config
- CascadeRevocationOperation: organization_id

Revision ID: 008_persistence_alignment
Revises: 007_compliance_profile_seed_update
Create Date: 2026-03-15
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '008_persistence_alignment'
down_revision = '007_compliance_profile_seed_update'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add missing columns for entity-model persistence alignment."""

    # ── CredentialTemplate ────────────────────────────────
    ct = 'digital_identity_credential_templates'

    op.add_column(ct, sa.Column('organization_id', sa.String(36), nullable=True))
    op.create_index(f'ix_{ct}_organization_id', ct, ['organization_id'])

    op.add_column(ct, sa.Column('issuer_key_id', sa.String(255), nullable=True))
    op.add_column(ct, sa.Column('issuer_algorithm', sa.String(50), nullable=True))
    op.add_column(ct, sa.Column('key_access_mode', sa.String(50), nullable=False, server_default='key_vault'))
    op.add_column(ct, sa.Column('revocation_profile_id', sa.String(36), nullable=True))
    op.create_index(f'ix_{ct}_revocation_profile_id', ct, ['revocation_profile_id'])
    op.add_column(ct, sa.Column('privacy_posture', sa.String(50), nullable=False, server_default='selective_disclosure'))
    op.add_column(ct, sa.Column('auto_generate_artifacts', sa.Boolean(), nullable=False, server_default='0'))

    # ── TrustProfile ─────────────────────────────────────
    tp = 'digital_identity_trust_profiles'

    op.add_column(tp, sa.Column('revocation_profile_id', sa.String(36), nullable=True))
    op.create_index(f'ix_{tp}_revocation_profile_id', tp, ['revocation_profile_id'])

    # ── PresentationPolicy ───────────────────────────────
    pp = 'digital_identity_presentation_policies'

    op.add_column(pp, sa.Column('fallback_policy', sa.String(50), nullable=False, server_default='ACCEPT_RAW'))
    op.add_column(pp, sa.Column('supported_circuits', sa.JSON(), nullable=False, server_default='[]'))

    # ── DeploymentProfile ────────────────────────────────
    dp = 'digital_identity_deployment_profiles'

    op.add_column(dp, sa.Column('organization_id', sa.String(36), nullable=True))
    op.create_index(f'ix_{dp}_organization_id', dp, ['organization_id'])
    op.add_column(dp, sa.Column('lanes', sa.JSON(), nullable=False, server_default='[]'))

    # ── ApplicationTemplate ──────────────────────────────
    at = 'digital_identity_application_templates'

    op.add_column(at, sa.Column('organization_id', sa.String(36), nullable=True))
    op.create_index(f'ix_{at}_organization_id', at, ['organization_id'])
    op.add_column(at, sa.Column('form_fields', sa.JSON(), nullable=False, server_default='[]'))
    op.add_column(at, sa.Column('claim_collection_rules', sa.JSON(), nullable=False, server_default='[]'))
    op.add_column(at, sa.Column('notifications', sa.JSON(), nullable=False, server_default='{}'))
    op.add_column(at, sa.Column('ui_config', sa.JSON(), nullable=False, server_default='{}'))

    # ── CascadeRevocationOperation ───────────────────────
    co = 'digital_identity_cascade_operations'

    op.add_column(co, sa.Column('organization_id', sa.String(36), nullable=True))
    op.create_index(f'ix_{co}_organization_id', co, ['organization_id'])


def downgrade() -> None:
    """Remove columns added in this migration."""

    # ── CascadeRevocationOperation ───────────────────────
    co = 'digital_identity_cascade_operations'
    op.drop_index(f'ix_{co}_organization_id', co)
    op.drop_column(co, 'organization_id')

    # ── ApplicationTemplate ──────────────────────────────
    at = 'digital_identity_application_templates'
    op.drop_column(at, 'ui_config')
    op.drop_column(at, 'notifications')
    op.drop_column(at, 'claim_collection_rules')
    op.drop_column(at, 'form_fields')
    op.drop_index(f'ix_{at}_organization_id', at)
    op.drop_column(at, 'organization_id')

    # ── DeploymentProfile ────────────────────────────────
    dp = 'digital_identity_deployment_profiles'
    op.drop_column(dp, 'lanes')
    op.drop_index(f'ix_{dp}_organization_id', dp)
    op.drop_column(dp, 'organization_id')

    # ── PresentationPolicy ───────────────────────────────
    pp = 'digital_identity_presentation_policies'
    op.drop_column(pp, 'supported_circuits')
    op.drop_column(pp, 'fallback_policy')

    # ── TrustProfile ─────────────────────────────────────
    tp = 'digital_identity_trust_profiles'
    op.drop_index(f'ix_{tp}_revocation_profile_id', tp)
    op.drop_column(tp, 'revocation_profile_id')

    # ── CredentialTemplate ────────────────────────────────
    ct = 'digital_identity_credential_templates'
    op.drop_column(ct, 'auto_generate_artifacts')
    op.drop_column(ct, 'privacy_posture')
    op.drop_index(f'ix_{ct}_revocation_profile_id', ct)
    op.drop_column(ct, 'revocation_profile_id')
    op.drop_column(ct, 'key_access_mode')
    op.drop_column(ct, 'issuer_algorithm')
    op.drop_column(ct, 'issuer_key_id')
    op.drop_index(f'ix_{ct}_organization_id', ct)
    op.drop_column(ct, 'organization_id')
