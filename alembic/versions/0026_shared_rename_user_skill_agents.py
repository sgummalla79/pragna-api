"""rename user_skill_agents → user_skill_agent_versions

Revision ID: 0026
Revises: 0025
Create Date: 2026-05-18
"""
from alembic import op
import sqlalchemy as sa

revision = '0026'
down_revision = '0025'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("ALTER TABLE IF EXISTS user_skill_agents RENAME TO user_skill_agent_versions"))
    conn.execute(sa.text("ALTER INDEX IF EXISTS idx_user_skill_agents_version_id RENAME TO idx_user_skill_agent_versions_version_id"))
    conn.execute(sa.text("ALTER INDEX IF EXISTS idx_user_skill_agents_user_id RENAME TO idx_user_skill_agent_versions_user_id"))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("ALTER INDEX IF EXISTS idx_user_skill_agent_versions_user_id RENAME TO idx_user_skill_agents_user_id"))
    conn.execute(sa.text("ALTER INDEX IF EXISTS idx_user_skill_agent_versions_version_id RENAME TO idx_user_skill_agents_version_id"))
    conn.execute(sa.text("ALTER TABLE IF EXISTS user_skill_agent_versions RENAME TO user_skill_agents"))
