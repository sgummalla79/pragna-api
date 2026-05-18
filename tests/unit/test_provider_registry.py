"""
Unit tests for utils/provider_registry.py — per-provider model fetching.
All external SDK/HTTP calls are mocked.

fetch_models() returns list[{"model_id": str, "display_name": str}].
Helper: ids(result) extracts just the model_id strings for easy assertion.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def ids(models: list[dict]) -> list[str]:
    """Extract model_id strings from a list[dict] result."""
    return [m["model_id"] for m in models]


def has_display(models: list[dict]) -> bool:
    """Every entry must have a non-empty display_name."""
    return all(m.get("display_name") for m in models)


async def test_fetch_anthropic_direct():
    from utils.provider_registry import _fetch_anthropic

    mock_model = MagicMock()
    mock_model.id = "claude-sonnet-4-6"

    mock_response = MagicMock()
    mock_response.data = [mock_model]

    mock_client = AsyncMock()
    mock_client.models.list = AsyncMock(return_value=mock_response)

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        models = await _fetch_anthropic("sk-ant-test")

    assert "claude-sonnet-4-6" in ids(models)
    assert has_display(models)


async def test_fetch_openai():
    from utils.provider_registry import _fetch_openai

    mock_model = MagicMock()
    mock_model.id = "gpt-4o"

    mock_response = MagicMock()
    mock_response.data = [mock_model]

    mock_client = AsyncMock()
    mock_client.models.list = AsyncMock(return_value=mock_response)

    with patch("openai.AsyncOpenAI", return_value=mock_client):
        models = await _fetch_openai("sk-oai-test")

    assert "gpt-4o" in ids(models)
    assert has_display(models)


async def test_fetch_openai_excludes_non_chat_models():
    from utils.provider_registry import _fetch_openai

    m1 = MagicMock(); m1.id = "gpt-4o"
    m2 = MagicMock(); m2.id = "text-embedding-ada-002"
    m3 = MagicMock(); m3.id = "tts-1"
    m4 = MagicMock(); m4.id = "whisper-1"

    mock_response = MagicMock()
    mock_response.data = [m1, m2, m3, m4]

    mock_client = AsyncMock()
    mock_client.models.list = AsyncMock(return_value=mock_response)

    with patch("openai.AsyncOpenAI", return_value=mock_client):
        models = await _fetch_openai("sk-oai-test")

    model_ids = ids(models)
    assert "gpt-4o" in model_ids
    assert "text-embedding-ada-002" not in model_ids
    assert "tts-1" not in model_ids
    assert "whisper-1" not in model_ids


async def test_fetch_google():
    from utils.provider_registry import _fetch_google

    mock_model = MagicMock()
    mock_model.name = "models/gemini-2.5-pro"
    mock_model.supported_generation_methods = ["generateContent"]

    with patch("google.generativeai.configure"), \
         patch("google.generativeai.list_models", return_value=[mock_model]):
        models = await _fetch_google("AIza-test")

    assert "gemini-2.5-pro" in ids(models)
    assert has_display(models)


async def test_fetch_google_excludes_non_generative():
    from utils.provider_registry import _fetch_google

    m1 = MagicMock(); m1.name = "models/gemini-2.5-pro"
    m1.supported_generation_methods = ["generateContent"]
    m2 = MagicMock(); m2.name = "models/embedding-001"
    m2.supported_generation_methods = ["embedContent"]

    with patch("google.generativeai.configure"), \
         patch("google.generativeai.list_models", return_value=[m1, m2]):
        models = await _fetch_google("AIza-test")

    model_ids = ids(models)
    assert "gemini-2.5-pro" in model_ids
    assert "embedding-001" not in model_ids


async def test_fetch_perplexity_valid_key():
    from utils.provider_registry import _fetch_perplexity
    catalog = [
        {"model_id": "sonar-pro",            "display_name": "Sonar Pro"},
        {"model_id": "sonar",                "display_name": "Sonar"},
        {"model_id": "sonar-reasoning-pro",  "display_name": "Sonar Reasoning Pro"},
        {"model_id": "sonar-deep-research",  "display_name": "Sonar Deep Research"},
    ]
    models = await _fetch_perplexity("pplx-valid-key", catalog_models=catalog)
    assert ids(models) == [m["model_id"] for m in catalog]
    assert has_display(models)


async def test_fetch_perplexity_invalid_key_raises():
    from utils.provider_registry import _fetch_perplexity
    with pytest.raises(ValueError, match="pplx-"):
        await _fetch_perplexity("invalid-key-format")


async def test_fetch_groq():
    from utils.provider_registry import _fetch_groq

    mock_model = MagicMock(); mock_model.id = "llama-3.3-70b-versatile"
    mock_response = MagicMock(); mock_response.data = [mock_model]
    mock_client = AsyncMock()
    mock_client.models.list = AsyncMock(return_value=mock_response)

    with patch("openai.AsyncOpenAI", return_value=mock_client):
        models = await _fetch_groq("gsk-test")

    assert "llama-3.3-70b-versatile" in ids(models)
    assert has_display(models)


async def test_fetch_models_dispatches_correctly():
    from utils.provider_registry import fetch_models

    expected = [{"model_id": "claude-sonnet-4-6", "display_name": "Claude Sonnet 4 6"}]
    with patch("utils.provider_registry._fetch_anthropic",
               new=AsyncMock(return_value=expected)) as mock:
        result = await fetch_models("anthropic", "sk-ant-test")

    mock.assert_called_once_with("sk-ant-test", mode="direct",
                                 bedrock_url="", bedrock_token="", catalog_models=[])
    assert result == expected


async def test_fetch_models_unknown_provider_raises():
    from utils.provider_registry import fetch_models
    with pytest.raises(ValueError, match="Unknown provider"):
        await fetch_models("unknown-provider", "some-key")


def test_prettify():
    from utils.provider_registry import _prettify
    assert _prettify("claude-sonnet-4-6")       == "Claude Sonnet 4 6"
    assert _prettify("gpt-4o-mini")             == "GPT 4o Mini"
    assert _prettify("llama-3.3-70b-versatile") == "Llama 3.3 70b Versatile"
    assert _prettify("gemini-1.5-pro")          == "Gemini 1.5 Pro"
    assert _prettify("sonar-pro")               == "Sonar Pro"
    # Bedrock vendor prefix is stripped
    assert _prettify("us.anthropic.claude-sonnet-4-6") == "Claude Sonnet 4 6"
