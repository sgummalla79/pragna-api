from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from repositories.base import BaseRepository


@dataclass
class UserSkillV2:
    id:              str
    user_id:         str
    skill_id:        str
    current_version: int
    created_at:      str


@dataclass
class UserSkillVersion:
    id:             str
    user_skill_id:  str
    version_number: int
    status:         str   # 'draft' | 'published'
    created_at:     str
    agents:         list[UserSkillAgent]


@dataclass
class UserSkillAgent:
    id:                    str
    user_id:               str
    user_skill_version_id: str
    skill_agent_id:        str
    content:               str
    model_id:              Optional[str]
    created_at:            str
    modified_at:           str


class UserSkillV2Repository(BaseRepository):

    # ── Install ───────────────────────────────────────────────────────────────

    async def install(self, user_id: str, skill_id: str) -> UserSkillV2:
        """Create a user_skills row if not already installed."""
        row = await self._fetchone(
            "INSERT INTO user_skills (user_id, skill_id)"
            " VALUES (%s, %s)"
            " ON CONFLICT (user_id, skill_id) DO UPDATE SET user_id = EXCLUDED.user_id"
            " RETURNING id, user_id, skill_id, current_version, created_at",
            (user_id, skill_id),
        )
        return self._row_to_skill(row)

    async def get(self, user_id: str, skill_id: str) -> Optional[UserSkillV2]:
        row = await self._fetchone(
            "SELECT id, user_id, skill_id, current_version, created_at"
            " FROM user_skills WHERE user_id = %s AND skill_id = %s",
            (user_id, skill_id),
        )
        return self._row_to_skill(row) if row else None

    # ── Versions ──────────────────────────────────────────────────────────────

    async def list_versions(self, user_skill_id: str) -> list[UserSkillVersion]:
        rows = await self._fetchall(
            "SELECT id, user_skill_id, version_number, status, created_at"
            " FROM user_skill_versions WHERE user_skill_id = %s"
            " ORDER BY version_number DESC",
            (user_skill_id,),
        )
        versions = []
        for row in rows:
            agents = await self._get_agents(str(row[0]))
            versions.append(self._row_to_version(row, agents))
        return versions

    async def get_version(self, user_skill_id: str, version_number: int) -> Optional[UserSkillVersion]:
        row = await self._fetchone(
            "SELECT id, user_skill_id, version_number, status, created_at"
            " FROM user_skill_versions"
            " WHERE user_skill_id = %s AND version_number = %s",
            (user_skill_id, version_number),
        )
        if not row:
            return None
        agents = await self._get_agents(str(row[0]))
        return self._row_to_version(row, agents)

    async def get_draft(self, user_skill_id: str) -> Optional[UserSkillVersion]:
        row = await self._fetchone(
            "SELECT id, user_skill_id, version_number, status, created_at"
            " FROM user_skill_versions"
            " WHERE user_skill_id = %s AND status = 'draft'"
            " LIMIT 1",
            (user_skill_id,),
        )
        if not row:
            return None
        agents = await self._get_agents(str(row[0]))
        return self._row_to_version(row, agents)

    async def create_draft(
        self,
        user_id:       str,
        user_skill_id: str,
        base_agents:   list[UserSkillAgent],
    ) -> UserSkillVersion:
        """Create a new draft version copying all agents from the latest published version."""
        next_version = await self._next_version_number(user_skill_id)

        version_row = await self._fetchone(
            "INSERT INTO user_skill_versions (user_skill_id, version_number, status)"
            " VALUES (%s, %s, 'draft')"
            " RETURNING id, user_skill_id, version_number, status, created_at",
            (user_skill_id, next_version),
        )
        version_id = str(version_row[0])

        for agent in base_agents:
            await self._exec(
                "INSERT INTO user_skill_agents"
                " (user_id, user_skill_version_id, skill_agent_id, content, model_id)"
                " VALUES (%s, %s, %s, %s, %s)",
                (user_id, version_id, agent.skill_agent_id, agent.content, agent.model_id),
            )

        agents = await self._get_agents(version_id)
        return self._row_to_version(version_row, agents)

    async def upsert_draft_agent(
        self,
        user_skill_version_id: str,
        skill_agent_id:        str,
        content:               str,
        model_id:              Optional[str],
    ) -> None:
        """Update a single agent's content within a draft version."""
        await self._exec(
            "UPDATE user_skill_agents SET content = %s, model_id = %s"
            " WHERE user_skill_version_id = %s AND skill_agent_id = %s",
            (content, model_id, user_skill_version_id, skill_agent_id),
        )

    async def publish_draft(self, user_skill_id: str, draft_version_id: str) -> UserSkillVersion:
        """Publish draft → set status=published, update user_skills.current_version."""
        version_row = await self._fetchone(
            "UPDATE user_skill_versions SET status = 'published'"
            " WHERE id = %s"
            " RETURNING id, user_skill_id, version_number, status, created_at",
            (draft_version_id,),
        )
        await self._exec(
            "UPDATE user_skills SET current_version = %s WHERE id = %s",
            (version_row[2], user_skill_id),
        )
        agents = await self._get_agents(str(version_row[0]))
        return self._row_to_version(version_row, agents)

    async def uninstall(self, user_id: str, skill_id: str) -> None:
        """Remove user_skills row — CASCADE deletes versions and agents."""
        await self._exec(
            "DELETE FROM user_skills WHERE user_id = %s AND skill_id = %s",
            (user_id, skill_id),
        )

    async def discard_draft(self, user_skill_id: str) -> None:
        """Delete the current draft version and its agents (cascade handles agents)."""
        await self._exec(
            "DELETE FROM user_skill_versions"
            " WHERE user_skill_id = %s AND status = 'draft'",
            (user_skill_id,),
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _get_agents(self, user_skill_version_id: str) -> list[UserSkillAgent]:
        rows = await self._fetchall(
            "SELECT id, user_id, user_skill_version_id, skill_agent_id,"
            "       content, model_id, created_at, modified_at"
            " FROM user_skill_agents WHERE user_skill_version_id = %s"
            " ORDER BY skill_agent_id",
            (user_skill_version_id,),
        )
        return [self._row_to_agent(r) for r in rows]

    async def _next_version_number(self, user_skill_id: str) -> int:
        row = await self._fetchone(
            "SELECT COALESCE(MAX(version_number), 0) + 1"
            " FROM user_skill_versions WHERE user_skill_id = %s",
            (user_skill_id,),
        )
        return int(row[0])

    async def get_latest_published_agents(self, user_skill_id: str) -> list[UserSkillAgent]:
        """Return agents from the latest published version (for copying into a new draft)."""
        row = await self._fetchone(
            "SELECT id FROM user_skill_versions"
            " WHERE user_skill_id = %s AND status = 'published'"
            " ORDER BY version_number DESC LIMIT 1",
            (user_skill_id,),
        )
        if not row:
            return []
        return await self._get_agents(str(row[0]))

    # ── Mappers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _row_to_skill(row) -> UserSkillV2:
        return UserSkillV2(
            id=str(row[0]), user_id=row[1], skill_id=str(row[2]),
            current_version=int(row[3]), created_at=str(row[4]),
        )

    @staticmethod
    def _row_to_version(row, agents: list[UserSkillAgent]) -> UserSkillVersion:
        return UserSkillVersion(
            id=str(row[0]), user_skill_id=str(row[1]),
            version_number=int(row[2]), status=row[3],
            created_at=str(row[4]), agents=agents,
        )

    @staticmethod
    def _row_to_agent(row) -> UserSkillAgent:
        return UserSkillAgent(
            id=str(row[0]), user_id=row[1], user_skill_version_id=str(row[2]),
            skill_agent_id=str(row[3]), content=row[4],
            model_id=str(row[5]) if row[5] else None,
            created_at=str(row[6]), modified_at=str(row[7]),
        )
