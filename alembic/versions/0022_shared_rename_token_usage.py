"""rename token_usage → user_token_usage

Revision ID: 0022
Revises: 0021
Create Date: 2026-05-18
"""
from alembic import op
import sqlalchemy as sa

revision = '0022'
down_revision = '0021'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().execute(sa.text("ALTER TABLE token_usage RENAME TO user_token_usage"))


def downgrade() -> None:
    op.get_bind().execute(sa.text("ALTER TABLE user_token_usage RENAME TO token_usage"))
