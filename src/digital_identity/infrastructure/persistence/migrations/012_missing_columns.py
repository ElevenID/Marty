"""
Migration: Add missing version/updated_at columns

- TrustProfileIssuer: add version column (S5)
- OrganizationCustomAnchor: add updated_at and version columns (S7)

Revision ID: 012_missing_columns
Revises: 011_field_alignment_batch
Create Date: 2026-03-15
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '012_missing_columns'
down_revision = '011_field_alignment_batch'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- S5: TrustProfileIssuer — add version column ---
    with op.batch_alter_table('digital_identity_trust_profile_issuers') as batch_op:
        batch_op.add_column(
            sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        )

    # --- S7: OrganizationCustomAnchor — add updated_at and version columns ---
    with op.batch_alter_table('organization_custom_anchors') as batch_op:
        batch_op.add_column(
            sa.Column(
                'updated_at',
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )
        batch_op.add_column(
            sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        )

    # Backfill updated_at from created_at where NULL
    op.execute(
        "UPDATE organization_custom_anchors "
        "SET updated_at = created_at "
        "WHERE updated_at IS NULL"
    )


def downgrade() -> None:
    with op.batch_alter_table('digital_identity_trust_profile_issuers') as batch_op:
        batch_op.drop_column('version')

    with op.batch_alter_table('organization_custom_anchors') as batch_op:
        batch_op.drop_column('version')
        batch_op.drop_column('updated_at')
