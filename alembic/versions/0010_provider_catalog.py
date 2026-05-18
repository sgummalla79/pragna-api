"""create provider_catalog table for providers without model listing APIs

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-16
"""

from alembic import op
import sqlalchemy as sa

revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS provider_catalog (
            id           UUID  PRIMARY KEY DEFAULT gen_random_uuid(),
            provider     TEXT  NOT NULL,
            model_id     TEXT  NOT NULL,
            display_name TEXT  NOT NULL,
            updated_at   TIMESTAMPTZ DEFAULT now(),
            CONSTRAINT uq_provider_catalog UNIQUE (provider, model_id)
        );
    """))

    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_provider_catalog_provider ON provider_catalog (provider);"
    ))

    # Seed static model lists for providers without public model listing APIs
    conn.execute(sa.text("""
        INSERT INTO provider_catalog (provider, model_id, display_name) VALUES
            ('bedrock',     'us.anthropic.claude-opus-4-7',           'Claude Opus 4.7'),
            ('bedrock',     'us.anthropic.claude-sonnet-4-6',         'Claude Sonnet 4.6'),
            ('bedrock',     'us.anthropic.claude-haiku-4-5-20251001', 'Claude Haiku 4.5'),
            ('perplexity',  'sonar-pro',                              'Sonar Pro'),
            ('perplexity',  'sonar',                                  'Sonar'),
            ('perplexity',  'sonar-reasoning-pro',                    'Sonar Reasoning Pro'),
            ('perplexity',  'sonar-deep-research',                    'Sonar Deep Research')
        ON CONFLICT (provider, model_id) DO NOTHING;
    """))


def downgrade() -> None:
    op.drop_index('idx_provider_catalog_provider', table_name='provider_catalog')
    op.drop_table('provider_catalog')
