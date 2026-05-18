from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from repositories.base import BaseRepository


@dataclass
class Skill:
    id:          str
    skill_key:   str
    name:        str
    description: Optional[str]
    icon:        str
    version:     int
    created_at:  str


class SkillRepository(BaseRepository):

    async def get_by_key(self, skill_key: str) -> Optional[Skill]:
        row = await self._fetchone(
            "SELECT id, skill_key, name, description, icon, version, created_at"
            " FROM skills WHERE skill_key = %s",
            (skill_key,),
        )
        return self._row_to_skill(row) if row else None

    async def get_by_id(self, skill_id: str) -> Optional[Skill]:
        row = await self._fetchone(
            "SELECT id, skill_key, name, description, icon, version, created_at"
            " FROM skills WHERE id = %s",
            (skill_id,),
        )
        return self._row_to_skill(row) if row else None

    async def list_all(self) -> list[Skill]:
        rows = await self._fetchall(
            "SELECT id, skill_key, name, description, icon, version, created_at"
            " FROM skills ORDER BY skill_key"
        )
        return [self._row_to_skill(r) for r in rows]

    async def upsert(
        self,
        skill_key:   str,
        name:        str,
        description: str,
        icon:        str,
        version:     int,
    ) -> Skill:
        now = datetime.now(timezone.utc).isoformat()
        await self._exec(
            "INSERT INTO skills (skill_key, name, description, icon, version, created_at)"
            " VALUES (%s, %s, %s, %s, %s, %s)"
            " ON CONFLICT (skill_key) DO UPDATE SET"
            "   name = EXCLUDED.name,"
            "   description = EXCLUDED.description,"
            "   icon = EXCLUDED.icon,"
            "   version = EXCLUDED.version",
            (skill_key, name, description, icon, version, now),
        )
        return await self.get_by_key(skill_key)

    @staticmethod
    def _row_to_skill(row) -> Skill:
        return Skill(
            id=str(row[0]), skill_key=row[1], name=row[2],
            description=row[3], icon=row[4], version=row[5],
            created_at=str(row[6]),
        )
