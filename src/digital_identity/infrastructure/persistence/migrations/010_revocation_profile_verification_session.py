"""
Migration: RevocationProfile, VerificationSession, privacy_posture JSON

- Create digital_identity_revocation_profiles table
- Create digital_identity_verification_sessions table
- CredentialTemplate: privacy_posture String(50) → JSON (with data migration)

Revision ID: 010_revocation_profile_verification_session
Revises: 009_holder_binding_vct_status
Create Date: 2026-03-15
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '010_revocation_profile_verification_session'
down_revision = '009_holder_binding_vct_status'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Create RevocationProfile table ---
    op.create_table(
        'digital_identity_revocation_profiles',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), nullable=False, index=True),
        sa.Column('name', sa.String(128), nullable=False, index=True),
        sa.Column('revocation_mechanism', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('mechanism_priority', sa.JSON(), server_default='[]'),
        sa.Column('check_mode', sa.String(50), nullable=False, server_default='ALWAYS'),
        sa.Column('cache_ttl_seconds', sa.Integer(), nullable=True),
        sa.Column('offline_grace_seconds', sa.Integer(), nullable=True),
        sa.Column('issuer_config', sa.JSON(), server_default='{}'),
        sa.Column('status_list_url', sa.String(2048), nullable=True),
        sa.Column('metadata', sa.JSON(), server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
    )

    # --- Create VerificationSession table ---
    op.create_table(
        'digital_identity_verification_sessions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('flow_id', sa.String(36),
                  sa.ForeignKey('digital_identity_flows.id', ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('flow_instance_id', sa.String(36), nullable=True, index=True),
        sa.Column('presentation_policy_id', sa.String(36),
                  sa.ForeignKey('digital_identity_presentation_policies.id', ondelete='RESTRICT'),
                  nullable=False, index=True),
        sa.Column('deployment_profile_id', sa.String(36),
                  sa.ForeignKey('digital_identity_deployment_profiles.id', ondelete='SET NULL'),
                  nullable=True),
        sa.Column('verifier_nonce', sa.String(255), nullable=True),
        sa.Column('holder_id', sa.String(255), nullable=True, index=True),
        sa.Column('status', sa.String(50), nullable=False, server_default='PENDING', index=True),
        sa.Column('result', sa.JSON(), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
    )

    # --- CredentialTemplate: privacy_posture String → JSON ---
    with op.batch_alter_table('digital_identity_credential_templates') as batch_op:
        batch_op.add_column(sa.Column('privacy_posture_json', sa.JSON(), nullable=True))

    import json
    conn = op.get_bind()
    rows = conn.execute(
        sa.text('SELECT id, privacy_posture FROM digital_identity_credential_templates')
    ).fetchall()

    for row in rows:
        row_id, pp = row
        if isinstance(pp, str):
            if pp == 'full_disclosure':
                pp_dict = {"default_disclose_all": True, "prefer_predicates": False, "sd_alg": "sha-256"}
            else:
                pp_dict = {"default_disclose_all": False, "prefer_predicates": False, "sd_alg": "sha-256"}
        elif isinstance(pp, dict):
            pp_dict = pp
        else:
            pp_dict = {"default_disclose_all": False, "prefer_predicates": False, "sd_alg": "sha-256"}
        conn.execute(
            sa.text('UPDATE digital_identity_credential_templates SET privacy_posture_json = :val WHERE id = :id'),
            {"val": json.dumps(pp_dict), "id": row_id},
        )

    with op.batch_alter_table('digital_identity_credential_templates') as batch_op:
        batch_op.drop_column('privacy_posture')
        batch_op.alter_column('privacy_posture_json', new_column_name='privacy_posture')


def downgrade() -> None:
    # --- Revert privacy_posture to String ---
    with op.batch_alter_table('digital_identity_credential_templates') as batch_op:
        batch_op.add_column(sa.Column('privacy_posture_str', sa.String(50), nullable=True))

    import json
    conn = op.get_bind()
    rows = conn.execute(
        sa.text('SELECT id, privacy_posture FROM digital_identity_credential_templates')
    ).fetchall()
    for row in rows:
        row_id, pp = row
        if isinstance(pp, str):
            pp = json.loads(pp)
        if isinstance(pp, dict):
            val = "full_disclosure" if pp.get("default_disclose_all") else "selective_disclosure"
        else:
            val = "selective_disclosure"
        conn.execute(
            sa.text('UPDATE digital_identity_credential_templates SET privacy_posture_str = :val WHERE id = :id'),
            {"val": val, "id": row_id},
        )

    with op.batch_alter_table('digital_identity_credential_templates') as batch_op:
        batch_op.drop_column('privacy_posture')
        batch_op.alter_column('privacy_posture_str', new_column_name='privacy_posture')

    # --- Drop tables ---
    op.drop_table('digital_identity_verification_sessions')
    op.drop_table('digital_identity_revocation_profiles')
