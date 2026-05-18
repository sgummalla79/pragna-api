"""soft-delete conversations via archived flag

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-15
"""

from alembic import op
import sqlalchemy as sa

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'conversations',
        sa.Column('archived', sa.Boolean(), nullable=False, server_default='false'),
    )


def downgrade() -> None:
    op.drop_column('conversations', 'archived')
