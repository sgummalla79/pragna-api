"""
Additional integration tests for repository methods not covered in the main test file.
Covers: artifact, message, usage, execution stages, conversation skill config.
"""

import os
import pytest
import pytest_asyncio

TEST_DB_URL = os.getenv("TEST_DATABASE_URL", "postgresql://pragna:pragna_dev@localhost:5432/pragna_test")

_TRUNCATE_SQL = """
    TRUNCATE TABLE
        token_usage, conversation_artifacts, conversation_messages,
        conversation_skill_execution_stages, conversation_skill_executions,
        conversation_skill_agents, conversation_skills, conversations,
        user_agents_versions, user_agents, user_skills,
        user_llm_providers, user_config, users
    CASCADE
"""


@pytest_asyncio.fixture
async def pool():
    from psycopg_pool import AsyncConnectionPool
    async with AsyncConnectionPool(TEST_DB_URL, min_size=1, max_size=2,
                                   kwargs={"autocommit": True}, open=False) as p:
        await p.open(wait=True)
        async with p.connection() as conn:
            await conn.execute(_TRUNCATE_SQL)
        yield p


async def _setup_base(pool):
    """Create a conversation with a running execution — shared fixture helper."""
    from repositories.user_repository import UserRepository
    from repositories.skill_repository import SkillRepository
    from repositories.conversation_repository import ConversationRepository
    from repositories.execution_repository import ExecutionRepository

    user_repo  = UserRepository(pool)
    skill_repo = SkillRepository(pool)
    conv_repo  = ConversationRepository(pool)
    exec_repo  = ExecutionRepository(pool)

    await user_repo.upsert("u-ext", "ext@test.com", None, None)
    skill = await skill_repo.get_by_key("architect")   # seeded at startup
    if not skill:
        skill = await skill_repo.upsert("architect", "Architect", "desc", "⚡", 1)
    conv      = await conv_repo.create("u-ext", "Test", "anthropic", "claude-sonnet-4-6")
    cs        = await conv_repo.add_skill(conv.id, skill.id, [])
    execution = await exec_repo.create(cs.id)
    return conv, cs, execution


@pytest.mark.integration
async def test_artifact_create_and_get(pool):
    from repositories.artifact_repository import ArtifactRepository
    conv, cs, execution = await _setup_base(pool)
    repo = ArtifactRepository(pool)

    artifact = await repo.create(conv.id, execution.id, "# Architecture v1", 1, "pending_review")
    assert artifact.id
    assert artifact.version == 1
    assert artifact.status  == "pending_review"

    fetched = await repo.get_by_id(artifact.id)
    assert fetched.id      == artifact.id
    assert fetched.content == "# Architecture v1"


@pytest.mark.integration
async def test_artifact_update_status(pool):
    from repositories.artifact_repository import ArtifactRepository
    conv, cs, execution = await _setup_base(pool)
    repo = ArtifactRepository(pool)

    artifact = await repo.create(conv.id, execution.id, "# Doc", 1, "pending_review")
    await repo.update_status(artifact.id, "approved")

    updated = await repo.get_by_id(artifact.id)
    assert updated.status == "approved"


@pytest.mark.integration
async def test_artifact_get_latest(pool):
    from repositories.artifact_repository import ArtifactRepository
    conv, cs, execution = await _setup_base(pool)
    repo = ArtifactRepository(pool)

    await repo.create(conv.id, execution.id, "v1", 1, "review_failed")
    await repo.create(conv.id, execution.id, "v2", 2, "approved")

    latest = await repo.get_latest(execution.id)
    assert latest.version == 2


@pytest.mark.integration
async def test_artifact_list_for_execution(pool):
    from repositories.artifact_repository import ArtifactRepository
    conv, cs, execution = await _setup_base(pool)
    repo = ArtifactRepository(pool)

    await repo.create(conv.id, execution.id, "v1", 1, "review_failed")
    await repo.create(conv.id, execution.id, "v2", 2, "approved")

    artifacts = await repo.list_for_execution(execution.id)
    assert len(artifacts) == 2
    assert artifacts[0].version == 1
    assert artifacts[1].version == 2


