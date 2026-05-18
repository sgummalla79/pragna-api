"""
Unit tests for utils/auth.py — JWT encoding/decoding and session token.
Auth0 HTTP calls are mocked.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


def _make_token(user):
    from utils.auth import _make_session_token
    return _make_session_token(user)


def _decode(token):
    from utils.auth import _decode_session_cookie
    return _decode_session_cookie(token)


def test_session_token_roundtrip():
    from utils.auth import AuthUser
    user = AuthUser(sub="auth0|123", email="test@example.com", name="Test", picture=None)
    token   = _make_token(user)
    payload = _decode(token)
    assert payload["sub"]   == "auth0|123"
    assert payload["email"] == "test@example.com"
    assert payload["name"]  == "Test"


def test_invalid_token_raises():
    from jose import JWTError
    with pytest.raises(Exception):
        _decode("not.a.valid.jwt")


async def test_get_current_user_from_cookie():
    from utils.auth import AuthUser, get_current_user
    user = AuthUser(sub="auth0|abc", email="u@e.com")
    token = _make_token(user)

    request = MagicMock()
    request.cookies = {"session": token}
    request.app.state.db.users.get_all_llm_provider_keys = AsyncMock(return_value={})

    with patch("utils.auth._inject_user_keys", new_callable=AsyncMock):
        result = await get_current_user(request, creds=None)

    assert result.sub   == "auth0|abc"
    assert result.email == "u@e.com"


async def test_get_current_user_no_token_raises():
    from fastapi import HTTPException
    from utils.auth import get_current_user

    request = MagicMock()
    request.cookies = {}

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(request, creds=None)

    assert exc_info.value.status_code == 401


async def test_exchange_code_for_tokens():
    from utils.auth import exchange_code_for_tokens
    fake_tokens = {"access_token": "abc123", "id_token": "xyz"}

    with patch("utils.auth.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__  = AsyncMock(return_value=None)
        mock_response = MagicMock()
        mock_response.json.return_value = fake_tokens
        mock_response.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        result = await exchange_code_for_tokens("test-code")

    assert result["access_token"] == "abc123"


async def test_get_userinfo():
    from utils.auth import get_userinfo
    fake_info = {"sub": "auth0|999", "email": "me@test.com", "name": "Me"}

    with patch("utils.auth.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__  = AsyncMock(return_value=None)
        mock_response = MagicMock()
        mock_response.json.return_value = fake_info
        mock_response.raise_for_status = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        result = await get_userinfo("access-token-123")

    assert result["sub"] == "auth0|999"
