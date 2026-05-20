"""
Database context — Postgres pool + LangGraph checkpointer + repositories + services.

Startup sequence (called from api/app.py lifespan):
  1. Open AsyncConnectionPool
  2. Run Alembic migrations to latest
  3. Set up AsyncPostgresSaver for LangGraph
  4. Instantiate all repositories (pure CRUD, one per table domain)
  5. Instantiate all services (business logic, injected with repositories)
  6. Load the pricing cache from llm_models

Dependency direction: Routes → Services → Repositories → Database.
Routes access app.state.services for business operations and
app.state.db only for the checkpointer and direct repo access where needed.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass

from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

# ── Repository imports ────────────────────────────────────────────────────────
from repositories.user_repository import UserRepository
from repositories.user_llm_provider_repository import UserLLMProviderRepository
from repositories.user_llm_model_repository import UserLLMModelRepository
from repositories.user_config_repository import UserConfigRepository
from repositories.conversation_repository import ConversationRepository
from repositories.message_repository import MessageRepository
from repositories.artifact_repository import ArtifactRepository
from repositories.skill_repository import SkillRepository
from repositories.agent_repository import AgentRepository
from repositories.skill_snapshot_repository import SkillSnapshotRepository
from repositories.skill_execution_repository import SkillExecutionRepository
from repositories.llm_provider_repository import LLMProviderRepository
from repositories.llm_model_repository import LLMModelRepository
from repositories.usage_repository import UsageRepository

# ── Service imports ───────────────────────────────────────────────────────────
from services.pricing_service import PricingService
from services.usage_service import UsageService
from services.provider_service import ProviderService
from services.llm_model_service import LLMModelService
from services.skill_service import SkillService
from services.conversation_service import ConversationService
from services.execution_service import ExecutionService

log = logging.getLogger(__name__)


@dataclass
class DBContext:
    """
    Holds the connection pool, LangGraph checkpointer, and all repository instances.

    Repositories are pure CRUD — they contain no business logic. For business
    operations, use AppServices instead.
    """
    checkpointer: AsyncPostgresSaver
    pool:         AsyncConnectionPool

    # Repositories — each owns exactly one table domain
    users:            UserRepository
    user_providers:   UserLLMProviderRepository
    user_llm_models:  UserLLMModelRepository
    user_config:      UserConfigRepository
    conversations:    ConversationRepository
    messages:         MessageRepository
    artifacts:        ArtifactRepository
    skills:           SkillRepository
    agents:           AgentRepository
    skill_snapshots:  SkillSnapshotRepository
    skill_executions: SkillExecutionRepository
    llm_providers:    LLMProviderRepository
    llm_models:       LLMModelRepository
    usage:            UsageRepository


@dataclass
class AppServices:
    """
    Holds all service layer instances — instantiated once at startup.

    Services contain all business logic and orchestration. They are injected
    with repository instances at construction time.
    Routes call services; services call repositories.
    """
    pricing:       PricingService
    usage:         UsageService
    providers:     ProviderService
    llm_models:    LLMModelService
    skills:        SkillService
    conversations: ConversationService
    executions:    ExecutionService


@asynccontextmanager
async def get_db():
    """
    Async context manager that opens the pool, runs migrations, and yields
    a fully initialised (DBContext, AppServices) pair.

    Usage in app lifespan:
        async with get_db() as (db, services):
            app.state.db = db
            app.state.services = services
    """
    from config import DATABASE_URL, DB_POOL_SIZE

    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not set. "
            "Copy .env.example to .env and configure the database URL."
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

        # ── Instantiate repositories ──────────────────────────────────────────
        users            = UserRepository(pool)
        user_providers   = UserLLMProviderRepository(pool)
        user_llm_models  = UserLLMModelRepository(pool)
        user_config      = UserConfigRepository(pool)
        conversations    = ConversationRepository(pool)
        messages         = MessageRepository(pool)
        artifacts        = ArtifactRepository(pool)
        skills           = SkillRepository(pool)
        agents           = AgentRepository(pool)
        skill_snapshots  = SkillSnapshotRepository(pool)
        skill_executions = SkillExecutionRepository(pool)
        llm_providers    = LLMProviderRepository(pool)
        llm_models       = LLMModelRepository(pool)
        usage            = UsageRepository(pool)

        db = DBContext(
            checkpointer     = checkpointer,
            pool             = pool,
            users            = users,
            user_providers   = user_providers,
            user_llm_models  = user_llm_models,
            user_config      = user_config,
            conversations    = conversations,
            messages         = messages,
            artifacts        = artifacts,
            skills           = skills,
            agents           = agents,
            skill_snapshots  = skill_snapshots,
            skill_executions = skill_executions,
            llm_providers    = llm_providers,
            llm_models       = llm_models,
            usage            = usage,
        )

        # ── Instantiate services ──────────────────────────────────────────────
        pricing_svc = PricingService()
        await pricing_svc.load_cache(llm_models)

        app_services = AppServices(
            pricing = pricing_svc,
            usage   = UsageService(usage, pricing_svc),
            providers = ProviderService(
                llm_provider_repo      = llm_providers,
                user_llm_provider_repo = user_providers,
                user_llm_model_repo    = user_llm_models,
                user_config_repo       = user_config,
            ),
            llm_models = LLMModelService(
                llm_provider_repo   = llm_providers,
                llm_model_repo      = llm_models,
                user_llm_model_repo = user_llm_models,
            ),
            skills = SkillService(
                skill_repo    = skills,
                agent_repo    = agents,
                snapshot_repo = skill_snapshots,
            ),
            conversations = ConversationService(
                conversation_repo = conversations,
                skill_repo        = skills,
                agent_repo        = agents,
                snapshot_repo     = skill_snapshots,
            ),
            executions = ExecutionService(
                agent_repo      = agents,
                snapshot_repo   = skill_snapshots,
                execution_repo  = skill_executions,
                user_model_repo = user_llm_models,
            ),
        )

        log.info("DBContext and AppServices ready")
        yield db, app_services


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
