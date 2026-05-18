"""
E2E tests — agent prompt versioning lifecycle via API routes.
"""

import pytest


@pytest.mark.e2e
async def test_save_draft_and_publish(client):
    await client.post("/api/skills/architect")

    resp = await client.put(
        "/api/skills/architect/agents/discovery/draft",
        json={"content": "New discovery prompt"},
    )
    assert resp.status_code == 200
    assert resp.json()["version"] == 2

    resp = await client.post("/api/skills/architect/agents/discovery/publish")
    assert resp.status_code == 200
    assert resp.json()["version"] == 2


@pytest.mark.e2e
async def test_publish_all_no_drafts_returns_400(client):
    await client.post("/api/skills/architect")
    resp = await client.post("/api/skills/architect/publish")
    assert resp.status_code == 400
