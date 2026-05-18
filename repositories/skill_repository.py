from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from repositories.base import BaseRepository


@dataclass
class Skill:
    id:           str
    name:         str
    display_name: str
    description:  Optional[str]
    icon:         str
    version:      int
    created_at:   str
    modified_at:  str


class SkillRepository(BaseRepository):

    async def get_by_key(self, name: str) -> Optional[Skill]:
        row = await self._fetchone(
            "SELECT id, name, display_name, description, icon, version, created_at, modified_at"
            " FROM skills WHERE name = %s",
            (name,),
        )
        return self._row_to_skill(row) if row else None

    async def get_by_id(self, skill_id: str) -> Optional[Skill]:
        row = await self._fetchone(
            "SELECT id, name, display_name, description, icon, version, created_at, modified_at"
            " FROM skills WHERE id = %s",
            (skill_id,),
        )
        return self._row_to_skill(row) if row else None

    async def list_all(self) -> list[Skill]:
        rows = await self._fetchall(
            "SELECT id, name, display_name, description, icon, version, created_at, modified_at"
            " FROM skills ORDER BY name"
        )
        return [self._row_to_skill(r) for r in rows]

    async def upsert(
        self,
        name:         str,
        display_name: str,
        description:  str,
        icon:         str,
        version:      int,
    ) -> Skill:
        now = datetime.now(timezone.utc).isoformat()
        await self._exec(
            "INSERT INTO skills (name, display_name, description, icon, version, created_at)"
            " VALUES (%s, %s, %s, %s, %s, %s)"
            " ON CONFLICT (name) DO UPDATE SET"
            "   display_name = EXCLUDED.display_name,"
            "   description  = EXCLUDED.description,"
            "   icon         = EXCLUDED.icon,"
            "   version      = EXCLUDED.version",
            (name, display_name, description, icon, version, now),
        )
        return await self.get_by_key(name)

    @staticmethod
    def _row_to_skill(row) -> Skill:
        return Skill(
            id=str(row[0]), name=row[1], display_name=row[2],
            description=row[3], icon=row[4], version=row[5],
            created_at=str(row[6]), modified_at=str(row[7]),
        )
