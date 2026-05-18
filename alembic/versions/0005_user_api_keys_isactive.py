"""add isactive to user_api_keys

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-15
"""

from alembic import op
import sqlalchemy as sa

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'user_api_keys',
        sa.Column('isactive', sa.Boolean(), nullable=False, server_default='true'),
    )


def downgrade() -> None:
    op.drop_column('user_api_keys', 'isactive')
