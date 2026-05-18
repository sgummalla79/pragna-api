"""
V2 Skill versioning routes — per-user skill versioning.

GET    /api/v2/skills/{skill_id}/versions            — list user's versions
GET    /api/v2/skills/{skill_id}/versions/{version}  — get a specific version
GET    /api/v2/skills/{skill_id}/draft               — get current draft
PUT    /api/v2/skills/{skill_id}/agents/{agent_name} — edit agent (auto-creates draft)
DELETE /api/v2/skills/{skill_id}/draft               — discard draft
POST   /api/v2/skills/{skill_id}/publish             — publish draft → new version
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
    model_id: Optional[str] = None


class PublishRequest(BaseModel):
    notes: Optional[str] = None


def _version_to_dict(v) -> dict:
    return {
        "id":             v.id,
        "version_number": v.version_number,
        "status":         v.status,
        "created_at":     v.created_at,
        "agents": [
            {
                "skill_agent_id": a.skill_agent_id,
                "content":        a.content,
                "model_id":       a.model_id,
                "modified_at":    a.modified_at,
            }
            for a in v.agents
        ],
    }


async def _get_user_skill_or_404(db, user_id: str, skill_id: str):
    skill = await db.skills.get_by_key(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found.")

    user_skill = await db.user_skill_v2.get(user_id, skill.id)
    if not user_skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not installed.")

    return skill, user_skill


@router.get(
    "/{skill_id}/versions",
    summary="List all versions for this user's skill",
)
async def list_versions(
    skill_id:     str,
    request:      Request,
    current_user: AuthUser = Depends(get_current_user),
):
    db = request.app.state.db
    skill, user_skill = await _get_user_skill_or_404(db, current_user.sub, skill_id)

    versions = await db.user_skill_v2.list_versions(user_skill.id)
    return {
        "skill_id":        skill_id,
        "current_version": user_skill.current_version,
        "versions":        [_version_to_dict(v) for v in versions],
        "total":           len(versions),
    }


@router.get(
    "/{skill_id}/versions/{version_number}",
    summary="Get a specific version",
)
async def get_version(
    skill_id:       str,
    version_number: int,
    request:        Request,
    current_user:   AuthUser = Depends(get_current_user),
):
    db = request.app.state.db
    skill, user_skill = await _get_user_skill_or_404(db, current_user.sub, skill_id)

    version = await db.user_skill_v2.get_version(user_skill.id, version_number)
    if not version:
        raise HTTPException(status_code=404, detail=f"Version {version_number} not found.")

    return _version_to_dict(version)


@router.get(
    "/{skill_id}/draft",
    summary="Get current draft",
)
async def get_draft(
    skill_id:     str,
    request:      Request,
    current_user: AuthUser = Depends(get_current_user),
):
    db = request.app.state.db
    skill, user_skill = await _get_user_skill_or_404(db, current_user.sub, skill_id)

    draft = await db.user_skill_v2.get_draft(user_skill.id)
    return {"skill_id": skill_id, "draft": _version_to_dict(draft) if draft else None}


@router.put(
    "/{skill_id}/agents/{agent_name}",
    summary="Edit an agent — auto-creates a draft if none exists",
)
async def update_agent(
    skill_id:     str,
    agent_name:   str,
    body:         UpdateAgentRequest,
    request:      Request,
    current_user: AuthUser = Depends(get_current_user),
):
    db = request.app.state.db
    skill, user_skill = await _get_user_skill_or_404(db, current_user.sub, skill_id)

    skill_agent = await db.agents.get_by_key(skill.id, agent_name)
    if not skill_agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found.")

    draft = await db.user_skill_v2.get_draft(user_skill.id)

    if not draft:
        # Create a new draft copying agents from the latest published version
        base_agents = await db.user_skill_v2.get_latest_published_agents(user_skill.id)
        if not base_agents:
            # First ever edit — seed from OOB skill_agents
            oob_agents = await db.agents.get_by_skill(skill.id)
            from repositories.user_skill_v2_repository import UserSkillAgent
            base_agents = [
                UserSkillAgent(
                    id="", user_id=current_user.sub,
                    user_skill_version_id="",
                    skill_agent_id=a.id,
                    content=a.content,
                    model_id=None,
                    created_at="", modified_at="",
                )
                for a in oob_agents
            ]
        draft = await db.user_skill_v2.create_draft(
            user_skill_id = user_skill.id,
            base_agents   = base_agents,
        )

    await db.user_skill_v2.upsert_draft_agent(
        user_skill_version_id = draft.id,
        skill_agent_id        = skill_agent.id,
        content               = body.content,
        model_id              = body.model_id,
    )

    updated_draft = await db.user_skill_v2.get_draft(user_skill.id)
    return {"ok": True, "skill_id": skill_id, "draft": _version_to_dict(updated_draft)}


@router.delete(
    "/{skill_id}/draft",
    summary="Discard current draft",
)
async def discard_draft(
    skill_id:     str,
    request:      Request,
    current_user: AuthUser = Depends(get_current_user),
):
    db = request.app.state.db
    skill, user_skill = await _get_user_skill_or_404(db, current_user.sub, skill_id)

    await db.user_skill_v2.discard_draft(user_skill.id)
    return {"ok": True, "skill_id": skill_id}


@router.post(
    "/{skill_id}/publish",
    summary="Publish current draft as a new version",
)
async def publish_skill(
    skill_id:     str,
    body:         PublishRequest,
    request:      Request,
    current_user: AuthUser = Depends(get_current_user),
):
    db = request.app.state.db
    skill, user_skill = await _get_user_skill_or_404(db, current_user.sub, skill_id)

    draft = await db.user_skill_v2.get_draft(user_skill.id)
    if not draft or not draft.agents:
        raise HTTPException(status_code=400, detail="No draft to publish.")

    version = await db.user_skill_v2.publish_draft(user_skill.id, draft.id)
    return {"ok": True, "skill_id": skill_id, "version": _version_to_dict(version)}
