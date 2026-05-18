"""
Auth utilities — JWT verification and Auth0 OAuth helpers.
"""

from __future__ import annotations
import os
import logging
from dataclasses import dataclass
from typing import Optional

import httpx
from jose import jwt, JWTError
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

log = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)

AUTH0_DOMAIN        = os.getenv("AUTH0_DOMAIN", "")
AUTH0_CLIENT_ID     = os.getenv("AUTH0_CLIENT_ID", "")
AUTH0_CLIENT_SECRET = os.getenv("AUTH0_CLIENT_SECRET", "")
AUTH0_CALLBACK_URL  = os.getenv("AUTH0_CALLBACK_URL", "http://localhost:5173/callback")
JWT_SECRET          = os.getenv("JWT_SECRET", "change-me")
FRONTEND_URL        = os.getenv("FRONTEND_URL", "http://localhost:5173")


@dataclass
class AuthUser:
    sub:     str
    email:   str
    name:    Optional[str]   = None
    picture: Optional[str]   = None


def _decode_session_cookie(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])


def _make_session_token(user: AuthUser) -> str:
    return jwt.encode(
        {"sub": user.sub, "email": user.email, "name": user.name, "picture": user.picture},
        JWT_SECRET,
        algorithm="HS256",
    )


async def get_current_user(
    request: Request,
    creds:   Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> AuthUser:
    """
    Extract the authenticated user from either:
    - Authorization: Bearer <token> header
    - session httpOnly cookie
    """
    token = None
    if creds:
        token = creds.credentials
    else:
        token = request.cookies.get("session")

    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = _decode_session_cookie(token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    user = AuthUser(
        sub=payload["sub"],
        email=payload.get("email", ""),
        name=payload.get("name"),
        picture=payload.get("picture"),
    )

    # Inject user's decrypted API keys into ContextVar
    await _inject_user_keys(request, user)

    return user


async def _inject_user_keys(request: Request, user: AuthUser) -> None:
    """Load and decrypt the user's API keys into the request ContextVar."""
    try:
        db = request.app.state.db
        encrypted_keys = await db.users.get_all_llm_provider_keys(user.sub)
        from utils.key_encryption import decrypt
        from utils.user_context import set_user_context
        decrypted: dict[str, str] = {}
        for key_name, enc_val in encrypted_keys.items():
            try:
                decrypted[key_name] = decrypt(enc_val, user.sub)
            except Exception:
                decrypted[key_name] = ""
        mode = decrypted.get("anthropic_mode", "direct")
        set_user_context(decrypted, mode)
    except Exception as exc:
        log.warning("Failed to inject user keys: %s", exc)


async def exchange_code_for_tokens(code: str) -> dict:
    """Exchange Auth0 authorization code for tokens."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://{AUTH0_DOMAIN}/oauth/token",
            json={
                "grant_type":    "authorization_code",
                "client_id":     AUTH0_CLIENT_ID,
                "client_secret": AUTH0_CLIENT_SECRET,
                "code":          code,
                "redirect_uri":  AUTH0_CALLBACK_URL,
            },
        )
        resp.raise_for_status()
        return resp.json()


async def get_userinfo(access_token: str) -> dict:
    """Fetch user profile from Auth0 userinfo endpoint."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://{AUTH0_DOMAIN}/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.json()
