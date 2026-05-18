"""fix user_llm_models — proper FK, rename columns, add modified_at

Changes:
  - provider_key (TEXT)  → user_llm_provider_id (UUID FK → user_llm_providers.id)
  - model_id             → model_name
  - isactive             → is_active
  - add modified_at column
  - update unique constraint

Revision ID: 0015
Revises: 0014
Create Date: 2026-05-18
"""
from alembic import op
import sqlalchemy as sa

revision = '0015'
down_revision = '0014'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── 1. Add user_llm_provider_id (nullable until populated) ────────────────
    conn.execute(sa.text("""
        ALTER TABLE user_llm_models
        ADD COLUMN user_llm_provider_id UUID
            REFERENCES user_llm_providers(id) ON DELETE CASCADE
    """))

    # ── 2. Populate FK from user_llm_providers matching user_id + key_name ────
    conn.execute(sa.text("""
        UPDATE user_llm_models m
        SET user_llm_provider_id = p.id
        FROM user_llm_providers p
        WHERE p.user_id  = m.user_id
          AND p.key_name = m.provider_key
    """))

    # ── 3. Drop rows with no matching provider (orphaned data) ────────────────
    conn.execute(sa.text("""
        DELETE FROM user_llm_models WHERE user_llm_provider_id IS NULL
    """))

    # ── 4. Enforce NOT NULL on FK ──────────────────────────────────────────────
    conn.execute(sa.text("""
        ALTER TABLE user_llm_models
        ALTER COLUMN user_llm_provider_id SET NOT NULL
    """))

    # ── 5. Rename model_id → model_name ───────────────────────────────────────
    conn.execute(sa.text("""
        ALTER TABLE user_llm_models RENAME COLUMN model_id TO model_name
    """))

    # ── 6. Rename isactive → is_active ────────────────────────────────────────
    conn.execute(sa.text("""
        ALTER TABLE user_llm_models RENAME COLUMN isactive TO is_active
    """))

    # ── 7. Add modified_at ────────────────────────────────────────────────────
    conn.execute(sa.text("""
        ALTER TABLE user_llm_models
        ADD COLUMN modified_at TIMESTAMPTZ NOT NULL DEFAULT now()
    """))

    # ── 8. Drop old provider_key column ───────────────────────────────────────
    conn.execute(sa.text("""
        ALTER TABLE user_llm_models DROP COLUMN provider_key
    """))

    # ── 9. Drop old unique constraint (by name or auto-generated) and add new ──
    conn.execute(sa.text("""
        DO $$
        DECLARE
            cname TEXT;
        BEGIN
            SELECT conname INTO cname
            FROM pg_constraint
            WHERE conrelid = 'user_llm_models'::regclass
              AND contype = 'u';
            IF cname IS NOT NULL THEN
                EXECUTE 'ALTER TABLE user_llm_models DROP CONSTRAINT ' || quote_ident(cname);
            END IF;
        END
        $$
    """))
    conn.execute(sa.text("""
        ALTER TABLE user_llm_models
        ADD CONSTRAINT uq_user_llm_models UNIQUE (user_llm_provider_id, model_name)
    """))

    # ── 10. Add trigger to auto-update modified_at on display_name change ─────
    conn.execute(sa.text("""
        CREATE OR REPLACE FUNCTION update_user_llm_models_modified_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.modified_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """))
    conn.execute(sa.text("""
        CREATE TRIGGER trg_user_llm_models_modified_at
        BEFORE UPDATE OF display_name ON user_llm_models
        FOR EACH ROW EXECUTE FUNCTION update_user_llm_models_modified_at()
    """))

    # ── 11. Update indexes ─────────────────────────────────────────────────────
    conn.execute(sa.text("DROP INDEX IF EXISTS idx_user_llm_models_provider"))
    conn.execute(sa.text("""
        CREATE INDEX idx_user_llm_models_provider_id
        ON user_llm_models (user_llm_provider_id)
    """))


def downgrade() -> None:
    conn = op.get_bind()

    conn.execute(sa.text("DROP TRIGGER IF EXISTS trg_user_llm_models_modified_at ON user_llm_models"))
    conn.execute(sa.text("DROP FUNCTION IF EXISTS update_user_llm_models_modified_at"))
    conn.execute(sa.text("DROP INDEX IF EXISTS idx_user_llm_models_provider_id"))

    conn.execute(sa.text("ALTER TABLE user_llm_models ADD COLUMN provider_key TEXT NOT NULL DEFAULT ''"))
    conn.execute(sa.text("""
        UPDATE user_llm_models m
        SET provider_key = p.key_name
        FROM user_llm_providers p
        WHERE p.id = m.user_llm_provider_id
    """))

    conn.execute(sa.text("ALTER TABLE user_llm_models DROP CONSTRAINT uq_user_llm_models"))
    conn.execute(sa.text("ALTER TABLE user_llm_models ADD CONSTRAINT uq_user_llm_models UNIQUE (user_id, provider_key, model_name)"))
    conn.execute(sa.text("ALTER TABLE user_llm_models DROP COLUMN modified_at"))
    conn.execute(sa.text("ALTER TABLE user_llm_models RENAME COLUMN is_active TO isactive"))
    conn.execute(sa.text("ALTER TABLE user_llm_models RENAME COLUMN model_name TO model_id"))
    conn.execute(sa.text("ALTER TABLE user_llm_models DROP COLUMN user_llm_provider_id"))
    conn.execute(sa.text("CREATE INDEX idx_user_llm_models_provider ON user_llm_models (user_id, provider_key)"))
