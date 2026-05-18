"""
Auth routes.

GET  /auth/connections   list enabled social connections (Auth0 Management API, cached 1h)
GET  /auth/initiate      redirect browser to Auth0 /authorize
GET  /auth/callback      Auth0 returns here; exchange code, set cookie, redirect to SPA
POST /auth/token         email/password login; set cookie, return user JSON
POST /auth/logout        clear session cookie
GET  /auth/me            return current user from cookie (bootstrap on mount)
"""

import os
import logging
import time
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from utils.auth import AuthUser, get_current_user, _make_session_token, FRONTEND_URL

log = logging.getLogger(__name__)

router = APIRouter(prefix="/auth")

AUTH0_DOMAIN        = os.getenv("AUTH0_DOMAIN", "")
AUTH0_CLIENT_ID     = os.getenv("AUTH0_CLIENT_ID", "")
AUTH0_CLIENT_SECRET = os.getenv("AUTH0_CLIENT_SECRET", "")
AUTH0_CALLBACK_URL  = os.getenv("AUTH0_CALLBACK_URL", "http://localhost:5173/auth/callback")
_COOKIE_NAME        = "session"
_SECURE             = os.getenv("COOKIE_SECURE", "false").lower() == "true"

_KNOWN_LABELS: dict[str, str] = {
    "google-oauth2": "Google",
    "github":        "GitHub",
    "twitter":       "Twitter / X",
    "facebook":      "Facebook",
    "linkedin":      "LinkedIn",
    "microsoft":     "Microsoft",
    "apple":         "Apple",
    "windowslive":   "Microsoft",
}


def _set_session_cookie(response, token: str) -> None:
    response.set_cookie(
        key=_COOKIE_NAME, value=token,
        httponly=True, samesite="lax",
        secure=_SECURE, max_age=60 * 60 * 24 * 30,
    )


# ── Management API token (cached) ─────────────────────────────────────────────

_mgmt_token:      str   = ""
_mgmt_expires_at: float = 0.0


async def _get_mgmt_token() -> str:
    global _mgmt_token, _mgmt_expires_at
    if _mgmt_token and time.time() < _mgmt_expires_at:
        return _mgmt_token

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://{AUTH0_DOMAIN}/oauth/token",
            json={
                "grant_type":    "client_credentials",
                "client_id":     AUTH0_CLIENT_ID,
                "client_secret": AUTH0_CLIENT_SECRET,
                "audience":      f"https://{AUTH0_DOMAIN}/api/v2/",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

    _mgmt_token      = data["access_token"]
    _mgmt_expires_at = time.time() + data.get("expires_in", 86400) - 60
    return _mgmt_token


# ── Connections (cached 1 hour) ────────────────────────────────────────────────

_connections_cache:      list  = []
_connections_expires_at: float = 0.0


@router.get(
    "/connections",
    tags=["Auth"],
    summary="List Auth0 social login connections",
    responses={
        200: {"description": "List of enabled social connections"},
        502: {"description": "Auth0 Management API unreachable"},
    },
)
async def list_connections():
    global _connections_cache, _connections_expires_at

    if _connections_cache and time.time() < _connections_expires_at:
        return {"connections": _connections_cache}

    try:
        token = await _get_mgmt_token()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://{AUTH0_DOMAIN}/api/v2/connections",
                params={
                    "client_id": AUTH0_CLIENT_ID,
                    "fields":    "name,strategy,display_name,enabled_clients",
                },
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )
            resp.raise_for_status()
            raw = resp.json()

        _connections_cache = [
            {
                "name":         c["name"],
                "display_name": (c.get("display_name")
                                 or _KNOWN_LABELS.get(c["name"])
                                 or _KNOWN_LABELS.get(c["strategy"])
                                 or c["name"]),
                "strategy":     c["strategy"],
            }
            for c in raw
            if c.get("strategy") != "auth0"
            and AUTH0_CLIENT_ID in (c.get("enabled_clients") or [])
        ]
        _connections_expires_at = time.time() + 3600

    except Exception as exc:
        log.error("Auth0 connections fetch failed: %s", exc)
        _connections_cache = []

    return {"connections": _connections_cache}


# ── Initiate — redirect to Auth0 /authorize ────────────────────────────────────

@router.get(
    "/initiate",
    tags=["Auth"],
    summary="Redirect to Auth0 authorize",
    responses={302: {"description": "Redirect to Auth0 /authorize"}},
)
async def initiate(connection: str = ""):
    params = {
        "response_type": "code",
        "client_id":     AUTH0_CLIENT_ID,
        "redirect_uri":  AUTH0_CALLBACK_URL,
        "scope":         "openid profile email",
    }
    if connection:
        params["connection"] = connection

    url = f"https://{AUTH0_DOMAIN}/authorize?{urlencode(params)}"
    log.info("Auth0 initiate → redirect_uri=%s", AUTH0_CALLBACK_URL)
    return RedirectResponse(url)


