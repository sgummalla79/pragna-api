"""
Unit tests for framework/defaults.py — smart_pick and resolve_agent_config.
"""

import pytest
from framework.defaults import smart_pick, resolve_agent_config, available_providers

# Sample active models used across tests
_ANTHROPIC_MODELS = [
    {"provider": "anthropic", "model_id": "claude-opus-4-7"},
    {"provider": "anthropic", "model_id": "claude-sonnet-4-6"},
]
_GOOGLE_MODELS = [
    {"provider": "google", "model_id": "gemini-2.5-pro"},
    {"provider": "google", "model_id": "gemini-2.0-flash"},
]
_PERPLEXITY_MODELS = [
    {"provider": "perplexity", "model_id": "sonar-pro"},
]
_OPENAI_MODELS = [
    {"provider": "openai", "model_id": "gpt-4o"},
]


def test_smart_pick_researcher_search_prefers_perplexity():
    connected     = {"perplexity", "anthropic"}
    active_models = _PERPLEXITY_MODELS + _ANTHROPIC_MODELS
    result        = smart_pick("researcher_search", connected, active_models)
    assert result["provider"] == "perplexity"
    assert result["model"]    == "sonar-pro"


def test_smart_pick_researcher_search_falls_back_to_google():
    connected     = {"google", "anthropic"}
    active_models = _GOOGLE_MODELS + _ANTHROPIC_MODELS
    result        = smart_pick("researcher_search", connected, active_models)
    assert result["provider"] == "google"


def test_smart_pick_researcher_reasoning_prefers_google():
    connected     = {"google", "anthropic", "openai"}
    active_models = _GOOGLE_MODELS + _ANTHROPIC_MODELS + _OPENAI_MODELS
    result        = smart_pick("researcher_reasoning", connected, active_models)
    assert result["provider"] == "google"
    assert result["model"]    == "gemini-2.5-pro"


def test_smart_pick_approver_prefers_anthropic():
    connected     = {"anthropic", "google"}
    active_models = _ANTHROPIC_MODELS + _GOOGLE_MODELS
    result        = smart_pick("approver", connected, active_models)
    assert result["provider"] == "anthropic"


def test_smart_pick_default_slot_prefers_anthropic():
    connected     = {"anthropic", "openai"}
    active_models = _ANTHROPIC_MODELS + _OPENAI_MODELS
    result        = smart_pick("discovery", connected, active_models)
    assert result["provider"] == "anthropic"


def test_smart_pick_raises_when_no_active_models():
    with pytest.raises(ValueError, match="No models are activated"):
        smart_pick("discovery", {"anthropic"}, [])


def test_smart_pick_raises_when_no_providers():
    with pytest.raises(ValueError):
        smart_pick("discovery", set(), [])


def test_resolve_agent_config_uses_snapshot():
    agent_slot_map = {"discovery": "discovery", "review": "reviewer"}
    snapshot_cfg   = {
        "discovery": {"provider": "anthropic", "model": "claude-sonnet-4-6"},
        "review":    {"provider": "google",    "model": "gemini-2.0-flash"},
    }
    connected = {"anthropic", "google"}
    result = resolve_agent_config(agent_slot_map, snapshot_cfg, connected)
    assert result["discovery"]["provider"] == "anthropic"
    assert result["review"]["provider"]    == "google"


def test_resolve_agent_config_smart_picks_when_provider_disconnected():
    agent_slot_map = {"discovery": "discovery"}
    snapshot_cfg   = {"discovery": {"provider": "perplexity", "model": "sonar-pro"}}
    connected      = {"anthropic"}   # perplexity not connected
    active_models  = _ANTHROPIC_MODELS
    result = resolve_agent_config(agent_slot_map, snapshot_cfg, connected, active_models)
    assert result["discovery"]["provider"] == "anthropic"


def test_available_providers_filters_empty_values():
    keys = {"anthropic": "sk-real-key", "openai": "", "google": None}
    providers = available_providers({k: v for k, v in keys.items() if v})
    assert "anthropic" in providers
    assert "openai" not in providers
    assert "google" not in providers
