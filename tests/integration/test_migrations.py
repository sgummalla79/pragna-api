"""
Integration test — Alembic migration applies cleanly to a fresh DB.

Requires a running PostgreSQL instance (pragna_test database).
Set TEST_DATABASE_URL env var to override the default.
"""

import os
import pytest


@pytest.mark.integration
async def test_migration_applies_cleanly():
    """Verify that migration 0001 creates all 16 expected tables."""
    from psycopg_pool import AsyncConnectionPool

    url = os.getenv("TEST_DATABASE_URL", "postgresql://pragna:pragna_dev@localhost:5432/pragna_test")

    async with AsyncConnectionPool(url, min_size=1, max_size=2, kwargs={"autocommit": True}, open=False) as pool:
        await pool.open(wait=True)

        # Run migrations
        from alembic.config import Config
        from alembic import command
        import pathlib

        backend_dir = pathlib.Path(__file__).parent.parent.parent
        alembic_cfg = Config(str(backend_dir / "alembic.ini"))
        alembic_cfg.set_main_option("sqlalchemy.url", url)
        alembic_cfg.set_main_option("script_location", str(backend_dir / "alembic"))
        command.upgrade(alembic_cfg, "head")

        # Verify all expected tables exist
        expected_tables = {
            "skills", "agents",
            "users", "user_llm_providers", "user_config", "user_skills",
            "user_agents", "user_agents_versions",
            "conversations", "conversation_skills", "conversation_skill_agents",
            "conversation_skill_executions", "conversation_skill_execution_stages",
            "conversation_messages", "conversation_artifacts",
            "token_usage", "user_llm_models",
            "model_pricing", "provider_catalog", "provider_registry",
        }

        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = 'public'"
            )
            rows       = await cur.fetchall()
            actual     = {r[0] for r in rows}
            missing    = expected_tables - actual
            assert not missing, f"Missing tables: {missing}"
