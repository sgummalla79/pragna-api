"""add capabilities column to provider_registry

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-16
"""

from alembic import op
import sqlalchemy as sa

revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    conn.execute(sa.text("""
        ALTER TABLE provider_registry
        ADD COLUMN IF NOT EXISTS capabilities JSONB NOT NULL DEFAULT '{}';
    """))

    # Anthropic supports extended thinking (Claude models)
    conn.execute(sa.text("""
        UPDATE provider_registry
        SET capabilities = '{"extended_thinking": true}'
        WHERE provider_key = 'anthropic';
    """))


def downgrade() -> None:
    op.drop_column('provider_registry', 'capabilities')