@pytest.mark.integration
async def test_message_create_and_list(pool):
    from repositories.message_repository import MessageRepository
    conv, cs, execution = await _setup_base(pool)
    repo = MessageRepository(pool)

    msg = await repo.create(conv.id, "user", "Hello!", "chat", "visible",
                            execution_id=None, artifact_id=None)
    assert msg.id
    assert msg.role         == "user"
    assert msg.message_type == "chat"

    messages = await repo.list_for_conversation(conv.id)
    assert any(m.id == msg.id for m in messages)


@pytest.mark.integration
async def test_message_visible_only_filter(pool):
    from repositories.message_repository import MessageRepository
    conv, cs, execution = await _setup_base(pool)
    repo = MessageRepository(pool)

    await repo.create(conv.id, "assistant", "Raw output", "stage_summary", "hidden")
    await repo.create(conv.id, "assistant", "Summary", "stage_summary", "visible")

    all_msgs     = await repo.list_for_conversation(conv.id, visible_only=False)
    visible_msgs = await repo.list_for_conversation(conv.id, visible_only=True)

    assert len(all_msgs)     == 2
    assert len(visible_msgs) == 1
    assert visible_msgs[0].content == "Summary"


@pytest.mark.integration
async def test_usage_record_and_retrieve(pool):
    from repositories.usage_repository import UsageRepository
    conv, cs, execution = await _setup_base(pool)
    repo = UsageRepository(pool)

    await repo.record(conv.id, "anthropic", "claude-sonnet-4-6", 1000, 500)
    await repo.record(conv.id, "perplexity", "sonar-pro", 800, 300)

    stats = await repo.get_by_conversation(conv.id)
    assert stats.input_tokens  == 1800
    assert stats.output_tokens == 800
    assert stats.cost_usd      >= 0
    assert len(stats.breakdown) == 2


@pytest.mark.integration
async def test_execution_record_and_get_stages(pool):
    from repositories.execution_repository import ExecutionRepository
    conv, cs, execution = await _setup_base(pool)
    repo = ExecutionRepository(pool)

    await repo.record_stage(execution.id, "discovery", "anthropic", "claude-sonnet-4-6", "success")
    await repo.record_stage(execution.id, "research",  "perplexity", "sonar-pro",         "success")
    await repo.record_stage(execution.id, "review",    "anthropic", "claude-sonnet-4-6", "failed")

    stages = await repo.get_stages(execution.id)
    assert len(stages) == 3
    assert stages[0].agent_key == "discovery"
    assert stages[2].status    == "failed"


@pytest.mark.integration
async def test_execution_list_for_skill(pool):
    from repositories.execution_repository import ExecutionRepository
    conv, cs, execution = await _setup_base(pool)
    repo = ExecutionRepository(pool)

    await repo.complete(execution.id, "complete")
    exec2 = await repo.create(cs.id)

    all_execs = await repo.list_for_skill(cs.id)
    assert len(all_execs) == 2

    running = await repo.get_running(conv.id)
    assert running is not None
    assert running.id == exec2.id


@pytest.mark.integration
async def test_conversation_update_agent_model(pool):
    from repositories.conversation_repository import ConversationRepository
    from repositories.skill_repository import SkillRepository
    from repositories.user_repository import UserRepository
    from repositories.agent_repository import AgentRepository

    ur = UserRepository(pool)
    sr = SkillRepository(pool)
    cr = ConversationRepository(pool)
    ar = AgentRepository(pool)

    await ur.upsert("u-model", "model@test.com", None, None)
    skill = await sr.get_by_key("architect")
    if not skill:
        skill = await sr.upsert("architect", "Architect", "desc", "⚡", 1)

    conv = await cr.create("u-model", "Model Test", "anthropic", "claude-sonnet-4-6")
    agents = await ar.get_by_skill(skill.id)

    agent_data = [{
        "agent_id": a.id, "version": 1, "content": "prompt", "provider": None, "model": None
    } for a in agents[:1]]

    cs = await cr.add_skill(conv.id, skill.id, agent_data)
    csa_list = await cr.get_skill_agents(cs.id)
    csa = csa_list[0]

    await cr.update_agent_model(csa.id, "google", "gemini-2.5-pro")

    updated = await cr.get_skill_agents(cs.id)
    assert updated[0].provider == "google"
    assert updated[0].model    == "gemini-2.5-pro"
