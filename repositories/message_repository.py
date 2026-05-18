from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from repositories.base import BaseRepository


@dataclass
class Message:
    id:              str
    conversation_id: str
    execution_id:    Optional[str]
    role:            str   # user | assistant
    content:         Optional[str]
    message_type:    str   # chat | stage_summary | question | user_answer | confirmation | artifact_ref
    message_state:   str   # visible | hidden
    artifact_id:     Optional[str]
    created_at:      str


class MessageRepository(BaseRepository):

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
        now = datetime.now(timezone.utc).isoformat()
        row = await self._fetchone(
            "INSERT INTO conversation_messages"
            " (conversation_id, execution_id, role, content, message_type, message_state, artifact_id, created_at)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (conversation_id, execution_id, role, content, message_type, message_state, artifact_id, now),
        )
        return Message(
            id=str(row[0]), conversation_id=conversation_id,
            execution_id=execution_id, role=role, content=content,
            message_type=message_type, message_state=message_state,
            artifact_id=artifact_id, created_at=now,
        )

    async def list_for_conversation(
        self,
        conversation_id: str,
        limit:           int = 200,
        visible_only:    bool = False,
    ) -> list[Message]:
        base_sql = (
            "SELECT id, conversation_id, execution_id, role, content,"
            "       message_type, message_state, artifact_id, created_at"
            " FROM conversation_messages WHERE conversation_id = %s"
        )
        if visible_only:
            base_sql += " AND message_state = 'visible'"
        base_sql += f" ORDER BY created_at ASC LIMIT {limit}"

        rows = await self._fetchall(base_sql, (conversation_id,))
        return [self._row_to_msg(r) for r in rows]

    async def set_artifact(self, message_id: str, artifact_id: str) -> None:
        await self._exec(
            "UPDATE conversation_messages SET artifact_id = %s WHERE id = %s",
            (artifact_id, message_id),
        )

    @staticmethod
    def _row_to_msg(row) -> Message:
        return Message(
            id=str(row[0]), conversation_id=str(row[1]),
            execution_id=str(row[2]) if row[2] else None,
            role=row[3], content=row[4],
            message_type=row[5], message_state=row[6],
            artifact_id=str(row[7]) if row[7] else None,
            created_at=str(row[8]),
        )
