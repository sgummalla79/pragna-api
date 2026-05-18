from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

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


@dataclass
class ConversationSkill:
    id:              str   # = skill_snapshot_id
    conversation_id: str
    skill_id:        str
    added_at:        str


@dataclass
class ConversationSkillAgent:
    id:                    str
    conversation_skill_id: str
    agent_id:              str
    version:               int
    content:               str   # frozen prompt — never updated
    provider:              Optional[str]  # modifiable if model becomes invalid
    model:                 Optional[str]  # modifiable if model becomes invalid


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

    # ── Skill snapshot management ─────────────────────────────────────────────

    async def add_skill(
        self,
        conversation_id: str,
        skill_id:        str,
        agents:          list,   # list[UserAgent] with content + model resolved
    ) -> ConversationSkill:
        """Add a skill to a conversation and create the frozen agent snapshot."""
        now = datetime.now(timezone.utc).isoformat()
        row = await self._fetchone(
            "INSERT INTO conversation_skills (conversation_id, skill_id, added_at)"
            " VALUES (%s, %s, %s) RETURNING id",
            (conversation_id, skill_id, now),
        )
        cs_id = str(row[0])

        for item in agents:
            await self._exec(
                "INSERT INTO conversation_skill_agents"
                " (conversation_skill_id, agent_id, version, content, provider, model)"
                " VALUES (%s, %s, %s, %s, %s, %s)",
                (cs_id, item["agent_id"], item["version"],
                 item["content"], item["provider"], item["model"]),
            )

        return ConversationSkill(
            id=cs_id, conversation_id=conversation_id,
            skill_id=skill_id, added_at=now,
        )

    async def remove_skill(self, conversation_skill_id: str) -> None:
        await self._exec(
            "DELETE FROM conversation_skills WHERE id = %s",
            (conversation_skill_id,),
        )

    async def get_skill(self, conversation_skill_id: str) -> Optional[ConversationSkill]:
        row = await self._fetchone(
            "SELECT id, conversation_id, skill_id, added_at"
            " FROM conversation_skills WHERE id = %s",
            (conversation_skill_id,),
        )
        if not row:
            return None
        return ConversationSkill(
            id=str(row[0]), conversation_id=str(row[1]),
            skill_id=str(row[2]), added_at=str(row[3]),
        )

    async def get_skills_for_conversation(self, conversation_id: str) -> list[ConversationSkill]:
        rows = await self._fetchall(
            "SELECT id, conversation_id, skill_id, added_at"
            " FROM conversation_skills WHERE conversation_id = %s ORDER BY added_at",
            (conversation_id,),
        )
        return [
            ConversationSkill(id=str(r[0]), conversation_id=str(r[1]),
                              skill_id=str(r[2]), added_at=str(r[3]))
            for r in rows
        ]

    async def get_skill_agents(self, conversation_skill_id: str) -> list[ConversationSkillAgent]:
        rows = await self._fetchall(
            "SELECT id, conversation_skill_id, agent_id, version, content, provider, model"
            " FROM conversation_skill_agents WHERE conversation_skill_id = %s",
            (conversation_skill_id,),
        )
        return [self._row_to_csa(r) for r in rows]

    async def update_agent_model(
        self,
        conversation_skill_agent_id: str,
        provider:                    Optional[str],
        model:                       Optional[str],
    ) -> None:
        await self._exec(
            "UPDATE conversation_skill_agents SET provider = %s, model = %s WHERE id = %s",
            (provider, model, conversation_skill_agent_id),
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

    @staticmethod
    def _row_to_csa(row) -> ConversationSkillAgent:
        return ConversationSkillAgent(
            id=str(row[0]), conversation_skill_id=str(row[1]),
            agent_id=str(row[2]), version=row[3], content=row[4],
            provider=row[5], model=row[6],
        )
