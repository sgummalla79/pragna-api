"""
Shared pytest fixtures.

client:  full FastAPI app wired to pragna_test DB, auth dependency overridden.
pool:    raw psycopg pool for repository-level tests.
mock_db: lightweight mock DBContext (no DB needed).

The FastAPI lifespan (DB pool + migrations + graph compilation) is session-scoped —
it starts once for the entire test run and is torn down at the end. This prevents
connection exhaustion from spinning up a new pool (min_size=1, max_size=10) per test.
Between tests, only the data tables are truncated.
"""

import os
import pytest
import pytest_asyncio

TEST_DB_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://pragna:pragna_dev@localhost:5432/pragna_test",
)

# Must be set before any module-level imports that call os.getenv()
os.environ["DATABASE_URL"]        = TEST_DB_URL
os.environ["SETTINGS_SECRET"]     = "iKAvMwP3LI41X6jTI65qdetfjnnIVVrStE_9B4Q2-7U="
os.environ["JWT_SECRET"]          = "a" * 64
os.environ["AUTH0_DOMAIN"]        = "test.auth0.com"
os.environ["AUTH0_CLIENT_ID"]     = "test-client-id"
os.environ["AUTH0_CLIENT_SECRET"] = "test-client-secret"


_TRUNCATE_SQL = """
    TRUNCATE TABLE
        token_usage, conversation_artifacts, conversation_messages,
        conversation_skill_execution_stages, conversation_skill_executions,
        conversation_skill_agents, conversation_skills, conversations,
        user_agents_versions, user_agents, user_skills,
        user_llm_providers, user_config, users
    CASCADE
"""
# Note: skills + agents are platform data seeded by lifespan — never truncated.


# ── Shared user ───────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def fake_user():
    from utils.auth import AuthUser
    return AuthUser(sub="test-user-001", email="test@example.com", name="Test User")


# ── Session-scoped lifespan — starts once, shared across all tests ────────────

@pytest_asyncio.fixture(scope="session")
async def _app_session(fake_user):
    """
    Boots the FastAPI app (DB pool, migrations, graph compilation) once per
    test session. Yields the running app and its db state for reuse.
    """
    from api.app import app
    from utils.auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: fake_user

    async with app.router.lifespan_context(app):
        yield app

    app.dependency_overrides.clear()


# ── Full test client (real DB + mocked auth) ──────────────────────────────────

@pytest_asyncio.fixture
async def client(_app_session, fake_user):
    """
    Per-test AsyncClient. Reuses the session-scoped app (no new pool per test).
    Truncates all data tables before yielding so each test starts clean.
    """
    from httpx import AsyncClient, ASGITransport

    db = _app_session.state.db

    async with db.pool.connection() as conn:
        await conn.execute(_TRUNCATE_SQL)

    await db.users.upsert(fake_user.sub, fake_user.email, fake_user.name, None)

    async with AsyncClient(
        transport=ASGITransport(app=_app_session),
        base_url="http://test",
        headers={"Content-Type": "application/json"},
    ) as ac:
        yield ac


# ── Raw pool for repository-level tests ──────────────────────────────────────

@pytest_asyncio.fixture
async def pool():
    from psycopg_pool import AsyncConnectionPool
    async with AsyncConnectionPool(
        TEST_DB_URL, min_size=1, max_size=2,
        kwargs={"autocommit": True}, open=False,
    ) as p:
        await p.open(wait=True)
        async with p.connection() as conn:
            await conn.execute(_TRUNCATE_SQL)
        yield p


# ── Lightweight mock DB (no DB needed) ────────────────────────────────────────

@pytest.fixture
def mock_db():
    from unittest.mock import AsyncMock, MagicMock
    db = MagicMock()
    for repo in ("skills", "agents", "users", "user_skills", "user_agents",
                 "conversations", "executions", "messages", "artifacts", "usage"):
        setattr(db, repo, AsyncMock())
    return db
