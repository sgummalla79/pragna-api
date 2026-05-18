"""
Agent prompt versioning routes.

GET    /api/skills/{skill_id}/agents                         — all agents + versions
PUT    /api/skills/{skill_id}/agents/{agent_key}/draft       — save/update draft
DELETE /api/skills/{skill_id}/agents/{agent_key}/draft       — discard draft
POST   /api/skills/{skill_id}/agents/{agent_key}/publish     — per-agent publish
POST   /api/skills/{skill_id}/publish                        — publish ALL drafts
PATCH  /api/skills/{skill_id}/agents/{agent_key}/model       — update default model
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from utils.auth import AuthUser, get_current_user

log    = logging.getLogger(__name__)
router = APIRouter(prefix="/api/skills")


class SaveDraftRequest(BaseModel):
    content:  str
    provider: Optional[str] = None
    model:    Optional[str] = None


class UpdateModelRequest(BaseModel):
    provider: Optional[str] = None   # None = revert to smart default
    model:    Optional[str] = None


@router.get(
    "/{skill_id}/agents",
    tags=["Agents"],
    summary="List agents and their published/draft prompt versions",
    responses={200: {"description": "All agents with published and draft version info"}},
)
async def list_agents(
    skill_id:     str,
    request:      Request,
    current_user: AuthUser = Depends(get_current_user),
):
    db    = request.app.state.db
    skill = await db.skills.get_by_key(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found.")

    skill_registry = request.app.state.skill_registry
    manifest       = skill_registry.get(skill_id).manifest if skill_id in skill_registry else None
    slot_map       = manifest.agent_slot_map if manifest else {}

    agents     = await db.agents.get_by_skill(skill.id)
    user_agents = await db.user_agents.get_for_skill(current_user.sub, skill.id)
    ua_by_agent = {ua.agent_id: ua for ua in user_agents}

    result = []
    for agent in agents:
        ua       = ua_by_agent.get(agent.id)
        history  = await db.user_agents.get_version_history(current_user.sub, agent.id) if ua else []
        published = next((v for v in history if v.status == "published" and (ua and v.version == ua.current_version)), None)
        draft     = next((v for v in history if v.status == "draft"), None)

        result.append({
            "agent_key":        agent.agent_key,
            "label":            agent.label,
            "slot":             slot_map.get(agent.agent_key),
            "provider_to_use":  published.provider_to_use if published else None,
            "model_to_use":     published.model_to_use    if published else None,
            "current_version":  ua.current_version if ua else None,
            "published":        {
                "version":          published.version,
                "content":          published.content,
                "provider_to_use":  published.provider_to_use,
                "model_to_use":     published.model_to_use,
                "published_at":     published.published_at,
            } if published else None,
            "draft": {
                "version":          draft.version,
                "content":          draft.content,
                "provider_to_use":  draft.provider_to_use,
                "model_to_use":     draft.model_to_use,
                "created_at":       draft.created_at,
            } if draft else None,
            "has_draft": draft is not None,
        })

    has_draft = any(a["has_draft"] for a in result)
    return {"skill_id": skill_id, "agents": result, "has_draft": has_draft}


@router.put(
    "/{skill_id}/agents/{agent_key}/draft",
    tags=["Agents"],
    summary="Save or update an agent prompt draft",
    responses={
        200: {"description": "Draft saved with version number"},
        404: {"description": "Skill or agent not found"},
    },
)
async def save_draft(
    skill_id:     str,
    agent_key:    str,
    body:         SaveDraftRequest,
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

    version = await db.user_agents.save_draft(
        current_user.sub, agent.id, body.content, body.provider, body.model
    )
    return {"ok": True, "agent_key": agent_key, "version": version.version}


@router.delete(
    "/{skill_id}/agents/{agent_key}/draft",
    tags=["Agents"],
    summary="Discard agent prompt draft",
    responses={
        200: {"description": "Draft discarded"},
        404: {"description": "Skill or agent not found"},
    },
)
async def discard_draft(
    skill_id:     str,
    agent_key:    str,
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

    await db.user_agents.discard_draft(current_user.sub, agent.id)
    return {"ok": True}


@router.post(
    "/{skill_id}/agents/{agent_key}/publish",
    tags=["Agents"],
    summary="Publish agent draft",
    responses={
        200: {"description": "Draft published as new version"},
        400: {"description": "No draft to publish"},
        404: {"description": "Skill or agent not found"},
    },
)
async def publish_agent(
    skill_id:     str,
    agent_key:    str,
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

    try:
        version = await db.user_agents.publish(current_user.sub, agent.id)
        return {"ok": True, "agent_key": agent_key, "version": version.version}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.patch(
    "/{skill_id}/agents/{agent_key}/model",
    tags=["Agents"],
    summary="Set default provider/model for an agent",
    responses={
        200: {"description": "Default model updated"},
        404: {"description": "Skill, agent, or user agent not found"},
    },
)
async def update_agent_model(
    skill_id:     str,
    agent_key:    str,
    body:         UpdateModelRequest,
    request:      Request,
    current_user: AuthUser = Depends(get_current_user),
):
    """Set (or clear) the default provider/model for an agent. Null = smart default."""
    db    = request.app.state.db
    skill = await db.skills.get_by_key(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found.")
    agent = await db.agents.get_by_key(skill.id, agent_key)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_key}' not found.")

    updated = await db.user_agents.set_model(
        current_user.sub, agent.id, body.provider or None, body.model or None
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Agent not installed for this user.")
    return {"ok": True, "agent_key": agent_key, "provider": body.provider, "model": body.model}


@router.post(
    "/{skill_id}/publish",
    tags=["Agents"],
    summary="Publish all agent drafts for a skill atomically",
    responses={
        200: {"description": "All drafts published"},
        400: {"description": "No unpublished drafts to publish"},
        404: {"description": "Skill not found"},
    },
)
async def publish_all(
    skill_id:     str,
    request:      Request,
    current_user: AuthUser = Depends(get_current_user),
):
    """Publish all drafts for a skill atomically."""
    db    = request.app.state.db
    skill = await db.skills.get_by_key(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found.")

    published = await db.user_agents.publish_all(current_user.sub, skill.id)
    if not published:
        raise HTTPException(status_code=400, detail="No unpublished drafts to publish.")

    return {
        "ok":               True,
        "skill_id":         skill_id,
        "published_agents": [v.user_agent_id for v in published],
        "count":            len(published),
    }


