"""drop provider_catalog and provider_registry — replaced by user_llm_models and providers_catalog.py constants

Revision ID: 0018
Revises: 0017
Create Date: 2026-05-18
"""
from alembic import op
import sqlalchemy as sa

revision = '0018'
down_revision = '0017'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP TABLE IF EXISTS provider_catalog CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS provider_registry CASCADE"))


def downgrade() -> None:
    pass  # intentionally irreversible — data is now in user_llm_models / constants
