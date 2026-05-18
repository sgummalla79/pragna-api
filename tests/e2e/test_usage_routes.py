"""
E2E tests for usage routes.
"""

import pytest


@pytest.mark.e2e
async def test_conversation_usage_empty(client):
    resp = await client.post("/api/conversations", json={"title": "Usage Test"})
    conv_id = resp.json()["id"]

    resp = await client.get(f"/api/conversations/{conv_id}/usage")
    assert resp.status_code == 200
    data = resp.json()
    assert data["totals"]["input_tokens"]  == 0
    assert data["totals"]["output_tokens"] == 0
    assert data["totals"]["cost_usd"]      == 0.0


@pytest.mark.e2e
async def test_usage_summary(client):
    resp = await client.get("/api/usage/summary")
    assert resp.status_code == 200
    assert "totals" in resp.json()
    assert "input_tokens" in resp.json()["totals"]
