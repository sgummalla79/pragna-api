"""
Active models endpoint — used by chat and agent config dropdowns.

GET /api/models/active  — all active models across all active providers
"""

from fastapi import APIRouter, Depends, Request
from utils.auth import AuthUser, get_current_user
from utils.providers_catalog import get_provider

router = APIRouter(prefix="/models")


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
    Return all models the user has marked active, filtered to only include
    models whose provider is also active (has a stored API key and is_active=True).
    """
    services      = request.app.state.services
    key_statuses  = await services.providers.get_key_statuses(current_user.sub)
    active        = await services.llm_models.get_active(current_user.sub)

    def provider_is_active(provider_key: str) -> bool:
        """Return True if the provider has a connected and active key."""
        return key_statuses.get(provider_key, False)

    result = []
    for m in active:
        if not provider_is_active(m.provider_key):
            continue
        entry = get_provider(m.provider_key)
        result.append({
            "provider":      m.provider_key,
            "provider_name": entry["name"] if entry else m.provider_key,
            "model_id":      m.model_name,
            "display_name":  m.display_name,
        })

    return {"models": result}
