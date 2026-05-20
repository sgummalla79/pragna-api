"""
AgentRepository — CRUD for the `skill_agents` table.

Stores the out-of-the-box agent definitions for each skill. Each agent has a
machine name (e.g. 'intake'), an optional display label, and a default system
prompt. Seeded at startup from disk; not user-specific.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from repositories.base import BaseRepository


@dataclass
class Agent:
    """Represents one row in the `skill_agents` table."""
    id:           str
    skill_id:     str   # UUID FK → skills(id)
    name:         str   # machine key, e.g. "intake", "discovery"
    display_name: Optional[str]
    content:      str   # default system prompt
    created_at:   str
    modified_at:  str


class AgentRepository(BaseRepository):
    """Pure CRUD repository for the `skill_agents` table."""

    async def upsert(
        self,
        skill_id:     str,
        name:         str,
        display_name: Optional[str],
        content:      str,
    ) -> Agent:
        """
        Insert an agent or update its content if one with the same skill+name exists.

        Sets created_at on first insert; updates display_name, content,
        and modified_at on conflict. Returns the current agent row.
        """
        now = self._now()
        row = await self._fetchone(
            "INSERT INTO skill_agents"
            "  (skill_id, name, display_name, content, created_at, modified_at)"
            " VALUES (%s, %s, %s, %s, %s, %s)"
            " ON CONFLICT (skill_id, name) DO UPDATE SET"
            "   display_name = EXCLUDED.display_name,"
            "   content      = EXCLUDED.content,"
            "   modified_at  = EXCLUDED.modified_at"
            " RETURNING id, skill_id, name, display_name, content, created_at, modified_at",
            (skill_id, name, display_name, content, now, now),
        )
        return self._row(row)

    async def get_by_id(self, agent_id: str) -> Optional[Agent]:
        """Return the agent with the given UUID, or None."""
        row = await self._fetchone(
            "SELECT id, skill_id, name, display_name, content, created_at, modified_at"
            " FROM skill_agents WHERE id = %s",
            (agent_id,),
        )
        return self._row(row) if row else None

    async def get_by_name(self, skill_id: str, name: str) -> Optional[Agent]:
        """Return the agent with the given skill UUID and agent name, or None."""
        row = await self._fetchone(
            "SELECT id, skill_id, name, display_name, content, created_at, modified_at"
            " FROM skill_agents WHERE skill_id = %s AND name = %s",
            (skill_id, name),
        )
        return self._row(row) if row else None

    async def list_for_skill(self, skill_id: str) -> list[Agent]:
        """Return all agents for a skill ordered by name."""
        rows = await self._fetchall(
            "SELECT id, skill_id, name, display_name, content, created_at, modified_at"
            " FROM skill_agents WHERE skill_id = %s ORDER BY name",
            (skill_id,),
        )
        return [self._row(r) for r in rows]

    @staticmethod
    def _row(row) -> Agent:
        """Map a raw DB row to an Agent dataclass."""
        return Agent(
            id=str(row[0]), skill_id=str(row[1]), name=row[2],
            display_name=row[3], content=row[4],
            created_at=str(row[5]), modified_at=str(row[6]),
        )
