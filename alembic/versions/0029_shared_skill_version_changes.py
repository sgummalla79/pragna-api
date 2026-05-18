"""user_skill_versions add modified_at; user_skill_agent_versions drop user_id

Revision ID: 0029
Revises: 0028
Create Date: 2026-05-18
"""
from alembic import op
import sqlalchemy as sa

revision = '0029'
down_revision = '0028'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── user_skill_versions: add modified_at ──────────────────────────────────
    conn.execute(sa.text("""
        ALTER TABLE user_skill_versions
        ADD COLUMN modified_at TIMESTAMPTZ NOT NULL DEFAULT now()
    """))

    conn.execute(sa.text("""
        CREATE OR REPLACE FUNCTION update_user_skill_versions_modified_at()
        RETURNS TRIGGER AS $$
        BEGIN NEW.modified_at = now(); RETURN NEW; END;
        $$ LANGUAGE plpgsql
    """))
    conn.execute(sa.text("""
        CREATE TRIGGER trg_user_skill_versions_modified_at
        BEFORE UPDATE ON user_skill_versions
        FOR EACH ROW EXECUTE FUNCTION update_user_skill_versions_modified_at()
    """))

    # ── user_skill_agent_versions: drop user_id ───────────────────────────────
    conn.execute(sa.text(
        "DROP INDEX IF EXISTS idx_user_skill_agent_versions_user_id"
    ))
    conn.execute(sa.text(
        "ALTER TABLE user_skill_agent_versions DROP COLUMN IF EXISTS user_id"
    ))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP TRIGGER IF EXISTS trg_user_skill_versions_modified_at ON user_skill_versions"))
    conn.execute(sa.text("DROP FUNCTION IF EXISTS update_user_skill_versions_modified_at"))
    conn.execute(sa.text("ALTER TABLE user_skill_versions DROP COLUMN IF EXISTS modified_at"))
