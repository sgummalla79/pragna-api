from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from repositories.base import BaseRepository


@dataclass
class Agent:
    id:           str
    skill_id:     str
    name:         str
    display_name: Optional[str]
    content:      str
    created_at:   str
    modified_at:  str


class AgentRepository(BaseRepository):

    async def get_by_id(self, agent_id: str) -> Optional[Agent]:
        row = await self._fetchone(
            "SELECT id, skill_id, name, display_name, content, created_at, modified_at"
            " FROM skill_agents WHERE id = %s",
            (agent_id,),
        )
        return self._row_to_agent(row) if row else None

    async def get_by_key(self, skill_id: str, name: str) -> Optional[Agent]:
        row = await self._fetchone(
            "SELECT id, skill_id, name, display_name, content, created_at, modified_at"
            " FROM skill_agents WHERE skill_id = %s AND name = %s",
            (skill_id, name),
        )
        return self._row_to_agent(row) if row else None

    async def get_by_skill(self, skill_id: str) -> list[Agent]:
        rows = await self._fetchall(
            "SELECT id, skill_id, name, display_name, content, created_at, modified_at"
            " FROM skill_agents WHERE skill_id = %s ORDER BY name",
            (skill_id,),
        )
        return [self._row_to_agent(r) for r in rows]

    async def upsert(
        self,
        skill_id:     str,
        name:         str,
        display_name: Optional[str],
        content:      str,
    ) -> Agent:
        now = datetime.now(timezone.utc).isoformat()
        await self._exec(
            "INSERT INTO skill_agents (skill_id, name, display_name, content, created_at, modified_at)"
            " VALUES (%s, %s, %s, %s, %s, %s)"
            " ON CONFLICT (skill_id, name) DO UPDATE SET"
            "   display_name = EXCLUDED.display_name,"
            "   content      = EXCLUDED.content",
            (skill_id, name, display_name, content, now, now),
        )
        return await self.get_by_key(skill_id, name)

    @staticmethod
    def _row_to_agent(row) -> Agent:
        return Agent(
            id=str(row[0]), skill_id=str(row[1]), name=row[2],
            display_name=row[3], content=row[4],
            created_at=str(row[5]), modified_at=str(row[6]),
        )
