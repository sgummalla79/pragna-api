"""ensure llm_models.llm_provider_id is NOT NULL FK to llm_providers

Revision ID: 0025
Revises: 0024
Create Date: 2026-05-18
"""
from alembic import op
import sqlalchemy as sa

revision = '0025'
down_revision = '0024'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # Add column if not already present (0024 may have already added it)
    conn.execute(sa.text("""
        ALTER TABLE llm_models
        ADD COLUMN IF NOT EXISTS llm_provider_id UUID REFERENCES llm_providers(id) ON DELETE CASCADE
    """))

    # Enforce NOT NULL — safe since llm_models has no data yet
    conn.execute(sa.text("""
        ALTER TABLE llm_models
        ALTER COLUMN llm_provider_id SET NOT NULL
    """))

    conn.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_llm_models_provider_id ON llm_models(llm_provider_id)
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP INDEX IF EXISTS idx_llm_models_provider_id"))
    conn.execute(sa.text("ALTER TABLE llm_models ALTER COLUMN llm_provider_id DROP NOT NULL"))
