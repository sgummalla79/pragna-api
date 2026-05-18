"""create global llm_providers and llm_models catalog tables

Revision ID: 0023
Revises: 0022
Create Date: 2026-05-18
"""
from alembic import op
import sqlalchemy as sa

revision = '0023'
down_revision = '0022'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    conn.execute(sa.text("""
        CREATE TABLE llm_providers (
            id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            name        TEXT        NOT NULL UNIQUE,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            modified_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))

    conn.execute(sa.text("""
        CREATE TABLE llm_models (
            id                       UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            name                     TEXT        NOT NULL UNIQUE,
            input_usd_per_1m_tokens  NUMERIC(12,6) NOT NULL DEFAULT 0,
            output_usd_per_1m_tokens NUMERIC(12,6) NOT NULL DEFAULT 0,
            created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
            modified_at              TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))

    # Auto-update modified_at triggers
    conn.execute(sa.text("""
        CREATE OR REPLACE FUNCTION update_llm_providers_modified_at()
        RETURNS TRIGGER AS $$
        BEGIN NEW.modified_at = now(); RETURN NEW; END;
        $$ LANGUAGE plpgsql
    """))
    conn.execute(sa.text("""
        CREATE TRIGGER trg_llm_providers_modified_at
        BEFORE UPDATE ON llm_providers
        FOR EACH ROW EXECUTE FUNCTION update_llm_providers_modified_at()
    """))

    conn.execute(sa.text("""
        CREATE OR REPLACE FUNCTION update_llm_models_modified_at()
        RETURNS TRIGGER AS $$
        BEGIN NEW.modified_at = now(); RETURN NEW; END;
        $$ LANGUAGE plpgsql
    """))
    conn.execute(sa.text("""
        CREATE TRIGGER trg_llm_models_modified_at
        BEFORE UPDATE ON llm_models
        FOR EACH ROW EXECUTE FUNCTION update_llm_models_modified_at()
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP TRIGGER IF EXISTS trg_llm_models_modified_at ON llm_models"))
    conn.execute(sa.text("DROP FUNCTION IF EXISTS update_llm_models_modified_at"))
    conn.execute(sa.text("DROP TRIGGER IF EXISTS trg_llm_providers_modified_at ON llm_providers"))
    conn.execute(sa.text("DROP FUNCTION IF EXISTS update_llm_providers_modified_at"))
    conn.execute(sa.text("DROP TABLE IF EXISTS llm_models"))
    conn.execute(sa.text("DROP TABLE IF EXISTS llm_providers"))
