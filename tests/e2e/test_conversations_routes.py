"""
E2E tests for /api/conversations routes.
Covers: create, list, get, rename, delete, add/remove skill, config.
"""

import pytest


@pytest.mark.e2e
async def test_create_and_list_conversation(client):
    resp = await client.post("/api/conversations", json={
        "title": "Test Conversation",
        "chat_provider": "anthropic",
        "chat_model": "claude-sonnet-4-6",
    })
    assert resp.status_code == 200
    conv_id = resp.json()["id"]
    assert conv_id

    resp = await client.get("/api/conversations")
    assert resp.status_code == 200
    data = resp.json()
    all_convs = data.get("recent", []) + data.get("pinned", [])
    ids = [c["id"] for c in all_convs]
    assert conv_id in ids


@pytest.mark.e2e
async def test_get_conversation(client):
    resp = await client.post("/api/conversations", json={"title": "Get Test"})
    conv_id = resp.json()["id"]

    resp = await client.get(f"/api/conversations/{conv_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == conv_id
    assert data["title"] == "Get Test"
    assert "messages" in data
    assert "skills" in data


@pytest.mark.e2e
async def test_get_nonexistent_conversation_returns_404(client):
    resp = await client.get("/api/conversations/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


@pytest.mark.e2e
async def test_rename_conversation(client):
    resp = await client.post("/api/conversations", json={"title": "Original"})
    conv_id = resp.json()["id"]

    resp = await client.patch(f"/api/conversations/{conv_id}", json={"title": "Renamed"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    resp = await client.get(f"/api/conversations/{conv_id}")
    assert resp.json()["title"] == "Renamed"


@pytest.mark.e2e
async def test_delete_conversation(client):
    resp = await client.post("/api/conversations", json={"title": "To Delete"})
    conv_id = resp.json()["id"]

    resp = await client.delete(f"/api/conversations/{conv_id}")
    assert resp.status_code == 200

    resp = await client.get(f"/api/conversations/{conv_id}")
    assert resp.status_code == 404


@pytest.mark.e2e
async def test_add_skill_requires_install_first(client):
    resp = await client.post("/api/conversations", json={"title": "Skill Test"})
    conv_id = resp.json()["id"]

    # Skill not installed — should 400
    resp = await client.post(f"/api/conversations/{conv_id}/skills",
                             json={"skill_id": "architect"})
    assert resp.status_code == 400


@pytest.mark.e2e
async def test_add_skill_after_install(client):
    # Install skill first
    await client.post("/api/skills/architect")

    # Create conversation
    resp = await client.post("/api/conversations", json={"title": "With Skill"})
    conv_id = resp.json()["id"]

    # Add skill
    resp = await client.post(f"/api/conversations/{conv_id}/skills",
                             json={"skill_id": "architect"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["agents_count"] > 0
    snap_id = data["conversation_skill_id"]

    # Conversation shows the skill
    resp = await client.get(f"/api/conversations/{conv_id}")
    skills = resp.json()["skills"]
    assert any(s["id"] == snap_id for s in skills)

    # Get config
    resp = await client.get(f"/api/conversations/{conv_id}/skills/{snap_id}/config")
    assert resp.status_code == 200
    assert "agents" in resp.json()

    # Remove skill
    resp = await client.delete(f"/api/conversations/{conv_id}/skills/{snap_id}")
    assert resp.status_code == 200
