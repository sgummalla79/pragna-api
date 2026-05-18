from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from repositories.base import BaseRepository


@dataclass
class Agent:
    id:              str
    skill_id:        str
    agent_key:       str
    label:           Optional[str]
    default_content: str
    created_at:      str


class AgentRepository(BaseRepository):

    async def get_by_id(self, agent_id: str) -> Optional[Agent]:
        row = await self._fetchone(
            "SELECT id, skill_id, agent_key, label, default_content, created_at"
            " FROM agents WHERE id = %s",
            (agent_id,),
        )
        return self._row_to_agent(row) if row else None

    async def get_by_key(self, skill_id: str, agent_key: str) -> Optional[Agent]:
        row = await self._fetchone(
            "SELECT id, skill_id, agent_key, label, default_content, created_at"
            " FROM agents WHERE skill_id = %s AND agent_key = %s",
            (skill_id, agent_key),
        )
        return self._row_to_agent(row) if row else None

    async def get_by_skill(self, skill_id: str) -> list[Agent]:
        rows = await self._fetchall(
            "SELECT id, skill_id, agent_key, label, default_content, created_at"
            " FROM agents WHERE skill_id = %s ORDER BY agent_key",
            (skill_id,),
        )
        return [self._row_to_agent(r) for r in rows]

    async def upsert(
        self,
        skill_id:        str,
        agent_key:       str,
        label:           Optional[str],
        default_content: str,
    ) -> Agent:
        now = datetime.now(timezone.utc).isoformat()
        await self._exec(
            "INSERT INTO agents (skill_id, agent_key, label, default_content, created_at)"
            " VALUES (%s, %s, %s, %s, %s)"
            " ON CONFLICT (skill_id, agent_key) DO UPDATE SET"
            "   label = EXCLUDED.label,"
            "   default_content = EXCLUDED.default_content",
            (skill_id, agent_key, label, default_content, now),
        )
        return await self.get_by_key(skill_id, agent_key)

    @staticmethod
    def _row_to_agent(row) -> Agent:
        return Agent(
            id=str(row[0]), skill_id=str(row[1]), agent_key=row[2],
            label=row[3], default_content=row[4], created_at=str(row[5]),
        )
