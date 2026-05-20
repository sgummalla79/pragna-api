"""
User settings routes.

GET  /api/settings/theme   — get current theme preference
POST /api/settings/theme   — save theme preference
"""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from repositories.constants import ConfigKey
from utils.auth import AuthUser, get_current_user

router = APIRouter(prefix="/settings")


@router.get(
    "/theme",
    tags=["Settings"],
    summary="Get current theme preference",
    responses={200: {"description": "Current theme name"}},
)
async def get_theme(
    request:      Request,
    current_user: AuthUser = Depends(get_current_user),
):
    """Return the user's saved theme preference, or 'default' if not set."""
    db    = request.app.state.db
    theme = await db.user_config.get(current_user.sub, ConfigKey.THEME)
    return {"theme": theme or "default"}


class ThemeRequest(BaseModel):
    theme: str


@router.post(
    "/theme",
    tags=["Settings"],
    summary="Save theme preference",
    responses={200: {"description": "Theme saved"}},
)
async def save_theme(
    body:         ThemeRequest,
    request:      Request,
    current_user: AuthUser = Depends(get_current_user),
):
    """Persist the user's theme preference in user_config."""
    db = request.app.state.db
    await db.user_config.upsert(current_user.sub, ConfigKey.THEME, body.theme)
    return {"ok": True, "theme": body.theme}
