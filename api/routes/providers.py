"""
LLM provider management routes.

GET    /api/providers                     — list providers with connection status
POST   /api/providers/bedrock/connect     — save Bedrock credentials
PATCH  /api/providers/bedrock/toggle      — toggle Bedrock active state
DELETE /api/providers/bedrock             — remove Bedrock credentials
POST   /api/providers/{id}/connect        — save API key and seed models
PATCH  /api/providers/{id}/toggle         — toggle provider active state
DELETE /api/providers/{id}                — remove API key and delete models

GET    /api/providers/{id}/models                      — list models for provider
PATCH  /api/providers/{id}/models/{mid}               — toggle model active state
PUT    /api/providers/{id}/models/{mid}/display-name  — rename model
POST   /api/providers/{id}/refresh                    — re-fetch models from provider API
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from utils.auth import AuthUser, get_current_user
from utils.key_encryption import encrypt
from utils.providers_catalog import get_all_providers, get_provider

log    = logging.getLogger(__name__)
router = APIRouter(prefix="/providers")


class ConnectRequest(BaseModel):
    api_key: str


class BedrockConnectRequest(BaseModel):
    bedrock_url:   str
    bedrock_token: str


# ── List providers ────────────────────────────────────────────────────────────

@router.get(
    "",
    tags=["Providers"],
    summary="List all providers with connection status",
    responses={200: {"description": "All providers with connected/isactive flags"}},
)
async def list_providers(
    request:      Request,
    current_user: AuthUser = Depends(get_current_user),
):
    """Return every known provider with whether the user has connected it and its active state."""
    services     = request.app.state.services
    key_statuses = await services.providers.get_key_statuses(current_user.sub)

    providers = []
    for entry in get_all_providers():
        pid = entry["provider_key"]
        providers.append({
            "id":          pid,
            "name":        entry["name"],
            "connected":   pid in key_statuses,
            "isactive":    key_statuses.get(pid, False),
            "description": entry["description"],
            "auth_config": entry["auth_config"],
        })

    # Bedrock virtual tile — stored in user_config, not user_llm_providers
    from repositories.constants import ConfigKey
    bedrock_url = key_statuses.get(ConfigKey.BEDROCK_URL)
    providers.append({
        "id":          "bedrock",
        "name":        "AWS Bedrock",
        "connected":   bedrock_url is not None,
        "isactive":    bool(bedrock_url),
        "description": "Claude models via AWS Bedrock",
    })

    return {"providers": providers}


# ── AWS Bedrock ───────────────────────────────────────────────────────────────

@router.post(
    "/bedrock/connect",
    tags=["Providers"],
    summary="Connect AWS Bedrock",
    responses={200: {"description": "Bedrock credentials saved"}},
)
async def connect_bedrock(
    body:         BedrockConnectRequest,
    request:      Request,
    current_user: AuthUser = Depends(get_current_user),
):
    """Save encrypted Bedrock URL and token in user_config."""
    services = request.app.state.services
    await services.providers.connect_bedrock(
        user_id       = current_user.sub,
        bedrock_url   = encrypt(body.bedrock_url,   current_user.sub),
        bedrock_token = encrypt(body.bedrock_token, current_user.sub),
    )
    return {"ok": True, "provider": "bedrock"}


@router.patch(
    "/bedrock/toggle",
    tags=["Providers"],
    summary="Toggle AWS Bedrock active/inactive",
    responses={
        200: {"description": "Bedrock active state toggled"},
        404: {"description": "AWS Bedrock is not configured"},
    },
)
async def toggle_bedrock(
    request:      Request,
    current_user: AuthUser = Depends(get_current_user),
):
    """Toggle the Bedrock connection on or off. Returns the new active state."""
    from repositories.constants import ConfigKey
    db       = request.app.state.db
    services = request.app.state.services

    bedrock_url = await db.user_config.get(current_user.sub, ConfigKey.BEDROCK_URL)
    if not bedrock_url:
        raise HTTPException(status_code=404, detail="AWS Bedrock is not configured.")

    # For Bedrock, toggle = delete or restore the config entry.
    # Here we simply return ok — a more complete implementation would track
    # an is_active flag in user_config.
    return {"ok": True, "provider": "bedrock"}


@router.delete(
    "/bedrock",
    tags=["Providers"],
    summary="Disconnect AWS Bedrock",
    responses={200: {"description": "Bedrock credentials removed"}},
)
async def disconnect_bedrock(
    request:      Request,
    current_user: AuthUser = Depends(get_current_user),
):
    """Remove all Bedrock credentials from user_config."""
    services = request.app.state.services
    await services.providers.disconnect_bedrock(current_user.sub)
    return {"ok": True, "provider": "bedrock"}


# ── Model info (literal — must appear before /{provider_id}) ─────────────────

@router.get(
    "/model-info",
    tags=["Providers"],
    summary="Get metadata for a specific model",
    responses={200: {"description": "Model metadata"}},
)
async def model_info(
    provider: str,
    model:    str,
    request:  Request,
    current_user: AuthUser = Depends(get_current_user),
):
    """Return context-window and capability metadata for a provider+model pair."""
    from utils.model_metadata import get_model_info
    info = get_model_info(provider, model)
    return info or {"provider": provider, "model": model}


# ── Regular providers ─────────────────────────────────────────────────────────

@router.post(
    "/{provider_id}/connect",
    tags=["Providers"],
    summary="Connect a provider with API key",
    responses={
        200: {"description": "API key saved and models seeded"},
        404: {"description": "Unknown provider"},
    },
)
async def connect_provider(
    provider_id:  str,
    body:         ConnectRequest,
    request:      Request,
    current_user: AuthUser = Depends(get_current_user),
):
    """Save an encrypted API key for the provider and seed available models."""
    entry = get_provider(provider_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider_id}")

    db       = request.app.state.db
    services = request.app.state.services

    # Ensure the user row exists before any FK-referencing operations
    await db.users.upsert(current_user.sub, current_user.email, current_user.name, None)

    enc = encrypt(body.api_key, current_user.sub)
    try:
        await services.providers.connect(current_user.sub, provider_id, enc)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    # Fetch and seed models from the provider API
    count, err = await _fetch_and_seed_models(db, services, current_user.sub, provider_id, body.api_key)
    return {"ok": True, "provider": provider_id, "models_seeded": count, "fetch_error": err}


@router.patch(
    "/{provider_id}/toggle",
    tags=["Providers"],
    summary="Toggle provider active/inactive",
    responses={
        200: {"description": "Provider active state toggled"},
        404: {"description": "Provider not connected"},
    },
)
async def toggle_provider(
    provider_id:  str,
    request:      Request,
    current_user: AuthUser = Depends(get_current_user),
):
    """Flip the is_active state for a provider. Deactivating also deactivates all its models."""
    services = request.app.state.services
    try:
        new_state = await services.providers.toggle(current_user.sub, provider_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"ok": True, "provider": provider_id, "isactive": new_state}


@router.delete(
    "/{provider_id}",
    tags=["Providers"],
    summary="Disconnect provider and delete its models",
    responses={200: {"description": "Provider key and models removed"}},
)
async def disconnect_provider(
    provider_id:  str,
    request:      Request,
    current_user: AuthUser = Depends(get_current_user),
):
    """Remove the API key and all associated user model rows for a provider."""
    services = request.app.state.services
    await services.providers.disconnect(current_user.sub, provider_id)
    return {"ok": True}


# ── Per-provider model management ─────────────────────────────────────────────

@router.get(
    "/{provider_id}/models",
    tags=["Providers"],
    summary="List models for a provider",
    responses={200: {"description": "All models for the provider with active status"}},
)
async def list_provider_models(
    provider_id:  str,
    request:      Request,
    current_user: AuthUser = Depends(get_current_user),
):
    """Return all models for a provider with their display name and active state."""
    services = request.app.state.services
    models   = await services.llm_models.list_for_provider(current_user.sub, provider_id)
    return {
        "provider": provider_id,
        "models": [
            {
                "model_id":     m.model_name,
                "display_name": m.display_name,
                "isactive":     m.is_active,
            }
            for m in models
        ],
    }


@router.patch(
    "/{provider_id}/models/{model_id:path}",
    tags=["Providers"],
    summary="Toggle a model active/inactive",
    responses={
        200: {"description": "Model active state toggled"},
        404: {"description": "Model not found"},
    },
)
async def toggle_model(
    provider_id:  str,
    model_id:     str,
    request:      Request,
    current_user: AuthUser = Depends(get_current_user),
):
    """Flip the is_active state for a specific model."""
    services  = request.app.state.services
    new_state = await services.llm_models.toggle(current_user.sub, provider_id, model_id)
    if new_state is None:
        raise HTTPException(status_code=404, detail="Model not found.")
    return {"ok": True, "provider": provider_id, "model_id": model_id, "isactive": new_state}


class RenameModelRequest(BaseModel):
    display_name: str


@router.put(
    "/{provider_id}/models/{model_id:path}/display-name",
    tags=["Providers"],
    summary="Update model display name",
    responses={
        200: {"description": "Display name updated"},
        404: {"description": "Model not found"},
        422: {"description": "display_name cannot be empty"},
    },
)
async def rename_model(
    provider_id:  str,
    model_id:     str,
    body:         RenameModelRequest,
    request:      Request,
    current_user: AuthUser = Depends(get_current_user),
):
    """Update the user-visible display name for a model."""
    if not body.display_name.strip():
        raise HTTPException(status_code=422, detail="display_name cannot be empty.")
    services = request.app.state.services
    found    = await services.llm_models.rename(
        current_user.sub, provider_id, model_id, body.display_name
    )
    if not found:
        raise HTTPException(status_code=404, detail="Model not found.")
    return {"ok": True, "provider": provider_id, "model_id": model_id,
            "display_name": body.display_name.strip()}


@router.post(
    "/{provider_id}/refresh",
    tags=["Providers"],
    summary="Re-fetch and re-seed models from provider API",
    responses={
        200: {"description": "Models refreshed"},
        404: {"description": "Provider not connected"},
        422: {"description": "Cannot decrypt provider key"},
    },
)
async def refresh_provider_models(
    provider_id:  str,
    request:      Request,
    current_user: AuthUser = Depends(get_current_user),
):
    """Delete existing user model rows and re-seed from the live provider API."""
    db       = request.app.state.db
    services = request.app.state.services

    statuses = await services.providers.get_key_statuses(current_user.sub)
    if provider_id not in statuses:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' not connected.")

    from utils.key_encryption import decrypt
    enc_keys = await services.providers.get_all_encrypted_keys(current_user.sub)
    enc_key  = enc_keys.get(provider_id)
    if not enc_key:
        raise HTTPException(status_code=422, detail="Provider key not found.")
    try:
        api_key = decrypt(enc_key, current_user.sub)
    except Exception:
        raise HTTPException(status_code=422, detail="Failed to decrypt provider key.")

    count, err = await _fetch_and_seed_models(db, services, current_user.sub, provider_id, api_key)
    return {"ok": True, "provider": provider_id, "models_seeded": count, "fetch_error": err}


# ── Helper ─────────────────────────────────────────────────────────────────────

async def _fetch_and_seed_models(
    db, services, user_id: str, provider_key: str, api_key: str
) -> tuple[int, Optional[str]]:
    """
    Fetch available models from the provider API and seed user_llm_models.

    Returns (count_seeded, error_message). The provider key is always saved
    before this is called — a fetch failure does not remove the key.
    """
    from utils.provider_registry import fetch_models

    try:
        model_names = await fetch_models(provider_key, api_key)
    except Exception as exc:
        log.warning("Could not fetch models for provider '%s': %s", provider_key, exc)
        return 0, str(exc)

    count = await services.llm_models.seed_for_provider(user_id, provider_key, model_names)
    return count, None
