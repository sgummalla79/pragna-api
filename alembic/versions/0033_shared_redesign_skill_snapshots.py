"""redesign skill versioning — 7 tables → 3 (skill_snapshots, skill_snapshot_agents, skill_executions)

Drops:
  conversation_skill_execution_stages
  conversation_skill_executions
  conversation_skill_agents
  conversation_skills
  user_skill_agent_versions (user_skill_agents before rename)
  user_skill_versions
  user_skills

Creates:
  skill_snapshots   — draft / published / execution snapshots
  skill_snapshot_agents — agent content per snapshot
  skill_executions  — execution run lifecycle (renamed from conversation_skill_executions)

Revision ID: 0033
Revises: 0032
Create Date: 2026-05-18
"""
from alembic import op
import sqlalchemy as sa

revision = '0033'
down_revision = '0032'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── Drop old tables (dependency order) ────────────────────────────────────
    conn.execute(sa.text("DROP TABLE IF EXISTS conversation_skill_execution_stages CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS conversation_skill_executions CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS conversation_skill_agents CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS conversation_skills CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS user_skill_agent_versions CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS user_skill_versions CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS user_skills CASCADE"))

    # ── skill_snapshots ───────────────────────────────────────────────────────
    conn.execute(sa.text("""
        CREATE TABLE skill_snapshots (
            id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id         TEXT        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            skill_id        UUID        NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
            version_number  INT         NOT NULL DEFAULT 1,
            type            VARCHAR     NOT NULL CHECK (type IN ('draft','published','execution')),
            conversation_id UUID        REFERENCES conversations(id) ON DELETE SET NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            modified_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (user_id, skill_id, version_number)
        )
    """))

    conn.execute(sa.text(
        "CREATE INDEX idx_skill_snapshots_user_skill ON skill_snapshots(user_id, skill_id)"
    ))
    conn.execute(sa.text(
        "CREATE INDEX idx_skill_snapshots_type ON skill_snapshots(user_id, skill_id, type)"
    ))
    conn.execute(sa.text(
        "CREATE INDEX idx_skill_snapshots_published ON skill_snapshots(user_id, skill_id, type, version_number DESC)"
    ))
    conn.execute(sa.text(
        "CREATE INDEX idx_skill_snapshots_conversation ON skill_snapshots(conversation_id)"
    ))

    conn.execute(sa.text("""
        CREATE OR REPLACE FUNCTION update_skill_snapshots_modified_at()
        RETURNS TRIGGER AS $$
        BEGIN NEW.modified_at = now(); RETURN NEW; END;
        $$ LANGUAGE plpgsql
    """))
    conn.execute(sa.text("""
        CREATE TRIGGER trg_skill_snapshots_modified_at
        BEFORE UPDATE ON skill_snapshots
        FOR EACH ROW EXECUTE FUNCTION update_skill_snapshots_modified_at()
    """))

    # ── skill_snapshot_agents ─────────────────────────────────────────────────
    conn.execute(sa.text("""
        CREATE TABLE skill_snapshot_agents (
            id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            snapshot_id    UUID        NOT NULL REFERENCES skill_snapshots(id) ON DELETE CASCADE,
            skill_agent_id UUID        NOT NULL REFERENCES skill_agents(id) ON DELETE CASCADE,
            content        TEXT        NOT NULL,
            model_id       UUID        REFERENCES user_llm_models(id) ON DELETE SET NULL,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            modified_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (snapshot_id, skill_agent_id)
        )
    """))

    conn.execute(sa.text(
        "CREATE INDEX idx_skill_snapshot_agents ON skill_snapshot_agents(snapshot_id)"
    ))

    conn.execute(sa.text("""
        CREATE OR REPLACE FUNCTION update_skill_snapshot_agents_modified_at()
        RETURNS TRIGGER AS $$
        BEGIN NEW.modified_at = now(); RETURN NEW; END;
        $$ LANGUAGE plpgsql
    """))
    conn.execute(sa.text("""
        CREATE TRIGGER trg_skill_snapshot_agents_modified_at
        BEFORE UPDATE OF content ON skill_snapshot_agents
        FOR EACH ROW EXECUTE FUNCTION update_skill_snapshot_agents_modified_at()
    """))

    # ── skill_executions ──────────────────────────────────────────────────────
    conn.execute(sa.text("""
        CREATE TABLE skill_executions (
            id           UUID        PRIMARY KEY,
            snapshot_id  UUID        NOT NULL REFERENCES skill_snapshots(id) ON DELETE CASCADE,
            status       TEXT        NOT NULL CHECK (status IN ('running','complete','halted','error','invalid_input')),
            started_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            completed_at TIMESTAMPTZ
        )
    """))

    conn.execute(sa.text(
        "CREATE INDEX idx_skill_executions_snapshot ON skill_executions(snapshot_id)"
    ))
    conn.execute(sa.text(
        "CREATE INDEX idx_skill_executions_status ON skill_executions(snapshot_id, status)"
    ))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP TRIGGER IF EXISTS trg_skill_snapshot_agents_modified_at ON skill_snapshot_agents"))
    conn.execute(sa.text("DROP FUNCTION IF EXISTS update_skill_snapshot_agents_modified_at"))
    conn.execute(sa.text("DROP TRIGGER IF EXISTS trg_skill_snapshots_modified_at ON skill_snapshots"))
    conn.execute(sa.text("DROP FUNCTION IF EXISTS update_skill_snapshots_modified_at"))
    conn.execute(sa.text("DROP TABLE IF EXISTS skill_executions CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS skill_snapshot_agents CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS skill_snapshots CASCADE"))
