"""create model_pricing table

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-16
"""

from alembic import op
import sqlalchemy as sa

revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS model_pricing (
            id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            model_id          TEXT        NOT NULL UNIQUE,
            provider          TEXT        NOT NULL,
            input_usd_per_1m  NUMERIC(12,6) NOT NULL DEFAULT 0,
            output_usd_per_1m NUMERIC(12,6) NOT NULL DEFAULT 0,
            updated_at        TIMESTAMPTZ DEFAULT now()
        );
    """))

    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_model_pricing_model ON model_pricing (model_id);"
    ))

    # Seed with known prices — update via API endpoint as prices change
    conn.execute(sa.text("""
        INSERT INTO model_pricing (model_id, provider, input_usd_per_1m, output_usd_per_1m) VALUES
            ('claude-sonnet-4-6',         'anthropic',  3.00,  15.00),
            ('claude-opus-4-7',           'anthropic', 15.00,  75.00),
            ('claude-haiku-4-5-20251001', 'anthropic',  0.80,   4.00),
            ('gpt-4o',                    'openai',     2.50,  10.00),
            ('gpt-4o-mini',               'openai',     0.15,   0.60),
            ('gemini-2.5-pro',            'google',     1.25,  10.00),
            ('gemini-2.0-flash',          'google',     0.10,   0.40),
            ('sonar-pro',                 'perplexity', 3.00,  15.00),
            ('sonar',                     'perplexity', 1.00,   1.00)
        ON CONFLICT (model_id) DO NOTHING;
    """))


def downgrade() -> None:
    op.drop_index('idx_model_pricing_model', table_name='model_pricing')
    op.drop_table('model_pricing')
