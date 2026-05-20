"""
ConversationRepository — CRUD for the `conversations` table.

Owns all reads and writes to the conversations table. Does not touch related
tables (messages, artifacts, skill snapshots) — those are owned by their
respective repositories.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from repositories.base import BaseRepository


@dataclass
class Conversation:
    """Represents one row in the `conversations` table."""
    id:            str
    user_id:       str
    title:         Optional[str]
    chat_provider: Optional[str]
    chat_model:    Optional[str]
    created_at:    str
    modified_at:   str
    pinned:        bool
    pinned_at:     Optional[str]
    archived:      bool


class ConversationRepository(BaseRepository):
    """Pure CRUD repository for the `conversations` table."""

    async def create(
        self,
        user_id:       str,
        title:         Optional[str]  = None,
        chat_provider: Optional[str]  = None,
        chat_model:    Optional[str]  = None,
    ) -> Conversation:
        """
        Insert a new conversation row.

        Sets both created_at and modified_at to the current UTC time.
        Returns the full conversation row.
        """
        now = self._now()
        row = await self._fetchone(
            "INSERT INTO conversations"
            "  (user_id, title, chat_provider, chat_model, created_at, modified_at,"
            "   pinned, archived)"
            " VALUES (%s, %s, %s, %s, %s, %s, FALSE, FALSE)"
            " RETURNING id, user_id, title, chat_provider, chat_model,"
            "           created_at, modified_at, pinned, pinned_at, archived",
            (user_id, title, chat_provider, chat_model, now, now),
        )
        return self._row(row)

    async def get_by_id(self, conversation_id: str) -> Optional[Conversation]:
        """
        Return the conversation with the given UUID, or None.

        Excludes archived conversations — use an explicit filter if you need those.
        """
        row = await self._fetchone(
            "SELECT id, user_id, title, chat_provider, chat_model,"
            "       created_at, modified_at, pinned, pinned_at, archived"
            " FROM conversations"
            " WHERE id = %s AND archived = FALSE",
            (conversation_id,),
        )
        return self._row(row) if row else None

    async def list_for_user(self, user_id: str) -> list[Conversation]:
        """
        Return all non-archived conversations for a user, ordered by most recently modified.
        """
        rows = await self._fetchall(
            "SELECT id, user_id, title, chat_provider, chat_model,"
            "       created_at, modified_at, pinned, pinned_at, archived"
            " FROM conversations"
            " WHERE user_id = %s AND archived = FALSE"
            " ORDER BY modified_at DESC",
            (user_id,),
        )
        return [self._row(r) for r in rows]

    async def update_title(self, conversation_id: str, title: str) -> None:
        """Update the conversation title and set modified_at."""
        await self._exec(
            "UPDATE conversations SET title = %s, modified_at = %s WHERE id = %s",
            (title, self._now(), conversation_id),
        )

    async def update_chat_model(
        self,
        conversation_id: str,
        chat_provider:   Optional[str],
        chat_model:      Optional[str],
    ) -> None:
        """Update the default provider and model for chat messages and set modified_at."""
        await self._exec(
            "UPDATE conversations"
            " SET chat_provider = %s, chat_model = %s, modified_at = %s"
            " WHERE id = %s",
            (chat_provider, chat_model, self._now(), conversation_id),
        )

    async def update_pinned(
        self, conversation_id: str, pinned: bool, pinned_at: Optional[str] = None
    ) -> None:
        """
        Set the pinned state for a conversation.

        When pinning, pass pinned_at=self._now() from the caller. When unpinning,
        pass pinned_at=None to clear the timestamp.
        """
        await self._exec(
            "UPDATE conversations SET pinned = %s, pinned_at = %s, modified_at = %s"
            " WHERE id = %s",
            (pinned, pinned_at, self._now(), conversation_id),
        )

    async def update_archived(self, conversation_id: str, archived: bool) -> None:
        """Soft-delete (or restore) a conversation by toggling the archived flag."""
        await self._exec(
            "UPDATE conversations SET archived = %s, modified_at = %s WHERE id = %s",
            (archived, self._now(), conversation_id),
        )

    async def touch(self, conversation_id: str) -> None:
        """
        Update modified_at to the current time without changing any other field.

        Called after sending a message or starting an execution to keep the
        conversation sorted correctly in the recent list.
        """
        await self._exec(
            "UPDATE conversations SET modified_at = %s WHERE id = %s",
            (self._now(), conversation_id),
        )

    @staticmethod
    def _row(row) -> Conversation:
        """Map a raw DB row to a Conversation dataclass."""
        return Conversation(
            id=str(row[0]), user_id=row[1], title=row[2],
            chat_provider=row[3], chat_model=row[4],
            created_at=str(row[5]), modified_at=str(row[6]),
            pinned=bool(row[7]),
            pinned_at=str(row[8]) if row[8] else None,
            archived=bool(row[9]),
        )
