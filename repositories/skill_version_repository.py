from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from repositories.base import BaseRepository


@dataclass
class SkillVersion:
    id:             str
    skill_id:       str
    version_number: int
    published_by:   str
    published_at:   str
    notes:          Optional[str]
    agents:         list[SkillVersionAgent]


@dataclass
class SkillVersionAgent:
    id:               str
    skill_version_id: str
    agent_key:        str
    content:          str
    provider:         Optional[str]
    model:            Optional[str]


@dataclass
class SkillDraft:
    id:                  str
    skill_id:            str
    user_id:             str
    based_on_version_id: Optional[str]
    created_at:          str
    updated_at:          str
    agents:              list[SkillDraftAgent]


@dataclass
class SkillDraftAgent:
    id:             str
    skill_draft_id: str
    agent_key:      str
    content:        str
    provider:       Optional[str]
    model:          Optional[str]
    updated_at:     str


class SkillVersionRepository(BaseRepository):

    # ── Versions ──────────────────────────────────────────────────────────────

    async def list_versions(self, skill_id: str) -> list[SkillVersion]:
        rows = await self._fetchall(
            "SELECT id, skill_id, version_number, published_by, published_at, notes"
            " FROM skill_versions WHERE skill_id = %s ORDER BY version_number DESC",
            (skill_id,),
        )
        versions = []
        for row in rows:
            agents = await self._get_version_agents(str(row[0]))
            versions.append(self._row_to_version(row, agents))
        return versions

    async def get_version(self, skill_id: str, version_number: int) -> Optional[SkillVersion]:
        row = await self._fetchone(
            "SELECT id, skill_id, version_number, published_by, published_at, notes"
            " FROM skill_versions WHERE skill_id = %s AND version_number = %s",
            (skill_id, version_number),
        )
        if not row:
            return None
        agents = await self._get_version_agents(str(row[0]))
        return self._row_to_version(row, agents)

    async def get_latest_version(self, skill_id: str) -> Optional[SkillVersion]:
        row = await self._fetchone(
            "SELECT id, skill_id, version_number, published_by, published_at, notes"
            " FROM skill_versions WHERE skill_id = %s ORDER BY version_number DESC LIMIT 1",
            (skill_id,),
        )
        if not row:
            return None
        agents = await self._get_version_agents(str(row[0]))
        return self._row_to_version(row, agents)

    async def _get_version_agents(self, skill_version_id: str) -> list[SkillVersionAgent]:
        rows = await self._fetchall(
            "SELECT id, skill_version_id, agent_key, content, provider, model"
            " FROM skill_version_agents WHERE skill_version_id = %s ORDER BY agent_key",
            (skill_version_id,),
        )
        return [self._row_to_version_agent(r) for r in rows]

    async def publish(
        self,
        skill_id:   str,
        user_id:    str,
        agents:     list[dict],
        notes:      Optional[str] = None,
    ) -> SkillVersion:
        next_version = await self._next_version_number(skill_id)

        version_row = await self._fetchone(
            "INSERT INTO skill_versions (skill_id, version_number, published_by, notes)"
            " VALUES (%s, %s, %s, %s)"
            " RETURNING id, skill_id, version_number, published_by, published_at, notes",
            (skill_id, next_version, user_id, notes),
        )
        version_id = str(version_row[0])

        for agent in agents:
            await self._exec(
                "INSERT INTO skill_version_agents"
                " (skill_version_id, agent_key, content, provider, model)"
                " VALUES (%s, %s, %s, %s, %s)",
                (version_id, agent["agent_key"], agent["content"],
                 agent.get("provider"), agent.get("model")),
            )

        version_agents = await self._get_version_agents(version_id)
        return self._row_to_version(version_row, version_agents)

    async def _next_version_number(self, skill_id: str) -> int:
        row = await self._fetchone(
            "SELECT COALESCE(MAX(version_number), 0) + 1 FROM skill_versions WHERE skill_id = %s",
            (skill_id,),
        )
        return int(row[0])

    # ── Drafts ────────────────────────────────────────────────────────────────

    async def get_draft(self, skill_id: str, user_id: str) -> Optional[SkillDraft]:
        row = await self._fetchone(
            "SELECT id, skill_id, user_id, based_on_version_id, created_at, updated_at"
            " FROM skill_drafts WHERE skill_id = %s AND user_id = %s",
            (skill_id, user_id),
        )
        if not row:
            return None
        agents = await self._get_draft_agents(str(row[0]))
        return self._row_to_draft(row, agents)

    async def upsert_draft_agent(
        self,
        skill_id:  str,
        user_id:   str,
        agent_key: str,
        content:   str,
        provider:  Optional[str],
        model:     Optional[str],
    ) -> SkillDraft:
        now = datetime.now(timezone.utc)

        # Get or create the draft
        draft_row = await self._fetchone(
            "SELECT id FROM skill_drafts WHERE skill_id = %s AND user_id = %s",
            (skill_id, user_id),
        )
        if draft_row:
            draft_id = str(draft_row[0])
            await self._exec(
                "UPDATE skill_drafts SET updated_at = %s WHERE id = %s",
                (now, draft_id),
            )
        else:
            latest = await self.get_latest_version(skill_id)
            draft_row = await self._fetchone(
                "INSERT INTO skill_drafts (skill_id, user_id, based_on_version_id)"
                " VALUES (%s, %s, %s) RETURNING id",
                (skill_id, user_id, latest.id if latest else None),
            )
            draft_id = str(draft_row[0])

        # Upsert the agent in the draft
        await self._exec(
            "INSERT INTO skill_draft_agents (skill_draft_id, agent_key, content, provider, model)"
            " VALUES (%s, %s, %s, %s, %s)"
            " ON CONFLICT (skill_draft_id, agent_key) DO UPDATE SET"
            "   content = EXCLUDED.content,"
            "   provider = EXCLUDED.provider,"
            "   model = EXCLUDED.model,"
            "   updated_at = now()",
            (draft_id, agent_key, content, provider, model),
        )

        return await self.get_draft(skill_id, user_id)

    async def discard_draft(self, skill_id: str, user_id: str) -> None:
        await self._exec(
            "DELETE FROM skill_drafts WHERE skill_id = %s AND user_id = %s",
            (skill_id, user_id),
        )

    async def _get_draft_agents(self, skill_draft_id: str) -> list[SkillDraftAgent]:
        rows = await self._fetchall(
            "SELECT id, skill_draft_id, agent_key, content, provider, model, updated_at"
            " FROM skill_draft_agents WHERE skill_draft_id = %s ORDER BY agent_key",
            (skill_draft_id,),
        )
        return [self._row_to_draft_agent(r) for r in rows]

    # ── Mappers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _row_to_version(row, agents: list[SkillVersionAgent]) -> SkillVersion:
        return SkillVersion(
            id=str(row[0]), skill_id=str(row[1]), version_number=int(row[2]),
            published_by=row[3], published_at=str(row[4]),
            notes=row[5], agents=agents,
        )

    @staticmethod
    def _row_to_version_agent(row) -> SkillVersionAgent:
        return SkillVersionAgent(
            id=str(row[0]), skill_version_id=str(row[1]), agent_key=row[2],
            content=row[3], provider=row[4], model=row[5],
        )

    @staticmethod
    def _row_to_draft(row, agents: list[SkillDraftAgent]) -> SkillDraft:
        return SkillDraft(
            id=str(row[0]), skill_id=str(row[1]), user_id=row[2],
            based_on_version_id=str(row[3]) if row[3] else None,
            created_at=str(row[4]), updated_at=str(row[5]),
            agents=agents,
        )

    @staticmethod
    def _row_to_draft_agent(row) -> SkillDraftAgent:
        return SkillDraftAgent(
            id=str(row[0]), skill_draft_id=str(row[1]), agent_key=row[2],
            content=row[3], provider=row[4], model=row[5], updated_at=str(row[6]),
        )
