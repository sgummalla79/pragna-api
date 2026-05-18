"""Drop provider_to_use and model_to_use from user_agents — model now lives in user_agents_versions.

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-15
"""

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    op.execute("ALTER TABLE user_agents DROP COLUMN IF EXISTS provider_to_use")
    op.execute("ALTER TABLE user_agents DROP COLUMN IF EXISTS model_to_use")


def downgrade() -> None:
    op.execute("ALTER TABLE user_agents ADD COLUMN IF NOT EXISTS provider_to_use TEXT")
    op.execute("ALTER TABLE user_agents ADD COLUMN IF NOT EXISTS model_to_use TEXT")
