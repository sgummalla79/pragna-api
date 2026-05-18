from __future__ import annotations
from datetime import datetime, timezone

from repositories.base import BaseRepository


class UserSkillRepository(BaseRepository):

    async def install(self, user_id: str, skill_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await self._exec(
            "INSERT INTO user_skills (user_id, skill_id, installed_at)"
            " VALUES (%s, %s, %s)"
            " ON CONFLICT (user_id, skill_id) DO NOTHING",
            (user_id, skill_id, now),
        )

    async def uninstall(self, user_id: str, skill_id: str) -> None:
        await self._exec(
            "DELETE FROM user_skills WHERE user_id = %s AND skill_id = %s",
            (user_id, skill_id),
        )

    async def is_installed(self, user_id: str, skill_id: str) -> bool:
        row = await self._fetchone(
            "SELECT 1 FROM user_skills WHERE user_id = %s AND skill_id = %s",
            (user_id, skill_id),
        )
        return row is not None

    async def get_installed_skill_ids(self, user_id: str) -> set[str]:
        rows = await self._fetchall(
            "SELECT skill_id FROM user_skills WHERE user_id = %s",
            (user_id,),
        )
        return {str(r[0]) for r in rows}
