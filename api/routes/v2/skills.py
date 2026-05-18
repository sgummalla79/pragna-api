"""
V2 Skill versioning routes — skill-level versioning.

GET    /api/v2/skills/{skill_id}/versions            — list all global versions
GET    /api/v2/skills/{skill_id}/versions/{version}  — get a specific version
GET    /api/v2/skills/{skill_id}/draft               — get your current draft
PUT    /api/v2/skills/{skill_id}/agents/{agent_key}  — edit agent (auto-creates draft)
DELETE /api/v2/skills/{skill_id}/draft               — discard your draft
POST   /api/v2/skills/{skill_id}/publish             — publish draft → new global version
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from utils.auth import AuthUser, get_current_user

log    = logging.getLogger(__name__)
router = APIRouter(prefix="/skills", tags=["v2 / Skills"])


class UpdateAgentRequest(BaseModel):
    content:  str
    provider: Optional[str] = None
    model:    Optional[str] = None


class PublishRequest(BaseModel):
    notes: Optional[str] = None


def _version_to_dict(v) -> dict:
    return {
        "id":             v.id,
        "version_number": v.version_number,
        "published_by":   v.published_by,
        "published_at":   v.published_at,
        "notes":          v.notes,
        "agents": [
            {
                "agent_key": a.agent_key,
                "content":   a.content,
                "provider":  a.provider,
                "model":     a.model,
            }
            for a in v.agents
        ],
    }


def _draft_to_dict(d) -> dict:
    return {
        "id":                  d.id,
        "based_on_version_id": d.based_on_version_id,
        "created_at":          d.created_at,
        "updated_at":          d.updated_at,
        "agents": [
            {
                "agent_key":  a.agent_key,
                "content":    a.content,
                "provider":   a.provider,
                "model":      a.model,
                "updated_at": a.updated_at,
            }
            for a in d.agents
        ],
    }


@router.get(
    "/{skill_id}/versions",
    summary="List all global versions for a skill",
)
async def list_versions(
    skill_id:     str,
    request:      Request,
    current_user: AuthUser = Depends(get_current_user),
):
    db    = request.app.state.db
    skill = await db.skills.get_by_key(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found.")

    versions = await db.skill_versions.list_versions(skill.id)
    return {
        "skill_id": skill_id,
        "versions": [_version_to_dict(v) for v in versions],
        "total":    len(versions),
    }


@router.get(
    "/{skill_id}/versions/{version_number}",
    summary="Get a specific global version",
)
async def get_version(
    skill_id:       str,
    version_number: int,
    request:        Request,
    current_user:   AuthUser = Depends(get_current_user),
):
    db    = request.app.state.db
    skill = await db.skills.get_by_key(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found.")

    version = await db.skill_versions.get_version(skill.id, version_number)
    if not version:
        raise HTTPException(status_code=404, detail=f"Version {version_number} not found.")

    return _version_to_dict(version)


@router.get(
    "/{skill_id}/draft",
    summary="Get your current draft",
)
async def get_draft(
    skill_id:     str,
    request:      Request,
    current_user: AuthUser = Depends(get_current_user),
):
    db    = request.app.state.db
    skill = await db.skills.get_by_key(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found.")

    draft = await db.skill_versions.get_draft(skill.id, current_user.sub)
    if not draft:
        return {"skill_id": skill_id, "draft": None}

    return {"skill_id": skill_id, "draft": _draft_to_dict(draft)}


@router.put(
    "/{skill_id}/agents/{agent_key}",
    summary="Edit an agent's prompt in your draft (auto-creates draft if needed)",
)
async def update_agent(
    skill_id:     str,
    agent_key:    str,
    body:         UpdateAgentRequest,
    request:      Request,
    current_user: AuthUser = Depends(get_current_user),
):
    db    = request.app.state.db
    skill = await db.skills.get_by_key(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found.")

    agent = await db.agents.get_by_key(skill.id, agent_key)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_key}' not found.")

    draft = await db.skill_versions.upsert_draft_agent(
        skill_id  = skill.id,
        user_id   = current_user.sub,
        agent_key = agent_key,
        content   = body.content,
        provider  = body.provider,
        model     = body.model,
    )
    return {"ok": True, "skill_id": skill_id, "draft": _draft_to_dict(draft)}


@router.delete(
    "/{skill_id}/draft",
    summary="Discard your entire draft",
)
async def discard_draft(
    skill_id:     str,
    request:      Request,
    current_user: AuthUser = Depends(get_current_user),
):
    db    = request.app.state.db
    skill = await db.skills.get_by_key(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found.")

    await db.skill_versions.discard_draft(skill.id, current_user.sub)
    return {"ok": True, "skill_id": skill_id}


@router.post(
    "/{skill_id}/publish",
    summary="Publish your draft as a new global version",
)
async def publish_skill(
    skill_id:     str,
    body:         PublishRequest,
    request:      Request,
    current_user: AuthUser = Depends(get_current_user),
):
    db    = request.app.state.db
    skill = await db.skills.get_by_key(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found.")

    draft = await db.skill_versions.get_draft(skill.id, current_user.sub)
    if not draft or not draft.agents:
        raise HTTPException(status_code=400, detail="No draft to publish.")

    agents = [
        {
            "agent_key": a.agent_key,
            "content":   a.content,
            "provider":  a.provider,
            "model":     a.model,
        }
        for a in draft.agents
    ]

    version = await db.skill_versions.publish(
        skill_id = skill.id,
        user_id  = current_user.sub,
        agents   = agents,
        notes    = body.notes,
    )

    # Discard draft after successful publish
    await db.skill_versions.discard_draft(skill.id, current_user.sub)

    return {
        "ok":      True,
        "skill_id": skill_id,
        "version": _version_to_dict(version),
    }
