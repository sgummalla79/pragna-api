"""Initial schema — all 16 application tables.

Revision ID: 0001
Revises:
Create Date: 2026-05-14
"""

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    # ── Platform tables ───────────────────────────────────────────────────────

    op.execute("""
        CREATE TABLE IF NOT EXISTS skills (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            skill_key   TEXT UNIQUE NOT NULL,
            name        TEXT NOT NULL,
            description TEXT,
            icon        TEXT DEFAULT '⚡',
            version     INTEGER DEFAULT 1,
            created_at  TIMESTAMPTZ DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS agents (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            skill_id        UUID NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
            agent_key       TEXT NOT NULL,
            label           TEXT,
            default_content TEXT NOT NULL,
            created_at      TIMESTAMPTZ DEFAULT now(),
            UNIQUE(skill_id, agent_key)
        )
    """)

    # ── User tables ───────────────────────────────────────────────────────────

    op.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id         TEXT PRIMARY KEY,
            email      TEXT UNIQUE NOT NULL,
            name       TEXT,
            picture    TEXT,
            created_at TIMESTAMPTZ DEFAULT now(),
            last_login TIMESTAMPTZ
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS user_api_keys (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id         TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            key_name        TEXT NOT NULL,
            encrypted_value TEXT NOT NULL,
            updated_at      TIMESTAMPTZ DEFAULT now(),
            UNIQUE(user_id, key_name)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS user_config (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            key        TEXT NOT NULL,
            value      TEXT NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT now(),
            UNIQUE(user_id, key)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS user_skills (
            user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            skill_id     UUID NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
            installed_at TIMESTAMPTZ DEFAULT now(),
            PRIMARY KEY(user_id, skill_id)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS user_agents (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id         TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            agent_id        UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
            current_version INTEGER NOT NULL DEFAULT 1,
            provider_to_use TEXT,
            model_to_use    TEXT,
            created_at      TIMESTAMPTZ DEFAULT now(),
            UNIQUE(user_id, agent_id)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS user_agents_versions (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_agent_id UUID NOT NULL REFERENCES user_agents(id) ON DELETE CASCADE,
            version       INTEGER NOT NULL,
            content       TEXT NOT NULL,
            status        TEXT NOT NULL CHECK(status IN ('draft', 'published')),
            created_at    TIMESTAMPTZ DEFAULT now(),
            published_at  TIMESTAMPTZ,
            UNIQUE(user_agent_id, version)
        )
    """)

    # ── Conversation tables ───────────────────────────────────────────────────

    op.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id       TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title         TEXT,
            chat_provider TEXT,
            chat_model    TEXT,
            created_at    TIMESTAMPTZ DEFAULT now(),
            last_modified TIMESTAMPTZ DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS conversation_skills (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            skill_id        UUID NOT NULL REFERENCES skills(id),
            added_at        TIMESTAMPTZ DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS conversation_skill_agents (
            id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            conversation_skill_id UUID NOT NULL REFERENCES conversation_skills(id) ON DELETE CASCADE,
            agent_id              UUID NOT NULL REFERENCES agents(id),
            version               INTEGER NOT NULL,
            content               TEXT NOT NULL,
            provider              TEXT,
            model                 TEXT
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS conversation_skill_executions (
            id                    UUID PRIMARY KEY,
            conversation_skill_id UUID NOT NULL REFERENCES conversation_skills(id) ON DELETE CASCADE,
            status                TEXT NOT NULL CHECK(status IN ('running', 'complete', 'halted')),
            started_at            TIMESTAMPTZ DEFAULT now(),
            completed_at          TIMESTAMPTZ
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS conversation_skill_execution_stages (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            execution_id UUID NOT NULL REFERENCES conversation_skill_executions(id) ON DELETE CASCADE,
            agent_key    TEXT NOT NULL,
            provider     TEXT,
            model        TEXT,
            status       TEXT NOT NULL CHECK(status IN ('success', 'failed')),
            ran_at       TIMESTAMPTZ DEFAULT now()
        )
    """)

    # conversation_messages and conversation_artifacts reference each other,
    # so we create messages first with a nullable artifact_id, then add the FK after artifacts.
    op.execute("""
        CREATE TABLE IF NOT EXISTS conversation_messages (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            execution_id    UUID REFERENCES conversation_skill_executions(id) ON DELETE SET NULL,
            role            TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
            content         TEXT,
            message_type    TEXT NOT NULL CHECK(message_type IN (
                'chat', 'stage_summary', 'question', 'user_answer', 'confirmation', 'artifact_ref'
            )),
            message_state   TEXT NOT NULL CHECK(message_state IN ('visible', 'hidden')),
            artifact_id     UUID,
            created_at      TIMESTAMPTZ DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS conversation_artifacts (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            execution_id    UUID NOT NULL REFERENCES conversation_skill_executions(id) ON DELETE CASCADE,
            artifact_type   TEXT NOT NULL DEFAULT 'document',
            content         TEXT NOT NULL,
            version         INTEGER NOT NULL,
            status          TEXT NOT NULL CHECK(status IN (
                'pending_review', 'review_failed', 'review_passed', 'approval_rejected', 'approved'
            )),
            created_at      TIMESTAMPTZ DEFAULT now()
        )
    """)

    op.execute("""
        ALTER TABLE conversation_messages
            ADD CONSTRAINT fk_message_artifact
            FOREIGN KEY (artifact_id) REFERENCES conversation_artifacts(id) ON DELETE SET NULL
    """)

    # ── Billing ───────────────────────────────────────────────────────────────
    # Drop token_usage if it exists with the old schema (missing conversation_id)
    # so the correct schema is always applied regardless of prior state.
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'token_usage'
            ) AND NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'token_usage' AND column_name = 'conversation_id'
            ) THEN
                DROP TABLE token_usage CASCADE;
            END IF;
        END $$;
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS token_usage (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            provider        TEXT,
            model           TEXT,
            input_tokens    INTEGER DEFAULT 0,
            output_tokens   INTEGER DEFAULT 0,
            cost_usd        REAL DEFAULT 0,
            created_at      TIMESTAMPTZ DEFAULT now()
        )
    """)

    # ── Indexes ───────────────────────────────────────────────────────────────

    op.execute("CREATE INDEX IF NOT EXISTS idx_conversations_user       ON conversations(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_conv_skills_conv         ON conversation_skills(conversation_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_conv_skill_agents_cs     ON conversation_skill_agents(conversation_skill_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_executions_cs            ON conversation_skill_executions(conversation_skill_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_stages_execution         ON conversation_skill_execution_stages(execution_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_messages_conversation    ON conversation_messages(conversation_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_messages_execution       ON conversation_messages(execution_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_artifacts_execution      ON conversation_artifacts(execution_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_token_usage_conversation ON token_usage(conversation_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_user_agents_user         ON user_agents(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_user_agents_versions_ua  ON user_agents_versions(user_agent_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS token_usage CASCADE")
    op.execute("ALTER TABLE conversation_messages DROP CONSTRAINT IF EXISTS fk_message_artifact")
    op.execute("DROP TABLE IF EXISTS conversation_artifacts CASCADE")
    op.execute("DROP TABLE IF EXISTS conversation_messages CASCADE")
    op.execute("DROP TABLE IF EXISTS conversation_skill_execution_stages CASCADE")
    op.execute("DROP TABLE IF EXISTS conversation_skill_executions CASCADE")
    op.execute("DROP TABLE IF EXISTS conversation_skill_agents CASCADE")
    op.execute("DROP TABLE IF EXISTS conversation_skills CASCADE")
    op.execute("DROP TABLE IF EXISTS conversations CASCADE")
    op.execute("DROP TABLE IF EXISTS user_agents_versions CASCADE")
    op.execute("DROP TABLE IF EXISTS user_agents CASCADE")
    op.execute("DROP TABLE IF EXISTS user_skills CASCADE")
    op.execute("DROP TABLE IF EXISTS user_config CASCADE")
    op.execute("DROP TABLE IF EXISTS user_api_keys CASCADE")
    op.execute("DROP TABLE IF EXISTS users CASCADE")
    op.execute("DROP TABLE IF EXISTS agents CASCADE")
    op.execute("DROP TABLE IF EXISTS skills CASCADE")
