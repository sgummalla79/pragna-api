"""add modified_at to users table

Revision ID: 0027
Revises: 0026
Create Date: 2026-05-18
"""
from alembic import op
import sqlalchemy as sa

revision = '0027'
down_revision = '0026'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    conn.execute(sa.text("""
        ALTER TABLE users
        ADD COLUMN modified_at TIMESTAMPTZ NOT NULL DEFAULT now()
    """))

    conn.execute(sa.text("""
        CREATE OR REPLACE FUNCTION update_users_modified_at()
        RETURNS TRIGGER AS $$
        BEGIN NEW.modified_at = now(); RETURN NEW; END;
        $$ LANGUAGE plpgsql
    """))

    conn.execute(sa.text("""
        CREATE TRIGGER trg_users_modified_at
        BEFORE UPDATE ON users
        FOR EACH ROW EXECUTE FUNCTION update_users_modified_at()
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP TRIGGER IF EXISTS trg_users_modified_at ON users"))
    conn.execute(sa.text("DROP FUNCTION IF EXISTS update_users_modified_at"))
    conn.execute(sa.text("ALTER TABLE users DROP COLUMN IF EXISTS modified_at"))
