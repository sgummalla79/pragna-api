"""rename user_skill_agents_v2 → user_skill_agents

Revision ID: 0021
Revises: 0020
Create Date: 2026-05-18
"""
from alembic import op
import sqlalchemy as sa

revision = '0021'
down_revision = '0020'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("ALTER TABLE IF EXISTS user_skill_agents_v2 RENAME TO user_skill_agents"))
    conn.execute(sa.text("ALTER INDEX IF EXISTS idx_user_skill_agents_v2_version_id RENAME TO idx_user_skill_agents_version_id"))
    conn.execute(sa.text("ALTER INDEX IF EXISTS idx_user_skill_agents_v2_user_id RENAME TO idx_user_skill_agents_user_id"))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("ALTER INDEX IF EXISTS idx_user_skill_agents_user_id RENAME TO idx_user_skill_agents_v2_user_id"))
    conn.execute(sa.text("ALTER INDEX IF EXISTS idx_user_skill_agents_version_id RENAME TO idx_user_skill_agents_v2_version_id"))
    conn.execute(sa.text("ALTER TABLE IF EXISTS user_skill_agents RENAME TO user_skill_agents_v2"))
