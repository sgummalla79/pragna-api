"""Add pinned columns to conversations.

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-15
"""

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    op.execute("ALTER TABLE conversations ADD COLUMN IF NOT EXISTS pinned INTEGER DEFAULT 0")
    op.execute("ALTER TABLE conversations ADD COLUMN IF NOT EXISTS pinned_at TIMESTAMPTZ")
    op.execute("CREATE INDEX IF NOT EXISTS idx_conversations_pinned ON conversations(user_id, pinned)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_conversations_pinned")
    op.execute("ALTER TABLE conversations DROP COLUMN IF EXISTS pinned")
    op.execute("ALTER TABLE conversations DROP COLUMN IF EXISTS pinned_at")
