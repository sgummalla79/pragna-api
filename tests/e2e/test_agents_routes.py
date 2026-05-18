"""
E2E tests for /api/skills/{id}/agents routes.
Covers: list agents, save draft, discard draft, publish per-agent, publish all.
"""

import pytest


@pytest.mark.e2e
async def test_list_agents_after_install(client):
    await client.post("/api/skills/architect")

    resp = await client.get("/api/skills/architect/agents")
    assert resp.status_code == 200
    data = resp.json()
    assert data["skill_id"] == "architect"
    assert len(data["agents"]) > 0
    assert not data["has_draft"]

    agent = data["agents"][0]
    assert "agent_key" in agent
    assert "published" in agent
    assert agent["published"] is not None   # version 1 from install


@pytest.mark.e2e
async def test_save_and_discard_draft(client):
    await client.post("/api/skills/architect")

    agent_key = "discovery"
    resp = await client.put(
        f"/api/skills/architect/agents/{agent_key}/draft",
        json={"content": "Updated discovery prompt v2"},
    )
    assert resp.status_code == 200
    assert resp.json()["version"] == 2

    # has_draft is now True
    resp = await client.get("/api/skills/architect/agents")
    assert resp.json()["has_draft"] is True

    # Discard
    resp = await client.delete(f"/api/skills/architect/agents/{agent_key}/draft")
    assert resp.status_code == 200

    resp = await client.get("/api/skills/architect/agents")
    assert resp.json()["has_draft"] is False


@pytest.mark.e2e
async def test_publish_per_agent(client):
    await client.post("/api/skills/architect")

    agent_key = "discovery"
    await client.put(
        f"/api/skills/architect/agents/{agent_key}/draft",
        json={"content": "Published prompt"},
    )

    resp = await client.post(f"/api/skills/architect/agents/{agent_key}/publish")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert resp.json()["version"] == 2

    # No more draft
    resp = await client.get("/api/skills/architect/agents")
    agents = {a["agent_key"]: a for a in resp.json()["agents"]}
    assert agents[agent_key]["draft"] is None
    assert agents[agent_key]["published"]["version"] == 2


@pytest.mark.e2e
async def test_publish_all_no_drafts_returns_400(client):
    await client.post("/api/skills/architect")
    resp = await client.post("/api/skills/architect/publish")
    assert resp.status_code == 400


@pytest.mark.e2e
async def test_publish_all(client):
    await client.post("/api/skills/architect")

    # Save drafts for two agents
    for key in ["discovery", "review"]:
        await client.put(
            f"/api/skills/architect/agents/{key}/draft",
            json={"content": f"Updated {key} prompt"},
        )

    resp = await client.post("/api/skills/architect/publish")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["count"] == 2
