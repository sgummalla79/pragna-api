"""
MessageRepository — CRUD for the `conversation_messages` table.

Stores every message in a conversation: user inputs, assistant replies,
artifact references, questions, and error notices. Supports filtering by
visibility state and paging by row limit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from repositories.base import BaseRepository
from repositories.constants import MessageRole, MessageState, MessageType


@dataclass
class Message:
    """Represents one row in the `conversation_messages` table."""
    id:              str
    conversation_id: str
    execution_id:    Optional[str]
    role:            str   # MessageRole constant
    content:         Optional[str]
    message_type:    str   # MessageType constant
    message_state:   str   # MessageState constant
    artifact_id:     Optional[str]
    created_at:      str
    modified_at:     str


class MessageRepository(BaseRepository):
    """Pure CRUD repository for the `conversation_messages` table."""

    async def create(
        self,
        conversation_id: str,
        role:            str,
        content:         Optional[str],
        message_type:    str,
        message_state:   str,
        execution_id:    Optional[str] = None,
        artifact_id:     Optional[str] = None,
    ) -> Message:
        """
        Insert a new message row.

        Sets created_at and modified_at to the current UTC time.
        Returns the inserted message as a typed dataclass.
        """
        now = self._now()
        row = await self._fetchone(
            "INSERT INTO conversation_messages"
            "  (conversation_id, execution_id, role, content, message_type,"
            "   message_state, artifact_id, created_at, modified_at)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
            " RETURNING id, conversation_id, execution_id, role, content,"
            "           message_type, message_state, artifact_id, created_at, modified_at",
            (conversation_id, execution_id, role, content, message_type,
             message_state, artifact_id, now, now),
        )
        return self._row(row)

    async def get_by_id(self, message_id: str) -> Optional[Message]:
        """Return the message with the given UUID, or None."""
        row = await self._fetchone(
            "SELECT id, conversation_id, execution_id, role, content,"
            "       message_type, message_state, artifact_id, created_at, modified_at"
            " FROM conversation_messages WHERE id = %s",
            (message_id,),
        )
        return self._row(row) if row else None

    async def list_for_conversation(
        self,
        conversation_id: str,
        limit:           int  = 200,
        visible_only:    bool = False,
    ) -> list[Message]:
        """
        Return messages for a conversation in chronological order.

        Args:
            limit: Maximum number of rows to return. Defaults to 200.
            visible_only: When True, exclude messages with state 'hidden'.
        """
        # Build the query dynamically — only the WHERE clause changes.
        # LIMIT is passed as a parameter to avoid string interpolation.
        if visible_only:
            sql = (
                "SELECT id, conversation_id, execution_id, role, content,"
                "       message_type, message_state, artifact_id, created_at, modified_at"
                " FROM conversation_messages"
                " WHERE conversation_id = %s AND message_state = %s"
                " ORDER BY created_at ASC LIMIT %s"
            )
            params = (conversation_id, MessageState.VISIBLE, limit)
        else:
            sql = (
                "SELECT id, conversation_id, execution_id, role, content,"
                "       message_type, message_state, artifact_id, created_at, modified_at"
                " FROM conversation_messages"
                " WHERE conversation_id = %s"
                " ORDER BY created_at ASC LIMIT %s"
            )
            params = (conversation_id, limit)

        rows = await self._fetchall(sql, params)
        return [self._row(r) for r in rows]

    async def update_artifact(self, message_id: str, artifact_id: str) -> None:
        """
        Link an artifact to a message and update modified_at.

        Called after an artifact is persisted to associate it with the message
        that prompted its creation.
        """
        await self._exec(
            "UPDATE conversation_messages"
            " SET artifact_id = %s, modified_at = %s"
            " WHERE id = %s",
            (artifact_id, self._now(), message_id),
        )

    @staticmethod
    def _row(row) -> Message:
        """Map a raw DB row to a Message dataclass."""
        return Message(
            id=str(row[0]), conversation_id=str(row[1]),
            execution_id=str(row[2]) if row[2] else None,
            role=row[3], content=row[4],
            message_type=row[5], message_state=row[6],
            artifact_id=str(row[7]) if row[7] else None,
            created_at=str(row[8]),
            modified_at=str(row[9]),
        )
