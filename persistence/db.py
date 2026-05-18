"""
Database context — Postgres connection pool + LangGraph checkpointer + repositories.

Startup sequence (called from api/app.py lifespan):
  1. Open AsyncConnectionPool
  2. Run Alembic migrations to latest
  3. Set up AsyncPostgresSaver for LangGraph
  4. Instantiate all repositories

All repositories share the same pool — no extra connections opened per repo.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass

from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from repositories.skill_repository import SkillRepository
from repositories.agent_repository import AgentRepository
from repositories.user_repository import UserRepository
from repositories.user_skill_repository import UserSkillRepository
from repositories.user_agent_repository import UserAgentRepository
from repositories.conversation_repository import ConversationRepository
from repositories.execution_repository import ExecutionRepository
from repositories.message_repository import MessageRepository
from repositories.artifact_repository import ArtifactRepository
from repositories.usage_repository import UsageRepository
from repositories.user_llm_models_repository import UserLLMModelsRepository
from repositories.model_pricing_repository import ModelPricingRepository
from repositories.model_catalog_repository import ModelCatalogRepository
from repositories.provider_registry_repository import ProviderRegistryRepository

log = logging.getLogger(__name__)


@dataclass
class DBContext:
    checkpointer: AsyncPostgresSaver
    pool:         AsyncConnectionPool

    # Repositories — each owns exactly one domain
    skills:        SkillRepository
    agents:        AgentRepository
    users:         UserRepository
    user_skills:   UserSkillRepository
    user_agents:   UserAgentRepository
    conversations: ConversationRepository
    executions:    ExecutionRepository
    messages:      MessageRepository
    artifacts:     ArtifactRepository
    usage:         UsageRepository
    llm_models:    UserLLMModelsRepository
    model_pricing:   ModelPricingRepository
    model_catalog:     ModelCatalogRepository
    provider_registry: ProviderRegistryRepository


@asynccontextmanager
async def get_db():
    from config import DATABASE_URL, DB_POOL_SIZE

    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not set. "
            "Copy backend/.env.example to backend/.env and configure the database URL."
        )

    log.info("Connecting to PostgreSQL …")

    async with AsyncConnectionPool(
        DATABASE_URL,
        min_size=1,
        max_size=DB_POOL_SIZE,
        kwargs={"autocommit": True},
        open=False,
    ) as pool:
        await pool.open(wait=True)
        log.info("PostgreSQL pool ready (max_size=%d)", DB_POOL_SIZE)

        # ── Run Alembic migrations ────────────────────────────────────────────
        _run_migrations(DATABASE_URL)

        # ── LangGraph checkpointer ────────────────────────────────────────────
        checkpointer = AsyncPostgresSaver(pool)
        await checkpointer.setup()
        log.info("LangGraph checkpointer ready")

        # ── Repositories ──────────────────────────────────────────────────────
        db = DBContext(
            checkpointer  = checkpointer,
            pool          = pool,
            skills        = SkillRepository(pool),
            agents        = AgentRepository(pool),
            users         = UserRepository(pool),
            user_skills   = UserSkillRepository(pool),
            user_agents   = UserAgentRepository(pool),
            conversations = ConversationRepository(pool),
            executions    = ExecutionRepository(pool),
            messages      = MessageRepository(pool),
            artifacts     = ArtifactRepository(pool),
            usage         = UsageRepository(pool),
            llm_models    = UserLLMModelsRepository(pool),
            model_pricing = ModelPricingRepository(pool),
            model_catalog     = ModelCatalogRepository(pool),
            provider_registry = ProviderRegistryRepository(pool),
        )

        log.info("DBContext ready — all repositories initialised")
        yield db


def _run_migrations(database_url: str) -> None:
    """Run Alembic migrations synchronously at startup."""
    from alembic.config import Config
    from alembic import command

    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    alembic_cfg = Config(os.path.join(backend_dir, "alembic.ini"))
    alembic_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    alembic_url = alembic_url.replace("postgres://", "postgresql+psycopg://", 1)
    alembic_cfg.set_main_option("sqlalchemy.url", alembic_url)
    alembic_cfg.set_main_option("script_location", os.path.join(backend_dir, "alembic"))

    log.info("Running Alembic migrations …")
    try:
        command.upgrade(alembic_cfg, "head")
    except Exception as exc:
        log.critical("Alembic migration failed: %s", exc, exc_info=True)
        raise
    log.info("Migrations complete")
