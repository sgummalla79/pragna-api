"""
FastAPI application entry point.

Startup sequence:
  1. Validate required environment variables
  2. Open PostgreSQL pool + run Alembic migrations
  3. Load SkillRegistry from disk (SKILL.md files)
  4. Seed skills + agents into DB (idempotent)
  5. Compile one LangGraph graph per skill (entry point = intake)
  6. Mount all routers

Chat is handled outside LangGraph (conversations route).
Each skill invocation uses its own compiled graph with a fresh execution_id as thread_id.
"""

import os
import sys
import logging
import warnings

try:
    from langchain_core._api.deprecation import LangChainPendingDeprecationWarning
    warnings.filterwarnings("ignore", category=LangChainPendingDeprecationWarning)
except ImportError:
    pass
warnings.filterwarnings("ignore", message=".*allowed_objects.*")

from contextlib import asynccontextmanager
from pathlib import Path

import config  # noqa: F401 — loads .env before any os.getenv() at module level

from utils.log import configure_logging
configure_logging(level=os.getenv("LOG_LEVEL", "INFO"))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.middleware.request_logger import RequestLoggerMiddleware
from api.routes.health import router as health_router
from api.routes.auth import router as auth_router
from api.routes.providers import router as providers_router
from api.routes.skills import router as skills_router
from api.routes.agents import router as agents_router
from api.routes.conversations import router as conversations_router
from api.routes.executions import router as executions_router
from api.routes.artifacts import router as artifacts_router
from api.routes.usage import router as usage_router
from api.routes.uploads import router as uploads_router
from api.routes.settings import router as settings_router
from api.routes.models import router as models_router

from framework.engine import SkillEngine
from framework.registry import SkillRegistry
from persistence.db import get_db
from persistence.seed import seed_skills

_SKILLS_DIR = Path(__file__).parent.parent / "skills"

logger = logging.getLogger(__name__)


def _validate_env() -> None:
    missing = []

    secret = os.getenv("SETTINGS_SECRET", "")
    if not secret:
        missing.append("SETTINGS_SECRET")
    else:
        try:
            from cryptography.fernet import Fernet
            Fernet(secret.encode() if isinstance(secret, str) else secret)
        except Exception:
            logger.critical(
                "SETTINGS_SECRET is set but is not a valid Fernet key.\n"
                "Generate: python -c \"from cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())\""
            )
            sys.exit(1)

    if not os.getenv("JWT_SECRET") or os.getenv("JWT_SECRET") == "change-me-to-a-long-random-secret":
        missing.append("JWT_SECRET  (generate with: openssl rand -hex 32)")

    for var in ("AUTH0_DOMAIN", "AUTH0_CLIENT_ID", "AUTH0_CLIENT_SECRET"):
        if not os.getenv(var):
            missing.append(var)

    if not os.getenv("DATABASE_URL"):
        missing.append("DATABASE_URL")

    if missing:
        logger.critical(
            "Missing required environment variables: %s\n"
            "Copy .env.example to .env and fill in the required values.",
            ", ".join(missing),
        )
        sys.exit(1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("═" * 60)
    logger.info("Pragna  starting up")
    logger.info("═" * 60)

    _validate_env()

    async with get_db() as db:
        app.state.db = db
        logger.info("Database ready")

        # ── Skill registry ─────────────────────────────────────────────────
        skill_registry = SkillRegistry(_SKILLS_DIR)
        skill_registry.load_all()
        app.state.skill_registry = skill_registry
        logger.info("Skills loaded: %s", [s.manifest.id for s in skill_registry.list_all()])

        # ── Seed DB from disk ─────────────────────────────────────────────
        await seed_skills(db, skill_registry)

        # ── Load pricing cache ────────────────────────────────────────────
        from utils.pricing import load_pricing_cache
        await load_pricing_cache(db)
        logger.info("Pricing cache ready")

        # ── Compile graphs ─────────────────────────────────────────────────
        engine = SkillEngine()
        graphs: dict = {}
        for skill in skill_registry.list_all():
            graphs[skill.manifest.id] = engine.build(skill, db.checkpointer)
            logger.info("Graph compiled: %s", skill.manifest.id)

        app.state.graphs = graphs
        app.state.graph  = next(iter(graphs.values())) if graphs else None

        logger.info("═" * 60)
        logger.info("Pragna ready  skills=%d", len(graphs))
        logger.info("═" * 60)
        yield

    logger.info("Pragna shutting down")


app = FastAPI(
    title="Pragna API",
    version="1.0.0",
    description="""
## Pragna — Multi-Agent AI Platform

Pragna runs structured AI pipelines ("skills") to produce Architecture Recommendation Documents and supports free-form chat.

### Authentication
All `/api/*` endpoints require a valid session cookie (set via `/auth/callback` or `/auth/token`).
Auth routes (`/auth/*`) are public.

### SSE Streaming
Pipeline and chat endpoints return `text/event-stream`. Each event is a JSON object:
`data: {"type": "<event_type>", ...}`.

### Key Concepts
- **Skill** — a named multi-stage agent pipeline (e.g. `architect`)
- **Execution** — a single run of a skill pipeline, keyed by a UUID that doubles as the LangGraph thread_id
- **Artifact** — the document produced by the research stage of a skill pipeline
- **Conversation** — a chat session that may contain one or more skill executions
""",
    openapi_tags=[
        {"name": "Health",         "description": "Service health and version info"},
        {"name": "Auth",           "description": "Auth0 OAuth flow, session management"},
        {"name": "Conversations",  "description": "Create and manage chat conversations"},
        {"name": "Chat",           "description": "Free-form chat SSE streaming"},
        {"name": "Skills",         "description": "Skill discovery, install, validate, and agent config"},
        {"name": "Agents",         "description": "Agent prompt versioning and model assignment"},
        {"name": "Executions",     "description": "Start, reply, retry, and audit skill pipeline runs"},
        {"name": "Artifacts",      "description": "Access documents produced by skill pipelines"},
        {"name": "Providers",      "description": "LLM provider connection and model management"},
        {"name": "Models",         "description": "Active model list for UI dropdowns"},
        {"name": "Uploads",        "description": "File upload (documents and images) for pipeline intake"},
        {"name": "Usage",          "description": "Token usage and cost tracking"},
        {"name": "Settings",       "description": "User preferences (theme, etc.)"},
    ],
    lifespan=lifespan,
    swagger_ui_parameters={
        "supportedSubmitMethods": [],   # disables "Try it out" on every endpoint
        "defaultModelsExpandDepth": -1, # hides the Schemas section by default
    },
)

_ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Execution-Id"],
)
app.add_middleware(RequestLoggerMiddleware)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(providers_router)
app.include_router(skills_router)
app.include_router(agents_router)
app.include_router(conversations_router)
app.include_router(executions_router)
app.include_router(artifacts_router)
app.include_router(usage_router)
app.include_router(uploads_router)
app.include_router(settings_router)
app.include_router(models_router)
