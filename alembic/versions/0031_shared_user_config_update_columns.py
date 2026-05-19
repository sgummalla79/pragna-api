"""user_config — remove updated_at, add created_at and modified_at

Revision ID: 0031
Revises: 0030
Create Date: 2026-05-18
"""
from alembic import op
import sqlalchemy as sa

revision = '0031'
down_revision = '0030'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    conn.execute(sa.text("ALTER TABLE user_config DROP COLUMN IF EXISTS updated_at"))

    conn.execute(sa.text("""
        ALTER TABLE user_config
        ADD COLUMN created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        ADD COLUMN modified_at TIMESTAMPTZ NOT NULL DEFAULT now()
    """))

    conn.execute(sa.text("""
        CREATE OR REPLACE FUNCTION update_user_config_modified_at()
        RETURNS TRIGGER AS $$
        BEGIN NEW.modified_at = now(); RETURN NEW; END;
        $$ LANGUAGE plpgsql
    """))

    conn.execute(sa.text("""
        CREATE TRIGGER trg_user_config_modified_at
        BEFORE UPDATE ON user_config
        FOR EACH ROW EXECUTE FUNCTION update_user_config_modified_at()
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP TRIGGER IF EXISTS trg_user_config_modified_at ON user_config"))
    conn.execute(sa.text("DROP FUNCTION IF EXISTS update_user_config_modified_at"))
    conn.execute(sa.text("ALTER TABLE user_config DROP COLUMN IF EXISTS modified_at"))
    conn.execute(sa.text("ALTER TABLE user_config DROP COLUMN IF EXISTS created_at"))
    conn.execute(sa.text("ALTER TABLE user_config ADD COLUMN updated_at TIMESTAMPTZ DEFAULT now()"))
