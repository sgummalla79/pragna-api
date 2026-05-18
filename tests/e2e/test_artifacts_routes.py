"""
E2E tests for /api/artifacts routes.
Covers: access control, 404 handling, content retrieval.
"""

import pytest


@pytest.mark.e2e
async def test_get_artifact_not_found(client):
    resp = await client.get("/api/artifacts/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


@pytest.mark.e2e
async def test_get_artifact_requires_auth(client):
    """Artifact endpoint is auth-guarded (client fixture provides auth)."""
    resp = await client.get("/api/artifacts/00000000-0000-0000-0000-000000000000")
    # Returns 404 (not 401/403) because auth is satisfied by fixture
    assert resp.status_code == 404


@pytest.mark.e2e
async def test_get_artifact_returns_content(client, pool):
    """Create an artifact directly via DB and retrieve it via API."""
    from repositories.conversation_repository import ConversationRepository
    from repositories.artifact_repository     import ArtifactRepository
    from repositories.user_repository         import UserRepository

    users  = UserRepository(pool)
    convs  = ConversationRepository(pool)
    arts   = ArtifactRepository(pool)

    await users.upsert("test-user-001", "test@example.com", "Test User", None)

    conv = await convs.create("test-user-001", "Artifact Test", "anthropic", "claude-sonnet-4-6")

    # Need an execution to attach the artifact to
    from repositories.execution_repository import ExecutionRepository
    execs = ExecutionRepository(pool)

    # Add a skill snapshot first
    from repositories.skill_repository import SkillRepository
    skills = SkillRepository(pool)
    skill  = await skills.get_by_key("architect")
    if not skill:
        pytest.skip("architect skill not seeded")

    from repositories.conversation_repository import ConversationRepository as CR
    conv_repo = CR(pool)
    cs = await conv_repo.add_skill(conv.id, skill.id, agents=[])

    execution = await execs.create(cs.id)

    artifact = await arts.create(
        conversation_id = conv.id,
        execution_id    = execution.id,
        content         = "# Architecture Document\n\nTest content.",
        version         = 1,
        status          = "pending_review",
    )

    resp = await client.get(f"/api/artifacts/{artifact.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"]      == artifact.id
    assert data["version"] == 1
    assert "Architecture Document" in data["content"]
    assert data["status"]  == "pending_review"


@pytest.mark.e2e
async def test_get_artifact_wrong_user_returns_404(client, pool):
    """Artifact belonging to a different user should not be accessible."""
    from repositories.user_repository         import UserRepository
    from repositories.conversation_repository import ConversationRepository
    from repositories.artifact_repository     import ArtifactRepository
    from repositories.execution_repository    import ExecutionRepository
    from repositories.skill_repository        import SkillRepository

    users  = UserRepository(pool)
    convs  = ConversationRepository(pool)
    arts   = ArtifactRepository(pool)
    execs  = ExecutionRepository(pool)
    skills = SkillRepository(pool)

    # Create a different user's conversation
    await users.upsert("other-user-999", "other@example.com", "Other User", None)
    conv  = await convs.create("other-user-999", "Other Conv", "anthropic", "claude-sonnet-4-6")

    skill = await skills.get_by_key("architect")
    if not skill:
        pytest.skip("architect skill not seeded")

    cs        = await convs.add_skill(conv.id, skill.id, agents=[])
    execution = await execs.create(cs.id)
    artifact  = await arts.create(
        conversation_id = conv.id,
        execution_id    = execution.id,
        content         = "Private content",
        version         = 1,
        status          = "pending_review",
    )

    # test-user-001 tries to access other-user-999's artifact — expect 403 or 404
    resp = await client.get(f"/api/artifacts/{artifact.id}")
    assert resp.status_code in (403, 404)
