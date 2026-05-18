"""create provider_registry table — replaces hardcoded PROVIDERS dict in code

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-16
"""

import json
from alembic import op
import sqlalchemy as sa

revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None

_PROVIDERS = [
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


def upgrade() -> None:
    conn = op.get_bind()

    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS provider_registry (
            id            UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
            provider_key  TEXT    NOT NULL UNIQUE,
            name          TEXT    NOT NULL,
            description   TEXT    NOT NULL DEFAULT '',
            display_order INT     NOT NULL DEFAULT 0,
            auth_config   JSONB   NOT NULL DEFAULT '{}',
            is_enabled    BOOLEAN NOT NULL DEFAULT true,
            updated_at    TIMESTAMPTZ DEFAULT now()
        );
    """))

    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_provider_registry_key ON provider_registry (provider_key);"
    ))

    for p in _PROVIDERS:
        conn.execute(sa.text("""
            INSERT INTO provider_registry
                (provider_key, name, description, display_order, auth_config)
            VALUES (:key, :name, :desc, :order, :cfg)
            ON CONFLICT (provider_key) DO NOTHING
        """), {
            "key":   p["provider_key"],
            "name":  p["name"],
            "desc":  p["description"],
            "order": p["display_order"],
            "cfg":   json.dumps(p["auth_config"]),
        })


def downgrade() -> None:
    op.drop_index('idx_provider_registry_key', table_name='provider_registry')
    op.drop_table('provider_registry')
