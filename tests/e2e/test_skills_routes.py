"""
E2E tests for /api/skills routes.
Covers: list, install, uninstall.
"""

import pytest


@pytest.mark.e2e
async def test_list_skills(client):
    resp = await client.get("/api/skills")
    assert resp.status_code == 200
    data = resp.json()
    assert "skills" in data
    assert any(s["id"] == "architect" for s in data["skills"])


@pytest.mark.e2e
async def test_install_and_uninstall_skill(client):
    # Install
    resp = await client.post("/api/skills/architect")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["skill"] == "architect"
    assert data["status"] in ("installed", "already_installed")

    # List shows installed
    resp = await client.get("/api/skills")
    skills = {s["id"]: s for s in resp.json()["skills"]}
    assert skills["architect"]["installed"] is True

    # Install again — idempotent
    resp = await client.post("/api/skills/architect")
    assert resp.status_code == 200
    assert resp.json()["status"] == "already_installed"

    # Uninstall
    resp = await client.delete("/api/skills/architect")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # No longer installed
    resp = await client.get("/api/skills")
    skills = {s["id"]: s for s in resp.json()["skills"]}
    assert skills["architect"]["installed"] is False


@pytest.mark.e2e
async def test_install_unknown_skill_returns_404(client):
    resp = await client.post("/api/skills/nonexistent-skill")
    assert resp.status_code == 404
