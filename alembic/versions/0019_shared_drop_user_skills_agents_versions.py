"""drop v1 tables user_skills, user_agents, user_agent_versions — replaced by user_skills_v2, user_skill_versions_v2, user_skill_agents_v2

Revision ID: 0019
Revises: 0018
Create Date: 2026-05-18
"""
from alembic import op
import sqlalchemy as sa

revision = '0019'
down_revision = '0018'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP TABLE IF EXISTS user_agents_versions CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS user_agents CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS user_skills CASCADE"))


def downgrade() -> None:
    pass  # intentionally irreversible — replaced by v2 tables
