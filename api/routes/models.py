"""
Active models endpoint — used by chat and agent config dropdowns.

GET /api/models/active  — all active models across all active providers
"""

from fastapi import APIRouter, Depends, Request
from utils.auth import AuthUser, get_current_user

router = APIRouter(prefix="/api/models")


@router.get(
    "/active",
    tags=["Models"],
    summary="All active models across connected providers",
    responses={200: {"description": "Active models grouped with provider metadata"}},
)
async def active_models(
    request:      Request,
    current_user: AuthUser = Depends(get_current_user),
):
    """
    Return all models the user has marked active, grouped by provider.
    Only includes models whose provider is also active (isactive=TRUE in user_llm_providers).
    """
    db           = request.app.state.db
    key_statuses  = await db.users.get_llm_provider_key_statuses(current_user.sub)
    active_models = await db.llm_models.get_active(current_user.sub)
    registry      = await db.provider_registry.get_all()
    registry_map  = {e.provider_key: e for e in registry}

    def provider_is_active(provider_key: str) -> bool:
        if provider_key == "bedrock":
            return key_statuses.get("anthropic_bedrock_url", False)
        return key_statuses.get(provider_key, False)

    result = []
    for m in active_models:
        if not provider_is_active(m.provider_key):
            continue
        entry = registry_map.get(m.provider_key)
        result.append({
            "provider":      m.provider_key,
            "provider_name": entry.name         if entry else m.provider_key,
            "capabilities":  entry.capabilities if entry else {},
            "model_id":      m.model_id,
            "display_name":  m.display_name,
        })

    return {"models": result}
