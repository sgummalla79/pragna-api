"""
Static provider catalog — replaces the provider_registry DB table.

Adding a new provider: add an entry to PROVIDERS and add a fetch function
in utils/provider_registry.py. No DB migration needed.
"""

PROVIDERS: list[dict] = [
    {
        "provider_key":  "anthropic",
        "name":          "Anthropic",
        "description":   "Claude models",
        "display_order": 1,
        "auth_config": {
            "auth_modes": [
                {
                    "id":    "direct",
                    "label": "Direct API",
                    "fields": [
                        {"key": "anthropic", "label": "API Key", "placeholder": "sk-ant-api03-…"},
                    ],
                },
                {
                    "id":    "bedrock",
                    "label": "AWS Bedrock",
                    "fields": [
                        {"key": "anthropic_bedrock_url",   "label": "Bedrock Base URL", "placeholder": "https://…"},
                        {"key": "anthropic_bedrock_token", "label": "Auth Token",       "placeholder": "…"},
                    ],
                },
            ],
        },
    },
    {
        "provider_key":  "openai",
        "name":          "OpenAI",
        "description":   "GPT-4o, o3, o4-mini and more",
        "display_order": 2,
        "auth_config": {
            "auth_modes": [
                {
                    "id":    "direct",
                    "label": "Direct API",
                    "fields": [
                        {"key": "openai", "label": "API Key", "placeholder": "sk-proj-…"},
                    ],
                },
            ],
        },
    },
    {
        "provider_key":  "google",
        "name":          "Google",
        "description":   "Gemini models",
        "display_order": 3,
        "auth_config": {
            "auth_modes": [
                {
                    "id":    "direct",
                    "label": "Direct API",
                    "fields": [
                        {"key": "google", "label": "API Key", "placeholder": "AIza…"},
                    ],
                },
            ],
        },
    },
    {
        "provider_key":  "perplexity",
        "name":          "Perplexity",
        "description":   "Sonar search-grounded models",
        "display_order": 4,
        "auth_config": {
            "auth_modes": [
                {
                    "id":    "direct",
                    "label": "Direct API",
                    "fields": [
                        {"key": "perplexity", "label": "API Key", "placeholder": "pplx-…"},
                    ],
                },
            ],
        },
    },
    {
        "provider_key":  "groq",
        "name":          "Groq",
        "description":   "Fast inference — Llama, Mixtral, Gemma",
        "display_order": 5,
        "auth_config": {
            "auth_modes": [
                {
                    "id":    "direct",
                    "label": "Direct API",
                    "fields": [
                        {"key": "groq", "label": "API Key", "placeholder": "gsk_…"},
                    ],
                },
            ],
        },
    },
]

_BY_KEY: dict[str, dict] = {p["provider_key"]: p for p in PROVIDERS}


def get_provider(provider_key: str) -> dict | None:
    return _BY_KEY.get(provider_key)


def get_all_providers() -> list[dict]:
    return PROVIDERS
