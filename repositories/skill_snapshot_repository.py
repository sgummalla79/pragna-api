from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from repositories.base import BaseRepository


@dataclass
class SkillSnapshot:
    id:              str
    user_id:         str
    skill_id:        str
    version_number:  int
    type:            str   # 'draft' | 'published' | 'execution'
    conversation_id: Optional[str]
    created_at:      str
    modified_at:     str
    agents:          list[SkillSnapshotAgent]


@dataclass
class SkillSnapshotAgent:
    id:             str
    snapshot_id:    str
    skill_agent_id: str
    content:        str
    model_id:       Optional[str]
    created_at:     str
    modified_at:    str


class SkillSnapshotRepository(BaseRepository):

    # ── Queries ───────────────────────────────────────────────────────────────

    async def is_installed(self, user_id: str, skill_id: str) -> bool:
        row = await self._fetchone(
            "SELECT 1 FROM skill_snapshots WHERE user_id=%s AND skill_id=%s LIMIT 1",
            (user_id, skill_id),
        )
        return row is not None

    async def get_draft(self, user_id: str, skill_id: str) -> Optional[SkillSnapshot]:
        row = await self._fetchone(
            "SELECT id, user_id, skill_id, version_number, type, conversation_id, created_at, modified_at"
            " FROM skill_snapshots WHERE user_id=%s AND skill_id=%s AND type='draft' LIMIT 1",
            (user_id, skill_id),
        )
        if not row:
            return None
        return await self._with_agents(row)

    async def get_current_published(self, user_id: str, skill_id: str) -> Optional[SkillSnapshot]:
        row = await self._fetchone(
            "SELECT id, user_id, skill_id, version_number, type, conversation_id, created_at, modified_at"
            " FROM skill_snapshots"
            " WHERE user_id=%s AND skill_id=%s AND type='published'"
            " ORDER BY version_number DESC LIMIT 1",
            (user_id, skill_id),
        )
        if not row:
            return None
        return await self._with_agents(row)

    async def list_published(self, user_id: str, skill_id: str) -> list[SkillSnapshot]:
        rows = await self._fetchall(
            "SELECT id, user_id, skill_id, version_number, type, conversation_id, created_at, modified_at"
            " FROM skill_snapshots"
            " WHERE user_id=%s AND skill_id=%s AND type='published'"
            " ORDER BY version_number DESC",
            (user_id, skill_id),
        )
        result = []
        for row in rows:
            result.append(await self._with_agents(row))
        return result

    async def get_by_id(self, snapshot_id: str) -> Optional[SkillSnapshot]:
        row = await self._fetchone(
            "SELECT id, user_id, skill_id, version_number, type, conversation_id, created_at, modified_at"
            " FROM skill_snapshots WHERE id=%s",
            (snapshot_id,),
        )
        if not row:
            return None
        return await self._with_agents(row)

    async def get_execution_snapshot(self, conversation_id: str, skill_id: str) -> Optional[SkillSnapshot]:
        row = await self._fetchone(
            "SELECT id, user_id, skill_id, version_number, type, conversation_id, created_at, modified_at"
            " FROM skill_snapshots"
            " WHERE conversation_id=%s AND skill_id=%s AND type='execution' LIMIT 1",
            (conversation_id, skill_id),
        )
        if not row:
            return None
        return await self._with_agents(row)

    async def list_for_conversation(self, conversation_id: str) -> list[SkillSnapshot]:
        """Return all execution snapshots for a conversation (one per skill)."""
        rows = await self._fetchall(
            "SELECT id, user_id, skill_id, version_number, type, conversation_id, created_at, modified_at"
            " FROM skill_snapshots WHERE conversation_id=%s AND type='execution'"
            " ORDER BY created_at",
            (conversation_id,),
        )
        result = []
        for row in rows:
            result.append(await self._with_agents(row))
        return result

    async def get_published_version(
        self, user_id: str, skill_id: str, version_number: int
    ) -> Optional[SkillSnapshot]:
        row = await self._fetchone(
            "SELECT id, user_id, skill_id, version_number, type, conversation_id, created_at, modified_at"
            " FROM skill_snapshots"
            " WHERE user_id=%s AND skill_id=%s AND type='published' AND version_number=%s",
            (user_id, skill_id, version_number),
        )
        if not row:
            return None
        return await self._with_agents(row)

    async def get_execution_agents(self, conversation_id: str, skill_id: str) -> list[SkillSnapshotAgent]:
        row = await self._fetchone(
            "SELECT id FROM skill_snapshots"
            " WHERE conversation_id=%s AND skill_id=%s AND type='execution' LIMIT 1",
            (conversation_id, skill_id),
        )
        if not row:
            return []
        return await self._get_agents(str(row[0]))

    # ── Mutations ─────────────────────────────────────────────────────────────

    async def create_draft(
        self,
        user_id:     str,
        skill_id:    str,
        base_agents: list[SkillSnapshotAgent],
    ) -> SkillSnapshot:
        next_version = await self._next_version_number(user_id, skill_id)
        row = await self._fetchone(
            "INSERT INTO skill_snapshots (user_id, skill_id, version_number, type)"
            " VALUES (%s, %s, %s, 'draft')"
            " RETURNING id, user_id, skill_id, version_number, type, conversation_id, created_at, modified_at",
            (user_id, skill_id, next_version),
        )
        snapshot_id = str(row[0])
        for agent in base_agents:
            await self._exec(
                "INSERT INTO skill_snapshot_agents (snapshot_id, skill_agent_id, content, model_id)"
                " VALUES (%s, %s, %s, %s)",
                (snapshot_id, agent.skill_agent_id, agent.content, agent.model_id),
            )
        return await self._with_agents(row)

    async def upsert_draft_agent(
        self,
        snapshot_id:    str,
        skill_agent_id: str,
        content:        str,
        model_id:       Optional[str],
    ) -> None:
        await self._exec(
            "UPDATE skill_snapshot_agents SET content=%s, model_id=%s"
            " WHERE snapshot_id=%s AND skill_agent_id=%s",
            (content, model_id, snapshot_id, skill_agent_id),
        )

    async def publish_draft(self, snapshot_id: str) -> SkillSnapshot:
        row = await self._fetchone(
            "UPDATE skill_snapshots SET type='published' WHERE id=%s"
            " RETURNING id, user_id, skill_id, version_number, type, conversation_id, created_at, modified_at",
            (snapshot_id,),
        )
        return await self._with_agents(row)

    async def discard_draft(self, user_id: str, skill_id: str) -> None:
        await self._exec(
            "DELETE FROM skill_snapshots WHERE user_id=%s AND skill_id=%s AND type='draft'",
            (user_id, skill_id),
        )

    async def create_execution_snapshot(
        self,
        user_id:         str,
        skill_id:        str,
        conversation_id: str,
        base_agents:     list[SkillSnapshotAgent],
    ) -> SkillSnapshot:
        next_version = await self._next_version_number(user_id, skill_id)
        row = await self._fetchone(
            "INSERT INTO skill_snapshots (user_id, skill_id, version_number, type, conversation_id)"
            " VALUES (%s, %s, %s, 'execution', %s)"
            " RETURNING id, user_id, skill_id, version_number, type, conversation_id, created_at, modified_at",
            (user_id, skill_id, next_version, conversation_id),
        )
        snapshot_id = str(row[0])
        for agent in base_agents:
            await self._exec(
                "INSERT INTO skill_snapshot_agents (snapshot_id, skill_agent_id, content, model_id)"
                " VALUES (%s, %s, %s, %s)",
                (snapshot_id, agent.skill_agent_id, agent.content, agent.model_id),
            )
        return await self._with_agents(row)

    async def update_agent_model(
        self,
        snapshot_id:    str,
        skill_agent_id: str,
        model_id:       Optional[str],
    ) -> None:
        await self._exec(
            "UPDATE skill_snapshot_agents SET model_id=%s"
            " WHERE snapshot_id=%s AND skill_agent_id=%s",
            (model_id, snapshot_id, skill_agent_id),
        )

    async def uninstall(self, user_id: str, skill_id: str) -> None:
        """Delete draft + published snapshots. Execution snapshots are preserved."""
        await self._exec(
            "DELETE FROM skill_snapshots"
            " WHERE user_id=%s AND skill_id=%s AND type IN ('draft','published')",
            (user_id, skill_id),
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _next_version_number(self, user_id: str, skill_id: str) -> int:
        row = await self._fetchone(
            "SELECT COALESCE(MAX(version_number), 0) + 1"
            " FROM skill_snapshots WHERE user_id=%s AND skill_id=%s",
            (user_id, skill_id),
        )
        return int(row[0])

    async def _get_agents(self, snapshot_id: str) -> list[SkillSnapshotAgent]:
        rows = await self._fetchall(
            "SELECT id, snapshot_id, skill_agent_id, content, model_id, created_at, modified_at"
            " FROM skill_snapshot_agents WHERE snapshot_id=%s ORDER BY skill_agent_id",
            (snapshot_id,),
        )
        return [self._row_to_agent(r) for r in rows]

    async def _with_agents(self, row) -> SkillSnapshot:
        agents = await self._get_agents(str(row[0]))
        return self._row_to_snapshot(row, agents)

    @staticmethod
    def _row_to_snapshot(row, agents: list[SkillSnapshotAgent]) -> SkillSnapshot:
        return SkillSnapshot(
            id=str(row[0]), user_id=row[1], skill_id=str(row[2]),
            version_number=int(row[3]), type=row[4],
            conversation_id=str(row[5]) if row[5] else None,
            created_at=str(row[6]), modified_at=str(row[7]),
            agents=agents,
        )

    @staticmethod
    def _row_to_agent(row) -> SkillSnapshotAgent:
        return SkillSnapshotAgent(
            id=str(row[0]), snapshot_id=str(row[1]), skill_agent_id=str(row[2]),
            content=row[3], model_id=str(row[4]) if row[4] else None,
            created_at=str(row[5]), modified_at=str(row[6]),
        )
