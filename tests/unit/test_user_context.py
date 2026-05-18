"""
Unit tests for utils/user_context.py — ContextVar and execution store.
No mocking needed — tests the module's own state directly.
"""

import pytest
from utils.user_context import (
    set_user_context,
    get_user_key,
    has_key,
    connected_providers,
    register_execution_keys,
    unregister_execution_keys,
    get_execution_keys,
    get_execution_mode,
    get_anthropic_mode,
)


def test_set_and_get_user_key():
    set_user_context({"anthropic": "sk-test-key"}, "direct")
    assert get_user_key("anthropic") == "sk-test-key"


def test_get_user_key_raises_when_missing():
    set_user_context({}, "direct")
    with pytest.raises(RuntimeError, match="API key not configured for 'openai'"):
        get_user_key("openai")


def test_has_key_true_and_false():
    set_user_context({"google": "AIza-test"}, "direct")
    assert has_key("google") is True
    assert has_key("openai") is False


def test_get_anthropic_mode():
    set_user_context({"anthropic": "key"}, "bedrock")
    assert get_anthropic_mode() == "bedrock"

    set_user_context({"anthropic": "key"}, "direct")
    assert get_anthropic_mode() == "direct"


def test_connected_providers():
    set_user_context({
        "anthropic":  "sk-ant-key",
        "openai":     "sk-oai-key",
        "google":     "",           # empty → not connected
        "perplexity": None,         # None → not connected
    }, "direct")
    connected = connected_providers()
    assert "anthropic" in connected
    assert "openai"    in connected
    assert "google"    not in connected
    assert "perplexity" not in connected


def test_register_and_unregister_execution_keys():
    keys = {"anthropic": "sk-exec-key", "openai": "oai-key"}
    register_execution_keys("exec-001", keys, "direct")

    assert get_execution_keys("exec-001") == keys
    assert get_execution_mode("exec-001") == "direct"

    unregister_execution_keys("exec-001")
    assert get_execution_keys("exec-001") == {}


def test_execution_keys_missing_returns_empty():
    assert get_execution_keys("nonexistent-exec") == {}
    assert get_execution_mode("nonexistent-exec") == "direct"


def test_register_skips_empty_inputs():
    register_execution_keys("", {"key": "val"}, "direct")    # empty execution_id
    register_execution_keys("exec-002", {}, "direct")          # empty keys
    assert get_execution_keys("") == {}
    assert get_execution_keys("exec-002") == {}
