"""v2 skill-level versioning — skill_versions, skill_version_agents, skill_drafts, skill_draft_agents

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-18
"""
from alembic import op
import sqlalchemy as sa

revision = '0014'
down_revision = '0013'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── skill_versions — global version snapshots per skill ───────────────────
    op.execute("""
        CREATE TABLE skill_versions (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            skill_id        UUID NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
            version_number  INTEGER NOT NULL,
            published_by    VARCHAR NOT NULL,
            published_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            notes           TEXT,
            UNIQUE (skill_id, version_number)
        )
    """)

    # ── skill_version_agents — agent snapshot at each version ─────────────────
    op.execute("""
        CREATE TABLE skill_version_agents (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            skill_version_id UUID NOT NULL REFERENCES skill_versions(id) ON DELETE CASCADE,
            agent_key        VARCHAR NOT NULL,
            content          TEXT NOT NULL,
            provider         VARCHAR,
            model            VARCHAR,
            UNIQUE (skill_version_id, agent_key)
        )
    """)

    # ── skill_drafts — one active draft per user per skill ────────────────────
    op.execute("""
        CREATE TABLE skill_drafts (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            skill_id            UUID NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
            user_id             VARCHAR NOT NULL,
            based_on_version_id UUID REFERENCES skill_versions(id) ON DELETE SET NULL,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (skill_id, user_id)
        )
    """)

    # ── skill_draft_agents — agent content inside a draft ─────────────────────
    op.execute("""
        CREATE TABLE skill_draft_agents (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            skill_draft_id UUID NOT NULL REFERENCES skill_drafts(id) ON DELETE CASCADE,
            agent_key     VARCHAR NOT NULL,
            content       TEXT NOT NULL,
            provider      VARCHAR,
            model         VARCHAR,
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (skill_draft_id, agent_key)
        )
    """)

    # ── Indexes ───────────────────────────────────────────────────────────────
    op.execute("CREATE INDEX idx_skill_versions_skill_id ON skill_versions(skill_id)")
    op.execute("CREATE INDEX idx_skill_drafts_user_id ON skill_drafts(user_id)")
    op.execute("CREATE INDEX idx_skill_draft_agents_draft_id ON skill_draft_agents(skill_draft_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS skill_draft_agents")
    op.execute("DROP TABLE IF EXISTS skill_drafts")
    op.execute("DROP TABLE IF EXISTS skill_version_agents")
    op.execute("DROP TABLE IF EXISTS skill_versions")