# ── Callback — exchange code, set cookie, redirect to SPA ─────────────────────

@router.get(
    "/callback",
    tags=["Auth"],
    summary="Auth0 OAuth callback — set session cookie",
    responses={302: {"description": "Redirect to SPA with session cookie set"}},
)
async def callback(code: str, request: Request, error: str = ""):
    if error:
        return RedirectResponse(f"{FRONTEND_URL}/login?error={error}")

    log.info("Auth0 callback — code=%s...", code[:8])
    try:
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                f"https://{AUTH0_DOMAIN}/oauth/token",
                json={
                    "grant_type":    "authorization_code",
                    "client_id":     AUTH0_CLIENT_ID,
                    "client_secret": AUTH0_CLIENT_SECRET,
                    "code":          code,
                    "redirect_uri":  AUTH0_CALLBACK_URL,
                },
                timeout=15,
            )
            if not token_resp.is_success:
                raise ValueError(f"Token exchange failed: {token_resp.text}")
            tokens = token_resp.json()

            ui_resp = await client.get(
                f"https://{AUTH0_DOMAIN}/userinfo",
                headers={"Authorization": f"Bearer {tokens['access_token']}"},
                timeout=10,
            )
            userinfo = ui_resp.json()

    except Exception as exc:
        log.error("OAuth callback error: %s", exc)
        return RedirectResponse(f"{FRONTEND_URL}/login?error=auth_failed")

    user = AuthUser(
        sub     = userinfo["sub"],
        email   = userinfo.get("email", ""),
        name    = userinfo.get("name") or userinfo.get("nickname", ""),
        picture = userinfo.get("picture", ""),
    )

    db = request.app.state.db
    await db.users.upsert(user.sub, user.email, user.name, user.picture)

    token    = _make_session_token(user)
    redirect = RedirectResponse(f"{FRONTEND_URL}/")
    _set_session_cookie(redirect, token)
    log.info("Auth0 callback success — user=%s", user.email)
    return redirect


# ── Email / password login ─────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email:      str
    password:   str
    connection: str = "Username-Password-Authentication"


@router.post(
    "/token",
    tags=["Auth"],
    summary="Email/password login",
    responses={
        200: {"description": "Authenticated user JSON with session cookie"},
        401: {"description": "Bad credentials"},
    },
)
async def login_with_password(body: LoginRequest, request: Request):
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://{AUTH0_DOMAIN}/oauth/token",
            json={
                "grant_type":    "http://auth0.com/oauth/grant-type/password-realm",
                "realm":         body.connection,
                "username":      body.email,
                "password":      body.password,
                "client_id":     AUTH0_CLIENT_ID,
                "client_secret": AUTH0_CLIENT_SECRET,
                "scope":         "openid profile email",
            },
            timeout=15,
        )

    if not resp.is_success:
        detail = resp.json().get("error_description") or "Invalid email or password."
        raise HTTPException(status_code=401, detail=detail)

    tokens = resp.json()

    async with httpx.AsyncClient() as client:
        ui = await client.get(
            f"https://{AUTH0_DOMAIN}/userinfo",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
            timeout=10,
        )
    userinfo = ui.json()

    user = AuthUser(
        sub     = userinfo["sub"],
        email   = userinfo.get("email", body.email),
        name    = userinfo.get("name") or userinfo.get("nickname", ""),
        picture = userinfo.get("picture", ""),
    )

    db = request.app.state.db
    await db.users.upsert(user.sub, user.email, user.name, user.picture)

    token    = _make_session_token(user)
    response = JSONResponse({"user": {
        "sub": user.sub, "email": user.email,
        "name": user.name, "picture": user.picture,
    }})
    _set_session_cookie(response, token)
    return response


# ── Logout ────────────────────────────────────────────────────────────────────

@router.post(
    "/logout",
    tags=["Auth"],
    summary="Clear session cookie",
    responses={200: {"description": "Session cookie cleared"}},
)
async def logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie(_COOKIE_NAME)
    return response


# ── Me (bootstrap) ────────────────────────────────────────────────────────────

@router.get(
    "/me",
    tags=["Auth"],
    summary="Get current authenticated user",
    responses={
        200: {"description": "Current user object"},
        401: {"description": "Not authenticated"},
    },
)
async def me(current_user: AuthUser = Depends(get_current_user)):
    return {
        "sub":     current_user.sub,
        "email":   current_user.email,
        "name":    current_user.name,
        "picture": current_user.picture,
    }
