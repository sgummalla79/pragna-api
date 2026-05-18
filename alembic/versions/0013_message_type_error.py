"""add error to message_type check constraint

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-17
"""
from alembic import op

revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE conversation_messages DROP CONSTRAINT IF EXISTS conversation_messages_message_type_check")
    op.execute("""
        ALTER TABLE conversation_messages
        ADD CONSTRAINT conversation_messages_message_type_check
        CHECK (message_type IN (
            'chat', 'stage_summary', 'question', 'user_answer',
            'confirmation', 'artifact_ref', 'error'
        ))
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE conversation_messages DROP CONSTRAINT IF EXISTS conversation_messages_message_type_check")
    op.execute("""
        ALTER TABLE conversation_messages
        ADD CONSTRAINT conversation_messages_message_type_check
        CHECK (message_type IN (
            'chat', 'stage_summary', 'question', 'user_answer',
            'confirmation', 'artifact_ref'
        ))
    """)
