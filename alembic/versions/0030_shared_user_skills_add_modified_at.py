"""add modified_at to user_skills

Revision ID: 0030
Revises: 0029
Create Date: 2026-05-18
"""
from alembic import op
import sqlalchemy as sa

revision = '0030'
down_revision = '0029'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    conn.execute(sa.text("""
        ALTER TABLE user_skills
        ADD COLUMN modified_at TIMESTAMPTZ NOT NULL DEFAULT now()
    """))

    conn.execute(sa.text("""
        CREATE OR REPLACE FUNCTION update_user_skills_modified_at()
        RETURNS TRIGGER AS $$
        BEGIN NEW.modified_at = now(); RETURN NEW; END;
        $$ LANGUAGE plpgsql
    """))

    conn.execute(sa.text("""
        CREATE TRIGGER trg_user_skills_modified_at
        BEFORE UPDATE ON user_skills
        FOR EACH ROW EXECUTE FUNCTION update_user_skills_modified_at()
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP TRIGGER IF EXISTS trg_user_skills_modified_at ON user_skills"))
    conn.execute(sa.text("DROP FUNCTION IF EXISTS update_user_skills_modified_at"))
    conn.execute(sa.text("ALTER TABLE user_skills DROP COLUMN IF EXISTS modified_at"))
