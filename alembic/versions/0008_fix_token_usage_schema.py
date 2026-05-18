"""Recreate token_usage with correct schema

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-16
"""

from alembic import op

revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS token_usage CASCADE")
    op.execute("""
        CREATE TABLE token_usage (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            provider        TEXT,
            model           TEXT,
            input_tokens    INTEGER DEFAULT 0,
            output_tokens   INTEGER DEFAULT 0,
            cost_usd        REAL DEFAULT 0,
            created_at      TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute(
        "CREATE INDEX idx_token_usage_conversation ON token_usage(conversation_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS token_usage CASCADE")
