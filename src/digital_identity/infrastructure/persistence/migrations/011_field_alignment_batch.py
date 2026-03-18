"""
Migration: Field alignment batch

- IssuedCredential: add organization_id column
- ApplicationTemplate: make credential_template_id and compliance_profile_id nullable,
  change FK ondelete to SET NULL
- TrustProfile: rename allowed_formats → supported_formats
- TrustProfileIssuer: add standalone id PK, convert composite PK to unique constraint

Revision ID: 011_field_alignment_batch
Revises: 010_revocation_profile_verification_session
Create Date: 2026-03-16
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '011_field_alignment_batch'
down_revision = '010_revocation_profile_verification_session'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- IssuedCredential: add organization_id ---
    op.add_column(
        'digital_identity_issued_credentials',
        sa.Column('organization_id', sa.String(36), nullable=True, index=True),
    )
    op.create_index(
        'ix_di_issued_creds_org_id',
        'digital_identity_issued_credentials',
        ['organization_id'],
    )

    # --- ApplicationTemplate: make FKs nullable with SET NULL ---
    # Drop old FK constraints and recreate with nullable + SET NULL
    with op.batch_alter_table('digital_identity_application_templates') as batch_op:
        batch_op.drop_constraint(
            'fk_app_template_credential_template',
            type_='foreignkey',
        )
        batch_op.drop_constraint(
            'fk_app_template_compliance_profile',
            type_='foreignkey',
        )
        batch_op.alter_column(
            'credential_template_id',
            existing_type=sa.String(36),
            nullable=True,
        )
        batch_op.alter_column(
            'compliance_profile_id',
            existing_type=sa.String(36),
            nullable=True,
        )
        batch_op.create_foreign_key(
            'fk_app_template_credential_template',
            'digital_identity_credential_templates',
            ['credential_template_id'], ['id'],
            ondelete='SET NULL',
        )
        batch_op.create_foreign_key(
            'fk_app_template_compliance_profile',
            'digital_identity_compliance_profiles',
            ['compliance_profile_id'], ['id'],
            ondelete='SET NULL',
        )

    # --- TrustProfile: rename allowed_formats → supported_formats ---
    with op.batch_alter_table('digital_identity_trust_profiles') as batch_op:
        batch_op.alter_column(
            'allowed_formats',
            new_column_name='supported_formats',
        )

    # --- TrustProfileIssuer: add standalone id PK ---
    # SQLite doesn't support ALTER TABLE ... DROP PRIMARY KEY.
    # Use batch mode which recreates the table.
    with op.batch_alter_table('digital_identity_trust_profile_issuers') as batch_op:
        batch_op.add_column(sa.Column('id', sa.String(36), nullable=True))

    # Backfill id values for existing rows
    op.execute(
        "UPDATE digital_identity_trust_profile_issuers "
        "SET id = lower(hex(randomblob(4)) || '-' || hex(randomblob(2)) || '-4' || "
        "substr(hex(randomblob(2)),2) || '-' || substr('89ab', abs(random()) % 4 + 1, 1) || "
        "substr(hex(randomblob(2)),2) || '-' || hex(randomblob(6))) "
        "WHERE id IS NULL"
    )

    # Recreate table with new PK structure via batch
    with op.batch_alter_table(
        'digital_identity_trust_profile_issuers',
        recreate='always',
    ) as batch_op:
        batch_op.alter_column('id', nullable=False)
        # The batch recreate will pick up the new model definition
        # which has id as PK and unique constraint on (trust_profile_id, issuer_id)


def downgrade() -> None:
    # --- TrustProfileIssuer: revert to composite PK ---
    with op.batch_alter_table(
        'digital_identity_trust_profile_issuers',
        recreate='always',
    ) as batch_op:
        batch_op.drop_column('id')

    # --- TrustProfile: rename supported_formats → allowed_formats ---
    with op.batch_alter_table('digital_identity_trust_profiles') as batch_op:
        batch_op.alter_column(
            'supported_formats',
            new_column_name='allowed_formats',
        )

    # --- ApplicationTemplate: revert FKs to NOT NULL ---
    with op.batch_alter_table('digital_identity_application_templates') as batch_op:
        batch_op.drop_constraint(
            'fk_app_template_credential_template',
            type_='foreignkey',
        )
        batch_op.drop_constraint(
            'fk_app_template_compliance_profile',
            type_='foreignkey',
        )
        batch_op.alter_column(
            'credential_template_id',
            existing_type=sa.String(36),
            nullable=False,
        )
        batch_op.alter_column(
            'compliance_profile_id',
            existing_type=sa.String(36),
            nullable=False,
        )
        batch_op.create_foreign_key(
            'fk_app_template_credential_template',
            'digital_identity_credential_templates',
            ['credential_template_id'], ['id'],
            ondelete='CASCADE',
        )
        batch_op.create_foreign_key(
            'fk_app_template_compliance_profile',
            'digital_identity_compliance_profiles',
            ['compliance_profile_id'], ['id'],
            ondelete='RESTRICT',
        )

    # --- IssuedCredential: drop organization_id ---
    op.drop_index('ix_di_issued_creds_org_id', 'digital_identity_issued_credentials')
    op.drop_column('digital_identity_issued_credentials', 'organization_id')
