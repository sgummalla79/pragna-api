"""
E2E tests — skill invocation guards.
"""

import pytest


@pytest.mark.e2e
async def test_invoke_rejects_snapshot_not_found(client):
    """404 when snapshot_id does not belong to the conversation."""
    resp = await client.post("/api/conversations", json={"title": "Test"})
    conv_id = resp.json()["id"]

    resp = await client.post(
        f"/api/conversations/{conv_id}/skills/00000000-0000-0000-0000-000000000099/invoke",
        json={"brief": "Build a platform", "source_type": "brief"},
    )
    assert resp.status_code == 404


@pytest.mark.e2e
async def test_invoke_rejects_conversation_not_found(client):
    resp = await client.post(
        "/api/conversations/00000000-0000-0000-0000-000000000000/skills/00000000-0000-0000-0000-000000000001/invoke",
        json={"brief": "test", "source_type": "brief"},
    )
    assert resp.status_code == 404
