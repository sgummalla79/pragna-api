"""
Integration tests — repository CRUD against a real test DB.

Each test runs inside a transaction that rolls back on teardown.
Requires TEST_DATABASE_URL pointing to pragna_test database with migrations applied.
"""

import os
import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def pool():
    from psycopg_pool import AsyncConnectionPool
    url = os.getenv("TEST_DATABASE_URL", "postgresql://pragna:pragna@localhost:5432/pragna_test")
    async with AsyncConnectionPool(url, min_size=1, max_size=2, kwargs={"autocommit": True}, open=False) as p:
        await p.open(wait=True)
        # Truncate user-data tables before each test for clean state.
        # skills + agents are platform data managed separately.
        async with p.connection() as conn:
            await conn.execute("""
                TRUNCATE TABLE
                    token_usage, conversation_artifacts, conversation_messages,
                    conversation_skill_execution_stages, conversation_skill_executions,
                    conversation_skill_agents, conversation_skills, conversations,
                    user_agents_versions, user_agents, user_skills,
                    user_llm_providers, user_config, users
                CASCADE
            """)
        yield p


@pytest.mark.integration
async def test_skill_upsert_and_get(pool):
    from repositories.skill_repository import SkillRepository
    repo = SkillRepository(pool)

    skill = await repo.upsert("test-skill", "Test Skill", "A test skill", "🧪", 1)
    assert skill.skill_key == "test-skill"
    assert skill.name      == "Test Skill"
    assert skill.id

    fetched = await repo.get_by_key("test-skill")
    assert fetched.id == skill.id


@pytest.mark.integration
async def test_user_upsert_and_api_key(pool):
    from repositories.user_repository import UserRepository
    repo = UserRepository(pool)

    user = await repo.upsert("user-123", "test@example.com", "Test User", None)
    assert user.id    == "user-123"
    assert user.email == "test@example.com"

    await repo.save_llm_provider_key("user-123", "anthropic", "encrypted-key-value")
    keys = await repo.get_all_llm_provider_keys("user-123")
    assert "anthropic" in keys
    assert keys["anthropic"] == "encrypted-key-value"

    await repo.delete_llm_provider_key("user-123", "anthropic")
    keys_after = await repo.get_all_llm_provider_keys("user-123")
    assert "anthropic" not in keys_after


@pytest.mark.integration
async def test_conversation_create_and_list(pool):
    from repositories.user_repository import UserRepository
    from repositories.conversation_repository import ConversationRepository

    user_repo = UserRepository(pool)
    conv_repo = ConversationRepository(pool)

    await user_repo.upsert("user-conv-test", "conv@test.com", None, None)
    conv = await conv_repo.create("user-conv-test", "Test Conversation", "anthropic", "claude-sonnet-4-6")
    assert conv.id
    assert conv.title == "Test Conversation"

    listing = await conv_repo.list_for_user("user-conv-test")
    assert any(c.id == conv.id for c in listing)


@pytest.mark.integration
async def test_execution_create_and_complete(pool):
    """Full chain: user → conversation → conversation_skill → execution."""
    from repositories.user_repository import UserRepository
    from repositories.skill_repository import SkillRepository
    from repositories.conversation_repository import ConversationRepository
    from repositories.execution_repository import ExecutionRepository

    user_repo = UserRepository(pool)
    skill_repo = SkillRepository(pool)
    conv_repo  = ConversationRepository(pool)
    exec_repo  = ExecutionRepository(pool)

    await user_repo.upsert("user-exec-test", "exec@test.com", None, None)
    skill = await skill_repo.upsert("exec-skill", "Exec Skill", "desc", "⚡", 1)
    conv  = await conv_repo.create("user-exec-test", "Exec Conv", "anthropic", "claude-sonnet-4-6")

    conv_skill = await conv_repo.add_skill(conv.id, skill.id, [])
    execution  = await exec_repo.create(conv_skill.id)
    assert execution.status == "running"

    running = await exec_repo.get_running(conv.id)
    assert running and running.id == execution.id

    await exec_repo.complete(execution.id, "complete")
    completed = await exec_repo.get_by_id(execution.id)
    assert completed.status == "complete"

    no_running = await exec_repo.get_running(conv.id)
    assert no_running is None


@pytest.mark.integration
async def test_user_agent_versioning(pool):
    """Install skill, save draft, publish, verify current_version pointer."""
    from repositories.user_repository import UserRepository
    from repositories.skill_repository import SkillRepository
    from repositories.agent_repository import AgentRepository
    from repositories.user_agent_repository import UserAgentRepository

    user_repo  = UserRepository(pool)
    skill_repo = SkillRepository(pool)
    agent_repo = AgentRepository(pool)
    ua_repo    = UserAgentRepository(pool)

    await user_repo.upsert("user-ver-test", "ver@test.com", None, None)
    skill = await skill_repo.upsert("ver-skill", "Ver Skill", "desc", "⚡", 1)
    agent = await agent_repo.upsert(skill.id, "discovery", "Discovery Agent", "Default prompt")

    await ua_repo.install_skill_agents("user-ver-test", [agent])

    ua = await ua_repo.get("user-ver-test", agent.id)
    assert ua is not None
    assert ua.current_version == 1

    draft = await ua_repo.save_draft("user-ver-test", agent.id, "Updated prompt v2")
    assert draft.version == 2
    assert draft.status  == "draft"

    published = await ua_repo.publish("user-ver-test", agent.id)
    assert published.version == 2

    ua_after = await ua_repo.get("user-ver-test", agent.id)
    assert ua_after.current_version == 2
