"""redesign user_llm_providers and user_llm_models — FK to global catalog tables

Changes:
  user_llm_providers: key_name+isactive → llm_provider_id FK, add created_at/modified_at
  user_llm_models: user_llm_provider_id+model_name → llm_model_id FK

Revision ID: 0024
Revises: 0023
Create Date: 2026-05-18
"""
from alembic import op
import sqlalchemy as sa

revision = '0024'
down_revision = '0023'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # Drop in dependency order (user_skill_agents references user_llm_models)
    conn.execute(sa.text("ALTER TABLE user_skill_agents DROP COLUMN IF EXISTS model_id"))
    conn.execute(sa.text("DROP TABLE IF EXISTS user_llm_models CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS user_llm_providers CASCADE"))

    # ── user_llm_providers ────────────────────────────────────────────────────
    conn.execute(sa.text("""
        CREATE TABLE user_llm_providers (
            id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id          TEXT        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            llm_provider_id  UUID        NOT NULL REFERENCES llm_providers(id) ON DELETE CASCADE,
            encrypted_value  TEXT        NOT NULL,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            modified_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (user_id, llm_provider_id)
        )
    """))

    conn.execute(sa.text("""
        CREATE OR REPLACE FUNCTION update_user_llm_providers_modified_at()
        RETURNS TRIGGER AS $$
        BEGIN NEW.modified_at = now(); RETURN NEW; END;
        $$ LANGUAGE plpgsql
    """))
    conn.execute(sa.text("""
        CREATE TRIGGER trg_user_llm_providers_modified_at
        BEFORE UPDATE OF encrypted_value ON user_llm_providers
        FOR EACH ROW EXECUTE FUNCTION update_user_llm_providers_modified_at()
    """))

    conn.execute(sa.text(
        "CREATE INDEX idx_user_llm_providers_user_id ON user_llm_providers(user_id)"
    ))

    # ── user_llm_models ───────────────────────────────────────────────────────
    conn.execute(sa.text("""
        CREATE TABLE user_llm_models (
            id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id         TEXT        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            llm_model_id    UUID        NOT NULL REFERENCES llm_models(id) ON DELETE CASCADE,
            display_name    TEXT        NOT NULL,
            is_active       BOOLEAN     NOT NULL DEFAULT FALSE,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            modified_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (user_id, llm_model_id)
        )
    """))

    conn.execute(sa.text("""
        CREATE OR REPLACE FUNCTION update_user_llm_models_modified_at()
        RETURNS TRIGGER AS $$
        BEGIN NEW.modified_at = now(); RETURN NEW; END;
        $$ LANGUAGE plpgsql
    """))
    conn.execute(sa.text("""
        CREATE TRIGGER trg_user_llm_models_modified_at
        BEFORE UPDATE OF is_active, display_name ON user_llm_models
        FOR EACH ROW EXECUTE FUNCTION update_user_llm_models_modified_at()
    """))

    conn.execute(sa.text(
        "CREATE INDEX idx_user_llm_models_user_id ON user_llm_models(user_id)"
    ))
    conn.execute(sa.text(
        "CREATE INDEX idx_user_llm_models_active ON user_llm_models(user_id, is_active)"
    ))

    # Add llm_provider_id to llm_models so we can query models by provider
    conn.execute(sa.text("""
        ALTER TABLE llm_models
        ADD COLUMN IF NOT EXISTS llm_provider_id UUID REFERENCES llm_providers(id) ON DELETE SET NULL
    """))

    # Re-add model_id FK on user_skill_agents pointing to new user_llm_models
    conn.execute(sa.text("""
        ALTER TABLE user_skill_agents
        ADD COLUMN model_id UUID REFERENCES user_llm_models(id) ON DELETE SET NULL
    """))


def downgrade() -> None:
    pass  # intentionally irreversible at this stage
