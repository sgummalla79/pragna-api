"""Add provider_to_use and model_to_use to user_agents_versions.

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-15
"""

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    op.execute("ALTER TABLE user_agents_versions ADD COLUMN IF NOT EXISTS provider_to_use TEXT")
    op.execute("ALTER TABLE user_agents_versions ADD COLUMN IF NOT EXISTS model_to_use TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE user_agents_versions DROP COLUMN IF EXISTS provider_to_use")
    op.execute("ALTER TABLE user_agents_versions DROP COLUMN IF EXISTS model_to_use")
