"""Audit column standardisation and schema cleanup.

Changes:
  - Drop model_pricing table (pricing is stored in llm_models)
  - Drop all modified_at triggers (audit columns managed at code level going forward)
  - Add is_active to user_llm_providers (provider enable/disable)
  - conversations: rename last_modified → modified_at; change pinned INTEGER → BOOLEAN
  - conversation_messages: add modified_at; fix execution_id FK → skill_executions
  - conversation_artifacts: add modified_at; fix execution_id FK → skill_executions
  - user_token_usage: add modified_at
  - skill_executions: add created_at, modified_at

Revision ID: 0034
Revises: 0033
Create Date: 2026-05-18
"""
from alembic import op
import sqlalchemy as sa

revision = '0034'
down_revision = '0033'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── Drop model_pricing (pricing lives in llm_models) ──────────────────────
    conn.execute(sa.text("DROP TABLE IF EXISTS model_pricing CASCADE"))

    # ── Drop all existing modified_at triggers and their functions ────────────
    # Triggers are no longer used — audit timestamps are set at the Python code level.
    _drop_trigger(conn, "trg_skill_snapshots_modified_at",        "skill_snapshots")
    _drop_trigger(conn, "trg_skill_snapshot_agents_modified_at",  "skill_snapshot_agents")
    _drop_trigger(conn, "trg_llm_providers_modified_at",          "llm_providers")
    _drop_trigger(conn, "trg_llm_models_modified_at",             "llm_models")
    _drop_trigger(conn, "trg_users_modified_at",                  "users")
    _drop_trigger(conn, "trg_user_config_modified_at",            "user_config")
    _drop_trigger(conn, "trg_user_llm_providers_modified_at",     "user_llm_providers")
    _drop_trigger(conn, "trg_user_llm_models_modified_at",        "user_llm_models")
    _drop_trigger(conn, "trg_skills_modified_at",                 "skills")
    _drop_trigger(conn, "trg_skill_agents_modified_at",           "skill_agents")

    _drop_function(conn, "update_skill_snapshots_modified_at")
    _drop_function(conn, "update_skill_snapshot_agents_modified_at")
    _drop_function(conn, "update_llm_providers_modified_at")
    _drop_function(conn, "update_llm_models_modified_at")
    _drop_function(conn, "update_users_modified_at")
    _drop_function(conn, "update_user_config_modified_at")
    _drop_function(conn, "update_user_llm_providers_modified_at")
    _drop_function(conn, "update_user_llm_models_modified_at")
    _drop_function(conn, "update_skills_modified_at")
    _drop_function(conn, "update_skill_agents_modified_at")

    # ── user_llm_providers: add is_active ─────────────────────────────────────
    # Allows users to enable/disable a provider without deleting their key.
    conn.execute(sa.text(
        "ALTER TABLE user_llm_providers"
        " ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE"
    ))

    # ── conversations: rename last_modified → modified_at ─────────────────────
    conn.execute(sa.text(
        "ALTER TABLE conversations RENAME COLUMN last_modified TO modified_at"
    ))
    # Change pinned from INTEGER to BOOLEAN.
    # Must drop the integer DEFAULT before changing type — PostgreSQL cannot
    # auto-cast a literal integer default expression to boolean.
    conn.execute(sa.text(
        "ALTER TABLE conversations ALTER COLUMN pinned DROP DEFAULT"
    ))
    conn.execute(sa.text(
        "ALTER TABLE conversations"
        " ALTER COLUMN pinned TYPE BOOLEAN USING (pinned::boolean)"
    ))
    conn.execute(sa.text(
        "ALTER TABLE conversations ALTER COLUMN pinned SET DEFAULT FALSE"
    ))

    # ── conversation_messages: add modified_at; fix execution_id FK ───────────
    conn.execute(sa.text(
        "ALTER TABLE conversation_messages"
        " ADD COLUMN IF NOT EXISTS modified_at TIMESTAMPTZ NOT NULL DEFAULT now()"
    ))
    # Null out any execution_id values that are orphaned (their old table was dropped in 0033).
    # These rows pre-date the skill_executions table and cannot be re-linked.
    conn.execute(sa.text(
        "UPDATE conversation_messages SET execution_id = NULL"
        " WHERE execution_id IS NOT NULL"
        "   AND execution_id NOT IN (SELECT id FROM skill_executions)"
    ))
    # Drop old FK (may reference a dropped table name; IF EXISTS is safe)
    conn.execute(sa.text(
        "ALTER TABLE conversation_messages"
        " DROP CONSTRAINT IF EXISTS conversation_messages_execution_id_fkey"
    ))
    conn.execute(sa.text(
        "ALTER TABLE conversation_messages"
        " ADD CONSTRAINT conversation_messages_execution_id_fkey"
        " FOREIGN KEY (execution_id) REFERENCES skill_executions(id) ON DELETE SET NULL"
    ))

    # ── conversation_artifacts: add modified_at; fix execution_id FK ──────────
    conn.execute(sa.text(
        "ALTER TABLE conversation_artifacts"
        " ADD COLUMN IF NOT EXISTS modified_at TIMESTAMPTZ NOT NULL DEFAULT now()"
    ))
    # execution_id was NOT NULL in the original schema.  We must drop that constraint
    # before nulling out orphaned rows (rows whose execution existed only in the old
    # conversation_skill_executions table, which was dropped in migration 0033).
    # Going forward the column is nullable; new inserts always provide an execution_id.
    conn.execute(sa.text(
        "ALTER TABLE conversation_artifacts ALTER COLUMN execution_id DROP NOT NULL"
    ))
    conn.execute(sa.text(
        "UPDATE conversation_artifacts SET execution_id = NULL"
        " WHERE execution_id IS NOT NULL"
        "   AND execution_id NOT IN (SELECT id FROM skill_executions)"
    ))
    conn.execute(sa.text(
        "ALTER TABLE conversation_artifacts"
        " DROP CONSTRAINT IF EXISTS conversation_artifacts_execution_id_fkey"
    ))
    conn.execute(sa.text(
        "ALTER TABLE conversation_artifacts"
        " ADD CONSTRAINT conversation_artifacts_execution_id_fkey"
        " FOREIGN KEY (execution_id) REFERENCES skill_executions(id) ON DELETE CASCADE"
    ))

    # ── user_token_usage: add modified_at ─────────────────────────────────────
    conn.execute(sa.text(
        "ALTER TABLE user_token_usage"
        " ADD COLUMN IF NOT EXISTS modified_at TIMESTAMPTZ NOT NULL DEFAULT now()"
    ))

    # ── skill_executions: add created_at and modified_at ─────────────────────
    conn.execute(sa.text(
        "ALTER TABLE skill_executions"
        " ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now()"
    ))
    conn.execute(sa.text(
        "ALTER TABLE skill_executions"
        " ADD COLUMN IF NOT EXISTS modified_at TIMESTAMPTZ NOT NULL DEFAULT now()"
    ))


def downgrade() -> None:
    # Intentionally not reversing — trigger removal and column renames are not worth reverting.
    pass


# ── Helpers ───────────────────────────────────────────────────────────────────

def _drop_trigger(conn, trigger_name: str, table_name: str) -> None:
    """Drop a trigger if it exists, suppressing errors if it does not."""
    conn.execute(sa.text(
        f"DROP TRIGGER IF EXISTS {trigger_name} ON {table_name}"
    ))


def _drop_function(conn, function_name: str) -> None:
    """Drop a PL/pgSQL function if it exists."""
    conn.execute(sa.text(
        f"DROP FUNCTION IF EXISTS {function_name}()"
    ))
