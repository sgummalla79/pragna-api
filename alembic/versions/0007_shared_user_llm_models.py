"""rename user_api_keys to user_llm_providers and create user_llm_models

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-16
"""

from alembic import op
import sqlalchemy as sa

revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # Rename user_api_keys → user_llm_providers only if the old name still exists
    conn.execute(sa.text("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'user_api_keys'
            ) THEN
                ALTER TABLE user_api_keys RENAME TO user_llm_providers;
            END IF;
        END
        $$;
    """))

    # Create user_llm_models only if it doesn't exist yet
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS user_llm_models (
            id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id      TEXT        NOT NULL REFERENCES users(id),
            provider_key TEXT        NOT NULL,
            model_id     TEXT        NOT NULL,
            display_name TEXT        NOT NULL,
            isactive     BOOLEAN     NOT NULL DEFAULT false,
            created_at   TIMESTAMPTZ DEFAULT now(),
            CONSTRAINT uq_user_llm_models UNIQUE (user_id, provider_key, model_id)
        );
    """))

    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_user_llm_models_user     ON user_llm_models (user_id);"
    ))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_user_llm_models_active   ON user_llm_models (user_id, isactive);"
    ))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_user_llm_models_provider ON user_llm_models (user_id, provider_key);"
    ))


def downgrade() -> None:
    op.drop_index('idx_user_llm_models_provider', table_name='user_llm_models')
    op.drop_index('idx_user_llm_models_active',   table_name='user_llm_models')
    op.drop_index('idx_user_llm_models_user',     table_name='user_llm_models')
    op.drop_table('user_llm_models')
    op.rename_table('user_llm_providers', 'user_api_keys')
