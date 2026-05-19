"""
V2 Skill versioning routes — per-user skill snapshot management.

GET    /api/v2/skills/{skill_id}/versions            — list published versions
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
    model_id: Optional[str] = None   # user_llm_models.id UUID


class PublishRequest(BaseModel):
    notes: Optional[str] = None


def _snapshot_to_dict(s) -> dict:
    return {
        "id":             s.id,
        "version_number": s.version_number,
        "status":         s.type,   # map type → status for API compatibility
        "created_at":     s.created_at,
        "modified_at":    s.modified_at,
        "agents": [
            {
                "skill_agent_id": a.skill_agent_id,
                "content":        a.content,
                "model_id":       a.model_id,
                "modified_at":    a.modified_at,
            }
            for a in s.agents
        ],
    }


async def _get_skill_or_404(db, user_id: str, skill_id: str):
    skill = await db.skills.get_by_key(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found.")
    installed = await db.skill_snapshots.is_installed(user_id, skill.id)
    if not installed:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not installed.")
    return skill


@router.get(
    "/{skill_id}/versions",
    summary="List all published versions for this user's skill",
)
async def list_versions(
    skill_id:     str,
    request:      Request,
    current_user: AuthUser = Depends(get_current_user),
):
    db    = request.app.state.db
    skill = await _get_skill_or_404(db, current_user.sub, skill_id)

    published = await db.skill_snapshots.list_published(current_user.sub, skill.id)
    current   = published[0] if published else None

    return {
        "skill_id":        skill_id,
        "current_version": current.version_number if current else 0,
        "versions":        [_snapshot_to_dict(v) for v in published],
        "total":           len(published),
    }


@router.get(
    "/{skill_id}/versions/{version_number}",
    summary="Get a specific published version",
)
async def get_version(
    skill_id:       str,
    version_number: int,
    request:        Request,
    current_user:   AuthUser = Depends(get_current_user),
):
    db    = request.app.state.db
    skill = await _get_skill_or_404(db, current_user.sub, skill_id)

    snapshot = await db.skill_snapshots.get_published_version(
        current_user.sub, skill.id, version_number
    )
    if not snapshot:
        raise HTTPException(status_code=404, detail=f"Version {version_number} not found.")

    return _snapshot_to_dict(snapshot)


@router.get(
    "/{skill_id}/draft",
    summary="Get current draft",
)
async def get_draft(
    skill_id:     str,
    request:      Request,
    current_user: AuthUser = Depends(get_current_user),
):
    db    = request.app.state.db
    skill = await _get_skill_or_404(db, current_user.sub, skill_id)

    draft = await db.skill_snapshots.get_draft(current_user.sub, skill.id)
    return {"skill_id": skill_id, "draft": _snapshot_to_dict(draft) if draft else None}


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
    db    = request.app.state.db
    skill = await _get_skill_or_404(db, current_user.sub, skill_id)

    skill_agent = await db.agents.get_by_key(skill.id, agent_name)
    if not skill_agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found.")

    draft = await db.skill_snapshots.get_draft(current_user.sub, skill.id)

    if not draft:
        published = await db.skill_snapshots.get_current_published(current_user.sub, skill.id)
        if published:
            base_agents = published.agents
        else:
            from repositories.skill_snapshot_repository import SkillSnapshotAgent
            oob = await db.agents.get_by_skill(skill.id)
            base_agents = [
                SkillSnapshotAgent(
                    id="", snapshot_id="",
                    skill_agent_id=a.id,
                    content=a.content,
                    model_id=None,
                    created_at="", modified_at="",
                )
                for a in oob
            ]
        draft = await db.skill_snapshots.create_draft(current_user.sub, skill.id, base_agents)

    await db.skill_snapshots.upsert_draft_agent(
        snapshot_id    = draft.id,
        skill_agent_id = skill_agent.id,
        content        = body.content,
        model_id       = body.model_id,
    )

    updated_draft = await db.skill_snapshots.get_draft(current_user.sub, skill.id)
    return {"ok": True, "skill_id": skill_id, "draft": _snapshot_to_dict(updated_draft)}


@router.delete(
    "/{skill_id}/draft",
    summary="Discard current draft",
)
async def discard_draft(
    skill_id:     str,
    request:      Request,
    current_user: AuthUser = Depends(get_current_user),
):
    db    = request.app.state.db
    skill = await _get_skill_or_404(db, current_user.sub, skill_id)

    await db.skill_snapshots.discard_draft(current_user.sub, skill.id)
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
    db    = request.app.state.db
    skill = await _get_skill_or_404(db, current_user.sub, skill_id)

    draft = await db.skill_snapshots.get_draft(current_user.sub, skill.id)
    if not draft or not draft.agents:
        raise HTTPException(status_code=400, detail="No draft to publish.")

    snapshot = await db.skill_snapshots.publish_draft(draft.id)
    return {"ok": True, "skill_id": skill_id, "version": _snapshot_to_dict(snapshot)}
