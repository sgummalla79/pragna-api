"""
E2E tests for conversation creation and message flow.
"""

import pytest


@pytest.mark.e2e
async def test_create_conversation(client):
    resp = await client.post("/api/conversations", json={
        "title": "Test Session",
        "chat_provider": "anthropic",
        "chat_model": "claude-sonnet-4-6",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"]
    assert data["title"] == "Test Session"


@pytest.mark.e2e
async def test_list_conversations_empty(client):
    resp = await client.get("/api/conversations")
    assert resp.status_code == 200
    data = resp.json()
    assert data["pinned"] == []
    assert data["recent"] == []
