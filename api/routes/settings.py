"""
User settings routes.

GET  /api/settings/theme   — get current theme preference
POST /api/settings/theme   — save theme preference
"""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from utils.auth import AuthUser, get_current_user

router = APIRouter(prefix="/api/settings")


@router.get(
    "/theme",
    tags=["Settings"],
    summary="Get current theme preference",
    responses={200: {"description": "Current theme name"}},
)
async def get_theme(request: Request, current_user: AuthUser = Depends(get_current_user)):
    db    = request.app.state.db
    theme = await db.users.get_config(current_user.sub, "theme")
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
    db = request.app.state.db
    await db.users.save_config(current_user.sub, "theme", body.theme)
    return {"ok": True, "theme": body.theme}
