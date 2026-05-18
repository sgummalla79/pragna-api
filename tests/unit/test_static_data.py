"""
Unit tests for model_metadata.py.
_MODEL_INFO and _DISPLAY_NAMES are removed — get_model_info now just returns
provider + model + prettified display_name for any model.
"""


class TestModelMetadata:

    def test_known_model_returns_info(self):
        from utils.model_metadata import get_model_info
        info = get_model_info("anthropic", "claude-sonnet-4-6")
        assert info is not None
        assert info["model"]        == "claude-sonnet-4-6"
        assert info["provider"]     == "anthropic"
        assert info["display_name"] == "Claude Sonnet 4 6"

    def test_unknown_model_still_returns_prettified_name(self):
        from utils.model_metadata import get_model_info
        info = get_model_info("anthropic", "some-new-model-2025")
        assert info is not None
        assert info["display_name"] == "Some New Model 2025"

    def test_display_name_uses_prettify(self):
        from utils.model_metadata import get_model_info
        info = get_model_info("google", "gemini-1.5-pro")
        assert info["display_name"] == "Gemini 1.5 Pro"
