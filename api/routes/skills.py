"""
Skill management routes.

GET    /api/skills                          — list all available skills with installed status
POST   /api/skills/classify-choice          — LLM-classify which skill the user chose
POST   /api/skills/{id}/validate-brief      — validate brief relevance + sufficiency
POST   /api/skills/{id}                     — install a skill (creates user_agents + version 1)
DELETE /api/skills/{id}                     — uninstall a skill
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from utils.auth import AuthUser, get_current_user

log    = logging.getLogger(__name__)
router = APIRouter(prefix="/skills")


@router.get(
    "",
    tags=["v1 / Skills"],
    summary="List all available skills with install status",
    responses={200: {"description": "All skills with installed flag and pipeline stages"}},
)
async def list_skills(request: Request, current_user: AuthUser = Depends(get_current_user)):
    db             = request.app.state.db
    skill_registry = request.app.state.skill_registry

    all_skills = await db.skills.list_all()

    # Build set of installed skill IDs from user_skills_v2
    installed_ids: set[str] = set()
    for skill in all_skills:
        us = await db.user_skill_v2.get(current_user.sub, skill.id)
        if us:
            installed_ids.add(skill.id)

    result = []
    for skill in all_skills:
        manifest = skill_registry.get(skill.name).manifest if skill.name in skill_registry else None
        result.append({
            "id":           skill.name,
            "name":         skill.name,
            "display_name": skill.display_name,
            "description":  skill.description,
            "installed":    skill.id in installed_ids,
            "pipeline":     manifest.pipeline if manifest else [],
        })

    return {"skills": result}


# ── Skill choice classification ───────────────────────────────────────────────
# NOTE: Must be defined BEFORE /{skill_id} so FastAPI matches the literal path first.

class SkillChoiceItem(BaseModel):
    id:          str
    name:        str
    description: Optional[str] = ""

class ClassifyChoiceRequest(BaseModel):
    response: str
    skills:   list[SkillChoiceItem]


@router.post(
    "/classify-choice",
    tags=["v1 / Skills"],
    summary="LLM-classify which skill the user chose from a list",
    responses={200: {"description": "Matched skill_id or 'none'"}},
)
async def classify_skill_choice(
    body:         ClassifyChoiceRequest,
    request:      Request,
    current_user: AuthUser = Depends(get_current_user),
):
    """Use the cheapest available LLM to classify which skill the user chose."""
    from utils.user_context import connected_providers
    from framework.defaults import smart_pick
    from utils.llm_factory import build_llm
    from langchain_core.messages import SystemMessage, HumanMessage

    db        = request.app.state.db
    connected = connected_providers()
    raw_models = await db.llm_models.get_active(current_user.sub)
    active_models = [{"provider": m.provider_key, "model_id": m.model_id} for m in raw_models]
    try:
        pick = smart_pick("default", connected, active_models)
        llm  = build_llm(pick["provider"], pick["model"])
    except ValueError:
        return {"skill_id": "none"}

    skill_lines = "\n".join(f'- {s.id}: {s.name}' for s in body.skills)
    valid_ids   = {s.id for s in body.skills} | {"none"}

    result = await llm.ainvoke([
        SystemMessage(content=(
            f"The user was asked to choose a skill to run. Options:\n{skill_lines}\n- none\n\n"
            "Reply with ONLY the exact skill_id or 'none'. No punctuation, no explanation."
        )),
        HumanMessage(content=body.response),
    ])

    chosen = result.content.strip().lower().split()[0] if result.content.strip() else "none"
    return {"skill_id": chosen if chosen in valid_ids else "none"}


# ── Brief validation ───────────────────────────────────────────────────────────

class ValidateBriefRequest(BaseModel):
    brief: str

class _BriefValidation(BaseModel):
    valid:   bool
    reason:  str   # "ok" | "not_relevant" | "insufficient"
    message: str   # user-facing guidance when not valid; empty when valid


@router.post(
    "/{skill_id}/validate-brief",
    tags=["v1 / Skills"],
    summary="Validate brief relevance and sufficiency for a skill",
    responses={
        200: {"description": "{valid, reason, message}"},
        404: {"description": "Skill not found"},
    },
)
async def validate_brief(
    skill_id:     str,
    body:         ValidateBriefRequest,
    request:      Request,
    current_user: AuthUser = Depends(get_current_user),
):
    """
    Validate that the user's brief is relevant and sufficient for the skill.
    Returns {valid, reason, message}. Falls back to valid=True if no LLM is available.
    """
    db    = request.app.state.db
    skill = await db.skills.get_by_key(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found.")

    from utils.user_context import connected_providers
    from framework.defaults import smart_pick
    from utils.llm_factory import build_llm
    from langchain_core.messages import SystemMessage, HumanMessage

    connected = connected_providers()
    raw_models = await db.llm_models.get_active(current_user.sub)
    active_models = [{"provider": m.provider_key, "model_id": m.model_id} for m in raw_models]
    try:
        pick = smart_pick("default", connected, active_models)
        llm  = build_llm(pick["provider"], pick["model"])
    except ValueError:
        return {"valid": True, "reason": "ok", "message": ""}

    system = (
        f"You evaluate whether a user's brief is suitable for the '{skill.display_name}' skill.\n"
        f"Skill purpose: {skill.description or 'No description provided.'}\n\n"
        "Evaluate on two criteria:\n"
        "1. RELEVANCE: Is the brief related to software/system architecture or technology?\n"
        "   Examples of relevant: system design, tech stack, microservices, APIs, databases, "
        "   cloud architecture, scalability, SaaS, backend, frontend, platform planning.\n"
        "   Not relevant: recipes, math homework, random words, unrelated topics.\n\n"
        "2. SUFFICIENCY: Does it give enough context to start? Even a brief description is fine.\n"
        "   Sufficient: 'build a chat app', 'e-commerce platform with recommendations'.\n"
        "   Insufficient: single words, 'help me', 'build something', 'test'.\n\n"
        "Return:\n"
        "  valid=true if relevant AND sufficient.\n"
        "  valid=false, reason='not_relevant' if clearly unrelated to software/architecture.\n"
        "  valid=false, reason='insufficient' if architecture-related but needs more context.\n"
        "  message: 1–2 sentence friendly guidance for the user (empty string when valid=true).\n\n"
        "Be lenient with relevance — if there is any reasonable software/architecture "
        "interpretation, mark it valid. Do not penalise brevity if the topic is clear."
    )

    try:
        result: _BriefValidation = await (
            llm.with_structured_output(_BriefValidation)
            .ainvoke([SystemMessage(content=system), HumanMessage(content=body.brief)])
        )
        return {"valid": result.valid, "reason": result.reason, "message": result.message}
    except Exception as exc:
        log.warning("validate_brief LLM call failed: %s", exc)
        return {"valid": True, "reason": "ok", "message": ""}


# ── Install / uninstall ────────────────────────────────────────────────────────

@router.post(
    "/{skill_id}",
    tags=["v1 / Skills"],
    summary="Install a skill for the current user",
    responses={
        200: {"description": "Skill installed (or already installed)"},
        404: {"description": "Skill not found"},
    },
)
async def install_skill(
    skill_id:     str,
    request:      Request,
    current_user: AuthUser = Depends(get_current_user),
):
    db   = request.app.state.db
    skill = await db.skills.get_by_key(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found.")

    existing = await db.user_skill_v2.get(current_user.sub, skill.id)
    if existing:
        return {"ok": True, "skill": skill_id, "status": "already_installed"}

    await db.user_skill_v2.install(current_user.sub, skill.id)
    agents = await db.agents.get_by_skill(skill.id)

    log.info("Installed skill '%s' for user %s (%d agents)", skill_id, current_user.sub, len(agents))
    return {"ok": True, "skill": skill_id, "status": "installed", "agents": len(agents)}


@router.delete(
    "/{skill_id}",
    tags=["v1 / Skills"],
    summary="Uninstall a skill",
    responses={
        200: {"description": "Skill uninstalled"},
        404: {"description": "Skill not found"},
    },
)
async def uninstall_skill(
    skill_id:     str,
    request:      Request,
    current_user: AuthUser = Depends(get_current_user),
):
    db    = request.app.state.db
    skill = await db.skills.get_by_key(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found.")

    await db.user_skill_v2.uninstall(current_user.sub, skill.id)
    return {"ok": True, "skill": skill_id}


# ── Suggest agent config ───────────────────────────────────────────────────────

@router.get(
    "/{skill_id}/suggest-config",
    tags=["v1 / Skills"],
    summary="Smart-pick provider/model for each agent in a skill",
    responses={200: {"description": "Suggested provider/model per agent key"}},
)
async def suggest_agent_config(
    skill_id:     str,
    request:      Request,
    current_user: AuthUser = Depends(get_current_user),
):
    """
    Return smart-picked provider+model for each agent in the skill,
    using the user's active models and slot preferences from defaults.py.
    """
    db             = request.app.state.db
    skill_registry = request.app.state.skill_registry

    skill = await db.skills.get_by_key(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found.")

    registry_entry = skill_registry.get(skill_id)
    if not registry_entry:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not loaded.")

    agent_slot_map = registry_entry.manifest.agent_slot_map

    from utils.user_context import connected_providers
    from framework.defaults import smart_pick
    connected     = connected_providers()
    raw_models    = await db.llm_models.get_active(current_user.sub)
    active_models = [{"provider": m.provider_key, "model_id": m.model_id} for m in raw_models]

    suggestions = {}
    for agent_key, slot in agent_slot_map.items():
        try:
            pick = smart_pick(slot, connected, active_models)
            suggestions[agent_key] = {"provider": pick["provider"], "model": pick["model"]}
        except ValueError:
            suggestions[agent_key] = None

    return {"skill": skill_id, "suggestions": suggestions}
