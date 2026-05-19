from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional  # used by Conversation dataclass fields

from repositories.base import BaseRepository


@dataclass
class Conversation:
    id:            str
    user_id:       str
    title:         Optional[str]
    chat_provider: Optional[str]
    chat_model:    Optional[str]
    created_at:    str
    last_modified: str
    pinned:        bool = False
    pinned_at:     Optional[str] = None


class ConversationRepository(BaseRepository):

    async def create(
        self,
        user_id:       str,
        title:         Optional[str],
        chat_provider: Optional[str],
        chat_model:    Optional[str],
    ) -> Conversation:
        now = datetime.now(timezone.utc).isoformat()
        row = await self._fetchone(
            "INSERT INTO conversations (user_id, title, chat_provider, chat_model, created_at, last_modified)"
            " VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
            (user_id, title, chat_provider, chat_model, now, now),
        )
        return await self.get_by_id(str(row[0]))

    async def get_by_id(self, conversation_id: str) -> Optional[Conversation]:
        row = await self._fetchone(
            "SELECT id, user_id, title, chat_provider, chat_model, created_at, last_modified,"
            "       COALESCE(pinned, 0), pinned_at"
            " FROM conversations WHERE id = %s AND COALESCE(archived, FALSE) = FALSE",
            (conversation_id,),
        )
        return self._row_to_conv(row) if row else None

    async def list_for_user(self, user_id: str) -> list[Conversation]:
        rows = await self._fetchall(
            "SELECT id, user_id, title, chat_provider, chat_model, created_at, last_modified,"
            "       COALESCE(pinned, 0), pinned_at"
            " FROM conversations WHERE user_id = %s AND COALESCE(archived, FALSE) = FALSE"
            " ORDER BY last_modified DESC",
            (user_id,),
        )
        return [self._row_to_conv(r) for r in rows]

    async def pin(self, conversation_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await self._exec(
            "UPDATE conversations SET pinned = 1, pinned_at = %s WHERE id = %s",
            (now, conversation_id),
        )

    async def unpin(self, conversation_id: str) -> None:
        await self._exec(
            "UPDATE conversations SET pinned = 0, pinned_at = NULL WHERE id = %s",
            (conversation_id,),
        )

    async def rename(self, conversation_id: str, title: str) -> None:
        await self._exec(
            "UPDATE conversations SET title = %s WHERE id = %s",
            (title, conversation_id),
        )

    async def archive(self, conversation_id: str) -> None:
        await self._exec(
            "UPDATE conversations SET archived = TRUE WHERE id = %s",
            (conversation_id,),
        )

    async def touch(self, conversation_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await self._exec(
            "UPDATE conversations SET last_modified = %s WHERE id = %s",
            (now, conversation_id),
        )

    @staticmethod
    def _row_to_conv(row) -> Conversation:
        return Conversation(
            id=str(row[0]), user_id=row[1], title=row[2],
            chat_provider=row[3], chat_model=row[4],
            created_at=str(row[5]), last_modified=str(row[6]),
            pinned=bool(row[7]) if len(row) > 7 else False,
            pinned_at=str(row[8]) if len(row) > 8 and row[8] else None,
        )
