"""
LLM provider management routes.

GET    /api/providers                     — list providers (connected/isactive)
POST   /api/providers/bedrock/connect     — save Bedrock credentials + seed models
PATCH  /api/providers/bedrock/toggle      — toggle Bedrock isactive (cascades to models)
DELETE /api/providers/bedrock             — remove Bedrock credentials + delete models
POST   /api/providers/{id}/connect        — save API key + seed models
PATCH  /api/providers/{id}/toggle         — toggle provider isactive (cascades to models)
DELETE /api/providers/{id}               — remove API key + delete models

GET    /api/providers/{id}/models                      — list models with isactive for provider
PATCH  /api/providers/{id}/models/{mid}               — toggle one model active/inactive
PUT    /api/providers/{id}/models/{mid}/display-name  — update model display name
POST   /api/providers/{id}/refresh                    — re-fetch models from LLM API, reset all inactive

GET    /api/models/active                 — all active models across providers (for dropdowns)
GET    /api/providers/model-info          — metadata for a specific model
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from utils.auth import AuthUser, get_current_user
from utils.key_encryption import encrypt

log    = logging.getLogger(__name__)
router = APIRouter(prefix="/api/providers")


class ConnectRequest(BaseModel):
    api_key: str


class BedrockConnectRequest(BaseModel):
    bedrock_url:   str
    bedrock_token: str


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _fetch_and_seed_models(
    db, user_id: str, provider_key: str, api_key: str
) -> tuple[int, str | None]:
    """
    Fetch available models from the LLM provider and seed user_llm_models (all inactive).
    Returns (count, error_message).
    - Provider key is always saved regardless of fetch outcome.
    - Existing models are NOT deleted if the fetch fails.
    """
    from utils.provider_registry import fetch_models

    fetch_error: str | None = None
    models = []

    catalog = await db.model_catalog.get_by_provider(provider_key)
    catalog_models = [{"model_id": c.model_id, "display_name": c.display_name} for c in catalog]

    try:
        models = await fetch_models(provider_key, api_key, catalog_models=catalog_models)
    except Exception as exc:
        fetch_error = str(exc)
        log.warning("Could not fetch models for provider '%s': %s", provider_key, exc)
        return 0, fetch_error   # bail out — do not wipe existing models

    try:
        await db.llm_models.seed(user_id, provider_key, models)
    except Exception as exc:
        log.error("Could not seed models for provider '%s': %s", provider_key, exc)
        return 0, str(exc)

    return len(models), None


# ── List providers ─────────────────────────────────────────────────────────────

@router.get(
    "",
    tags=["Providers"],
    summary="List all providers with connection status",
    responses={200: {"description": "All provider entries with connected/isactive flags"}},
)
async def list_providers(request: Request, current_user: AuthUser = Depends(get_current_user)):
    db           = request.app.state.db
    key_statuses = await db.users.get_llm_provider_key_statuses(current_user.sub)

    registry  = await db.provider_registry.get_all()
    providers = []
    for entry in registry:
        pid      = entry.provider_key
        has_key  = pid in key_statuses
        isactive = key_statuses.get(pid, False)
        providers.append({
            "id":          pid,
            "name":        entry.name,
            "connected":   has_key,
            "isactive":    isactive,
            "description": entry.description,
            "auth_config": entry.auth_config,
        })

    # AWS Bedrock virtual tile
    has_bedrock    = "anthropic_bedrock_url" in key_statuses
    bedrock_active = key_statuses.get("anthropic_bedrock_url", False)
    providers.append({
        "id":          "bedrock",
        "name":        "AWS Bedrock",
        "connected":   has_bedrock,
        "isactive":    bedrock_active,
        "description": "Claude models via AWS Bedrock",
    })

    return {"providers": providers}


# ── AWS Bedrock (literal routes — before /{provider_id}) ──────────────────────

@router.post(
    "/bedrock/connect",
    tags=["Providers"],
    summary="Connect AWS Bedrock",
    responses={200: {"description": "Bedrock credentials saved and catalog models seeded"}},
)
async def connect_bedrock(
    body:         BedrockConnectRequest,
    request:      Request,
    current_user: AuthUser = Depends(get_current_user),
):
    db = request.app.state.db
    await db.users.save_llm_provider_key(current_user.sub, "anthropic_bedrock_url",   encrypt(body.bedrock_url,   current_user.sub))
    await db.users.save_llm_provider_key(current_user.sub, "anthropic_bedrock_token", encrypt(body.bedrock_token, current_user.sub))
    await db.users.save_llm_provider_key(current_user.sub, "anthropic_mode",          encrypt("bedrock",           current_user.sub))

    catalog = await db.model_catalog.get_by_provider("bedrock")
    models  = [{"model_id": c.model_id, "display_name": c.display_name} for c in catalog]
    await db.llm_models.seed(current_user.sub, "bedrock", models)
    return {"ok": True, "provider": "bedrock", "models_seeded": len(models)}


@router.patch(
    "/bedrock/toggle",
    tags=["Providers"],
    summary="Toggle AWS Bedrock active/inactive",
    responses={200: {"description": "Bedrock active state toggled"}},
)
async def toggle_bedrock(
    request:      Request,
    current_user: AuthUser = Depends(get_current_user),
):
    db       = request.app.state.db
    statuses = await db.users.get_llm_provider_key_statuses(current_user.sub)
    if "anthropic_bedrock_url" not in statuses:
        raise HTTPException(status_code=404, detail="AWS Bedrock is not configured.")
    new_isactive = not statuses["anthropic_bedrock_url"]
    for key in ("anthropic_bedrock_url", "anthropic_bedrock_token"):
        if key in statuses:
            await db.users.set_llm_provider_key_active(current_user.sub, key, new_isactive)
    if not new_isactive:
        await db.llm_models.deactivate_all(current_user.sub, "bedrock")
    return {"ok": True, "provider": "bedrock", "isactive": new_isactive}


@router.delete(
    "/bedrock",
    tags=["Providers"],
    summary="Disconnect AWS Bedrock",
    responses={200: {"description": "Bedrock credentials and models removed"}},
)
async def disconnect_bedrock(
    request:      Request,
    current_user: AuthUser = Depends(get_current_user),
):
    db = request.app.state.db
    for key in ("anthropic_bedrock_url", "anthropic_bedrock_token", "anthropic_mode"):
        await db.users.delete_llm_provider_key(current_user.sub, key)
    await db.llm_models.delete_all(current_user.sub, "bedrock")
    return {"ok": True, "provider": "bedrock"}


# ── model-info (literal — before /{provider_id}) ──────────────────────────────

@router.get(
    "/model-info",
    tags=["Providers"],
    summary="Get metadata for a specific model",
    responses={200: {"description": "Model metadata (context window, capabilities, etc.)"}},
)
async def model_info(
    provider: str,
    model:    str,
    request:  Request,
    current_user: AuthUser = Depends(get_current_user),
):
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
    db    = request.app.state.db
    entry = await db.provider_registry.get_by_key(provider_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider_id}")
    # Ensure user row exists before any FK-referencing inserts
    await db.users.upsert(current_user.sub, current_user.email, current_user.name, None)
    enc = encrypt(body.api_key, current_user.sub)
    await db.users.save_llm_provider_key(current_user.sub, provider_id, enc)
    count, err = await _fetch_and_seed_models(db, current_user.sub, provider_id, body.api_key)
    return {"ok": True, "provider": provider_id, "models_seeded": count, "fetch_error": err}


@router.patch(
    "/{provider_id}/toggle",
    tags=["Providers"],
    summary="Toggle provider active/inactive",
    responses={
        200: {"description": "Provider active state toggled"},
        404: {"description": "No key stored for provider"},
    },
)
async def toggle_provider(
    provider_id:  str,
    request:      Request,
    current_user: AuthUser = Depends(get_current_user),
):
    db       = request.app.state.db
    statuses = await db.users.get_llm_provider_key_statuses(current_user.sub)
    if provider_id not in statuses:
        raise HTTPException(status_code=404, detail=f"No key stored for provider '{provider_id}'.")
    new_isactive = not statuses[provider_id]
    await db.users.set_llm_provider_key_active(current_user.sub, provider_id, new_isactive)
    if not new_isactive:
        await db.llm_models.deactivate_all(current_user.sub, provider_id)
    return {"ok": True, "provider": provider_id, "isactive": new_isactive}


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
    db = request.app.state.db
    await db.users.delete_llm_provider_key(current_user.sub, provider_id)
    await db.llm_models.delete_all(current_user.sub, provider_id)
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
    db     = request.app.state.db
    models = await db.llm_models.get_for_provider(current_user.sub, provider_id)
    return {
        "provider": provider_id,
        "models": [
            {"model_id": m.model_id, "display_name": m.display_name, "isactive": m.isactive}
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
    db        = request.app.state.db
    new_state = await db.llm_models.toggle(current_user.sub, provider_id, model_id)
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
    if not body.display_name.strip():
        raise HTTPException(status_code=422, detail="display_name cannot be empty.")
    db   = request.app.state.db
    found = await db.llm_models.rename(current_user.sub, provider_id, model_id, body.display_name)
    if not found:
        raise HTTPException(status_code=404, detail="Model not found.")
    return {"ok": True, "provider": provider_id, "model_id": model_id, "display_name": body.display_name.strip()}


@router.post(
    "/{provider_id}/refresh",
    tags=["Providers"],
    summary="Re-fetch and re-seed models from provider API",
    responses={
        200: {"description": "Models refreshed from provider API"},
        404: {"description": "Provider not connected"},
        422: {"description": "Cannot refresh — provider key not found or decrypt failed"},
    },
)
async def refresh_provider_models(
    provider_id:  str,
    request:      Request,
    current_user: AuthUser = Depends(get_current_user),
):
    """Delete all models for this provider, re-fetch from API, re-seed as inactive."""
    db       = request.app.state.db
    statuses = await db.users.get_llm_provider_key_statuses(current_user.sub)

    if provider_id == "bedrock":
        catalog = await db.model_catalog.get_by_provider("bedrock")
        models  = [{"model_id": c.model_id, "display_name": c.display_name} for c in catalog]
        await db.llm_models.seed(current_user.sub, "bedrock", models)
        return {"ok": True, "provider": "bedrock", "models_seeded": len(models)}

    if provider_id not in statuses:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' not connected.")

    from utils.key_encryption import decrypt
    enc_keys = await db.users.get_all_llm_provider_keys(current_user.sub)
    enc_key  = enc_keys.get(provider_id)
    if not enc_key:
        raise HTTPException(status_code=422, detail="Cannot refresh — provider key not found.")
    try:
        api_key = decrypt(enc_key, current_user.sub)
    except Exception:
        raise HTTPException(status_code=422, detail="Cannot refresh — failed to decrypt provider key.")

    count, err   = await _fetch_and_seed_models(db, current_user.sub, provider_id, api_key)
    return {"ok": True, "provider": provider_id, "models_seeded": count, "fetch_error": err}
