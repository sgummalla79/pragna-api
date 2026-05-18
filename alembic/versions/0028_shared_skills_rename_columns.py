"""skills table — rename skill_key→name, name→display_name, add modified_at

Revision ID: 0028
Revises: 0027
Create Date: 2026-05-18
"""
from alembic import op
import sqlalchemy as sa

revision = '0028'
down_revision = '0027'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    conn.execute(sa.text("ALTER TABLE skills RENAME COLUMN skill_key TO name"))
    conn.execute(sa.text("ALTER TABLE skills RENAME COLUMN name TO display_name"))
    conn.execute(sa.text("""
        ALTER TABLE skills ADD COLUMN modified_at TIMESTAMPTZ NOT NULL DEFAULT now()
    """))

    conn.execute(sa.text("""
        CREATE OR REPLACE FUNCTION update_skills_modified_at()
        RETURNS TRIGGER AS $$
        BEGIN NEW.modified_at = now(); RETURN NEW; END;
        $$ LANGUAGE plpgsql
    """))
    conn.execute(sa.text("""
        CREATE TRIGGER trg_skills_modified_at
        BEFORE UPDATE ON skills
        FOR EACH ROW EXECUTE FUNCTION update_skills_modified_at()
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP TRIGGER IF EXISTS trg_skills_modified_at ON skills"))
    conn.execute(sa.text("DROP FUNCTION IF EXISTS update_skills_modified_at"))
    conn.execute(sa.text("ALTER TABLE skills DROP COLUMN IF EXISTS modified_at"))
    conn.execute(sa.text("ALTER TABLE skills RENAME COLUMN display_name TO name"))
    conn.execute(sa.text("ALTER TABLE skills RENAME COLUMN name TO skill_key"))
