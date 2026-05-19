"""skills table — drop icon and version columns

Revision ID: 0032
Revises: 0031
Create Date: 2026-05-18
"""
from alembic import op
import sqlalchemy as sa

revision = '0032'
down_revision = '0031'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("ALTER TABLE skills DROP COLUMN IF EXISTS icon"))
    conn.execute(sa.text("ALTER TABLE skills DROP COLUMN IF EXISTS version"))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("ALTER TABLE skills ADD COLUMN icon TEXT"))
    conn.execute(sa.text("ALTER TABLE skills ADD COLUMN version INTEGER DEFAULT 1"))
