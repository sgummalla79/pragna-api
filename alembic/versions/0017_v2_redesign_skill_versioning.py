"""v2 per-user skill versioning — drop old global tables, create user_skills_v2, user_skill_versions_v2, user_skill_agents_v2

Revision ID: 0017
Revises: 0016
Create Date: 2026-05-18
"""
from alembic import op
import sqlalchemy as sa

revision = '0017'
down_revision = '0016'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── Drop old global v2 tables (dependency order) ──────────────────────────
    conn.execute(sa.text("DROP TABLE IF EXISTS skill_draft_agents CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS skill_drafts CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS skill_version_agents CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS skill_versions CASCADE"))

    # ── user_skills_v2 — one row per user per installed skill ─────────────────
    conn.execute(sa.text("""
        CREATE TABLE user_skills_v2 (
            id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id         TEXT        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            skill_id        UUID        NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
            current_version INT         NOT NULL DEFAULT 0,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (user_id, skill_id)
        )
    """))

    # ── user_skill_versions_v2 — version history per user_skill ───────────────
    conn.execute(sa.text("""
        CREATE TABLE user_skill_versions_v2 (
            id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            user_skill_id   UUID        NOT NULL REFERENCES user_skills_v2(id) ON DELETE CASCADE,
            version_number  INT         NOT NULL DEFAULT 1,
            status          VARCHAR     NOT NULL DEFAULT 'draft'
                                        CHECK (status IN ('draft', 'published')),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (user_skill_id, version_number)
        )
    """))

    # ── user_skill_agents_v2 — agent snapshot inside a version ────────────────
    conn.execute(sa.text("""
        CREATE TABLE user_skill_agents_v2 (
            id                    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id               TEXT        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            user_skill_version_id UUID        NOT NULL REFERENCES user_skill_versions_v2(id) ON DELETE CASCADE,
            skill_agent_id        UUID        NOT NULL REFERENCES skill_agents(id) ON DELETE CASCADE,
            content               TEXT        NOT NULL,
            model_id              UUID        REFERENCES user_llm_models(id) ON DELETE SET NULL,
            created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
            modified_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (user_skill_version_id, skill_agent_id)
        )
    """))

    # ── Indexes ───────────────────────────────────────────────────────────────
    conn.execute(sa.text("CREATE INDEX idx_user_skills_v2_user_id ON user_skills_v2(user_id)"))
    conn.execute(sa.text("CREATE INDEX idx_user_skill_versions_v2_user_skill_id ON user_skill_versions_v2(user_skill_id)"))
    conn.execute(sa.text("CREATE INDEX idx_user_skill_versions_v2_status ON user_skill_versions_v2(user_skill_id, status)"))
    conn.execute(sa.text("CREATE INDEX idx_user_skill_agents_v2_version_id ON user_skill_agents_v2(user_skill_version_id)"))
    conn.execute(sa.text("CREATE INDEX idx_user_skill_agents_v2_user_id ON user_skill_agents_v2(user_id)"))

    # ── Trigger: auto-update modified_at on content change ────────────────────
    conn.execute(sa.text("""
        CREATE OR REPLACE FUNCTION update_user_skill_agents_v2_modified_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.modified_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """))
    conn.execute(sa.text("""
        CREATE TRIGGER trg_user_skill_agents_v2_modified_at
        BEFORE UPDATE OF content ON user_skill_agents_v2
        FOR EACH ROW EXECUTE FUNCTION update_user_skill_agents_v2_modified_at()
    """))


def downgrade() -> None:
    conn = op.get_bind()

    conn.execute(sa.text("DROP TRIGGER IF EXISTS trg_user_skill_agents_v2_modified_at ON user_skill_agents_v2"))
    conn.execute(sa.text("DROP FUNCTION IF EXISTS update_user_skill_agents_v2_modified_at"))
    conn.execute(sa.text("DROP TABLE IF EXISTS user_skill_agents_v2 CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS user_skill_versions_v2 CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS user_skills_v2 CASCADE"))
