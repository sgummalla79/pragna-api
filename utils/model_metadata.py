"""
Model metadata — context window info for the /api/providers/model-info endpoint.
Display names are handled by provider_registry._prettify() at seed time.
"""


def get_model_info(provider: str, model: str) -> dict | None:
    """Return context window info if known, otherwise None."""
    from utils.provider_registry import _prettify
    return {
        "provider":     provider,
        "model":        model,
        "display_name": _prettify(model),
    }
