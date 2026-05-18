"""rename agents to skill_agents — rename columns agent_key→name, label→display_name, default_content→content, add modified_at trigger

Revision ID: 0016
Revises: 0015
Create Date: 2026-05-18
"""
from alembic import op
import sqlalchemy as sa

revision = '0016'
down_revision = '0015'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── 1. Rename table ───────────────────────────────────────────────────────
    conn.execute(sa.text("ALTER TABLE agents RENAME TO skill_agents"))

    # ── 2. Rename columns ─────────────────────────────────────────────────────
    conn.execute(sa.text("ALTER TABLE skill_agents RENAME COLUMN agent_key TO name"))
    conn.execute(sa.text("ALTER TABLE skill_agents RENAME COLUMN label TO display_name"))
    conn.execute(sa.text("ALTER TABLE skill_agents RENAME COLUMN default_content TO content"))

    # ── 3. Add modified_at ────────────────────────────────────────────────────
    conn.execute(sa.text("""
        ALTER TABLE skill_agents
        ADD COLUMN modified_at TIMESTAMPTZ NOT NULL DEFAULT now()
    """))

    # ── 4. Rename unique constraint ───────────────────────────────────────────
    conn.execute(sa.text("""
        ALTER TABLE skill_agents
        RENAME CONSTRAINT agents_skill_id_agent_key_key TO skill_agents_skill_id_name_key
    """))

    # ── 5. Add trigger to auto-update modified_at on content change ───────────
    conn.execute(sa.text("""
        CREATE OR REPLACE FUNCTION update_skill_agents_modified_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.modified_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """))
    conn.execute(sa.text("""
        CREATE TRIGGER trg_skill_agents_modified_at
        BEFORE UPDATE OF content ON skill_agents
        FOR EACH ROW EXECUTE FUNCTION update_skill_agents_modified_at()
    """))


def downgrade() -> None:
    conn = op.get_bind()

    conn.execute(sa.text("DROP TRIGGER IF EXISTS trg_skill_agents_modified_at ON skill_agents"))
    conn.execute(sa.text("DROP FUNCTION IF EXISTS update_skill_agents_modified_at"))
    conn.execute(sa.text("ALTER TABLE skill_agents DROP COLUMN modified_at"))
    conn.execute(sa.text("ALTER TABLE skill_agents RENAME CONSTRAINT skill_agents_skill_id_name_key TO agents_skill_id_agent_key_key"))
    conn.execute(sa.text("ALTER TABLE skill_agents RENAME COLUMN content TO default_content"))
    conn.execute(sa.text("ALTER TABLE skill_agents RENAME COLUMN display_name TO label"))
    conn.execute(sa.text("ALTER TABLE skill_agents RENAME COLUMN name TO agent_key"))
    conn.execute(sa.text("ALTER TABLE skill_agents RENAME TO agents"))
