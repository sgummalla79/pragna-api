"""rename user_skills_v2 → user_skills, user_skill_versions_v2 → user_skill_versions, user_skill_agents_v2 → user_skill_agents

Revision ID: 0020
Revises: 0019
Create Date: 2026-05-18
"""
from alembic import op
import sqlalchemy as sa

revision = '0020'
down_revision = '0019'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("ALTER TABLE user_skills_v2 RENAME TO user_skills"))
    conn.execute(sa.text("ALTER TABLE user_skill_versions_v2 RENAME TO user_skill_versions"))
    conn.execute(sa.text("ALTER TABLE user_skill_agents_v2 RENAME TO user_skill_agents"))

    # Rename indexes to match new table names
    conn.execute(sa.text("ALTER INDEX IF EXISTS idx_user_skills_v2_user_id RENAME TO idx_user_skills_user_id"))
    conn.execute(sa.text("ALTER INDEX IF EXISTS idx_user_skill_versions_v2_user_skill_id RENAME TO idx_user_skill_versions_user_skill_id"))
    conn.execute(sa.text("ALTER INDEX IF EXISTS idx_user_skill_versions_v2_status RENAME TO idx_user_skill_versions_status"))
    conn.execute(sa.text("ALTER INDEX IF EXISTS idx_user_skill_agents_v2_version_id RENAME TO idx_user_skill_agents_version_id"))
    conn.execute(sa.text("ALTER INDEX IF EXISTS idx_user_skill_agents_v2_user_id RENAME TO idx_user_skill_agents_user_id"))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("ALTER INDEX IF EXISTS idx_user_skill_versions_status RENAME TO idx_user_skill_versions_v2_status"))
    conn.execute(sa.text("ALTER INDEX IF EXISTS idx_user_skill_versions_user_skill_id RENAME TO idx_user_skill_versions_v2_user_skill_id"))
    conn.execute(sa.text("ALTER INDEX IF EXISTS idx_user_skills_user_id RENAME TO idx_user_skills_v2_user_id"))
    conn.execute(sa.text("ALTER INDEX IF EXISTS idx_user_skill_agents_user_id RENAME TO idx_user_skill_agents_v2_user_id"))
    conn.execute(sa.text("ALTER INDEX IF EXISTS idx_user_skill_agents_version_id RENAME TO idx_user_skill_agents_v2_version_id"))
    conn.execute(sa.text("ALTER INDEX IF EXISTS idx_user_skill_versions_status RENAME TO idx_user_skill_versions_v2_status"))
    conn.execute(sa.text("ALTER INDEX IF EXISTS idx_user_skill_versions_user_skill_id RENAME TO idx_user_skill_versions_v2_user_skill_id"))
    conn.execute(sa.text("ALTER INDEX IF EXISTS idx_user_skills_user_id RENAME TO idx_user_skills_v2_user_id"))
    conn.execute(sa.text("ALTER TABLE user_skill_agents RENAME TO user_skill_agents_v2"))
    conn.execute(sa.text("ALTER TABLE user_skill_versions RENAME TO user_skill_versions_v2"))
    conn.execute(sa.text("ALTER TABLE user_skills RENAME TO user_skills_v2"))
