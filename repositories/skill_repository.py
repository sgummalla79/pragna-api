"""
SkillRepository — CRUD for the `skills` table.

Stores the global catalog of out-of-the-box skill definitions (e.g. 'architect').
Seeded at application startup from disk; not user-specific.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from repositories.base import BaseRepository


@dataclass
class Skill:
    """Represents one row in the `skills` table."""
    id:           str
    name:         str          # machine identifier, e.g. "architect"
    display_name: str
    description:  Optional[str]
    created_at:   str
    modified_at:  str


class SkillRepository(BaseRepository):
    """Pure CRUD repository for the `skills` table."""

    async def upsert(
        self,
        name:         str,
        display_name: str,
        description:  Optional[str] = None,
    ) -> Skill:
        """
        Insert a skill by name or update its display fields if it already exists.

        Sets created_at on first insert; updates display_name, description,
        and modified_at on conflict. Returns the current skill row.
        """
        now = self._now()
        row = await self._fetchone(
            "INSERT INTO skills (name, display_name, description, created_at, modified_at)"
            " VALUES (%s, %s, %s, %s, %s)"
            " ON CONFLICT (name) DO UPDATE SET"
            "   display_name = EXCLUDED.display_name,"
            "   description  = EXCLUDED.description,"
            "   modified_at  = EXCLUDED.modified_at"
            " RETURNING id, name, display_name, description, created_at, modified_at",
            (name, display_name, description, now, now),
        )
        return self._row(row)

    async def get_by_id(self, skill_id: str) -> Optional[Skill]:
        """Return the skill with the given UUID, or None."""
        row = await self._fetchone(
            "SELECT id, name, display_name, description, created_at, modified_at"
            " FROM skills WHERE id = %s",
            (skill_id,),
        )
        return self._row(row) if row else None

    async def get_by_name(self, name: str) -> Optional[Skill]:
        """Return the skill with the given machine name (e.g. 'architect'), or None."""
        row = await self._fetchone(
            "SELECT id, name, display_name, description, created_at, modified_at"
            " FROM skills WHERE name = %s",
            (name,),
        )
        return self._row(row) if row else None

    async def list_all(self) -> list[Skill]:
        """Return all skills ordered by name."""
        rows = await self._fetchall(
            "SELECT id, name, display_name, description, created_at, modified_at"
            " FROM skills ORDER BY name"
        )
        return [self._row(r) for r in rows]

    @staticmethod
    def _row(row) -> Skill:
        """Map a raw DB row to a Skill dataclass."""
        return Skill(
            id=str(row[0]), name=row[1], display_name=row[2],
            description=row[3], created_at=str(row[4]), modified_at=str(row[5]),
        )
