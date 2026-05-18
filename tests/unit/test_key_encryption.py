"""
Unit tests for utils/key_encryption.py — Fernet per-user encryption.
"""

import pytest


def test_encrypt_decrypt_roundtrip():
    from utils.key_encryption import encrypt, decrypt
    value    = "sk-ant-real-api-key-here"
    user_id  = "auth0|user-123"
    token    = encrypt(value, user_id)
    assert decrypt(token, user_id) == value


def test_different_users_produce_different_ciphertext():
    from utils.key_encryption import encrypt
    value = "same-api-key"
    enc1  = encrypt(value, "user-001")
    enc2  = encrypt(value, "user-002")
    assert enc1 != enc2   # per-user key derivation


def test_wrong_user_cannot_decrypt():
    from utils.key_encryption import encrypt, decrypt
    from cryptography.fernet import InvalidToken
    token = encrypt("secret", "user-A")
    with pytest.raises(Exception):   # InvalidToken or similar
        decrypt(token, "user-B")


def test_missing_settings_secret_raises():
    import os
    from unittest.mock import patch
    with patch.dict(os.environ, {"SETTINGS_SECRET": ""}):
        with pytest.raises(RuntimeError, match="SETTINGS_SECRET"):
            from utils.key_encryption import _master_bytes
            # Force re-evaluation
            import importlib, utils.key_encryption as m
            importlib.reload(m)
            m._master_bytes()


def test_get_key_reads_from_context_var():
    from utils.user_context import set_user_context
    from utils.key_encryption import get_key
    set_user_context({"anthropic": "sk-test"}, "direct")
    assert get_key("anthropic") == "sk-test"


def test_get_anthropic_mode_reads_from_context():
    from utils.user_context import set_user_context
    from utils.key_encryption import get_anthropic_mode
    set_user_context({}, "bedrock")
    assert get_anthropic_mode() == "bedrock"
