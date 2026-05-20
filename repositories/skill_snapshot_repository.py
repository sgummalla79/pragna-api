"""
SkillSnapshotRepository — CRUD for `skill_snapshots` and `skill_snapshot_agents`.

A snapshot is a point-in-time copy of a skill's agent prompts. Three types exist:
  - draft:     work in progress (at most one per user+skill)
  - published: a saved version (accumulates; current = MAX version_number)
  - execution: frozen copy locked to a conversation (never deleted)

See docs/SKILL_SNAPSHOT_DESIGN.md for full lifecycle documentation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from repositories.base import BaseRepository
from repositories.constants import SnapshotType


@dataclass
class SkillSnapshotAgent:
    """Represents one row in the `skill_snapshot_agents` table."""
    id:             str
    snapshot_id:    str   # UUID FK → skill_snapshots(id)
    skill_agent_id: str   # UUID FK → skill_agents(id)
    content:        str   # frozen system prompt
    model_id:       Optional[str]  # UUID FK → user_llm_models(id), nullable
    created_at:     str
    modified_at:    str


@dataclass
class SkillSnapshot:
    """Represents one row in the `skill_snapshots` table, with its agents loaded."""
    id:              str
    user_id:         str
    skill_id:        str
    version_number:  int
    type:            str   # SnapshotType constant
    conversation_id: Optional[str]
    created_at:      str
    modified_at:     str
    agents:          list[SkillSnapshotAgent]


class SkillSnapshotRepository(BaseRepository):
    """Pure CRUD repository for skill_snapshots and skill_snapshot_agents."""

    # ── Queries ───────────────────────────────────────────────────────────────

    async def is_installed(self, user_id: str, skill_id: str) -> bool:
        """
        Return True if the user has any snapshot for this skill.

        A user 'has' a skill the moment any snapshot (draft, published, or
        execution) exists — no explicit install record is needed.
        """
        row = await self._fetchone(
            "SELECT 1 FROM skill_snapshots WHERE user_id = %s AND skill_id = %s LIMIT 1",
            (user_id, skill_id),
        )
        return row is not None

    async def get_draft(self, user_id: str, skill_id: str) -> Optional[SkillSnapshot]:
        """Return the current draft snapshot for a user+skill, or None."""
        row = await self._fetchone(
            "SELECT id, user_id, skill_id, version_number, type, conversation_id,"
            "       created_at, modified_at"
            " FROM skill_snapshots"
            " WHERE user_id = %s AND skill_id = %s AND type = %s LIMIT 1",
            (user_id, skill_id, SnapshotType.DRAFT),
        )
        return await self._with_agents(row) if row else None

    async def get_current_published(
        self, user_id: str, skill_id: str
    ) -> Optional[SkillSnapshot]:
        """
        Return the most recently published snapshot for a user+skill, or None.

        'Current' is defined as the highest version_number among published rows.
        """
        row = await self._fetchone(
            "SELECT id, user_id, skill_id, version_number, type, conversation_id,"
            "       created_at, modified_at"
            " FROM skill_snapshots"
            " WHERE user_id = %s AND skill_id = %s AND type = %s"
            " ORDER BY version_number DESC LIMIT 1",
            (user_id, skill_id, SnapshotType.PUBLISHED),
        )
        return await self._with_agents(row) if row else None

    async def get_published_version(
        self, user_id: str, skill_id: str, version_number: int
    ) -> Optional[SkillSnapshot]:
        """Return a specific published version by number, or None."""
        row = await self._fetchone(
            "SELECT id, user_id, skill_id, version_number, type, conversation_id,"
            "       created_at, modified_at"
            " FROM skill_snapshots"
            " WHERE user_id = %s AND skill_id = %s AND type = %s AND version_number = %s",
            (user_id, skill_id, SnapshotType.PUBLISHED, version_number),
        )
        return await self._with_agents(row) if row else None

    async def list_published(
        self, user_id: str, skill_id: str
    ) -> list[SkillSnapshot]:
        """Return all published snapshots for a user+skill, newest first."""
        rows = await self._fetchall(
            "SELECT id, user_id, skill_id, version_number, type, conversation_id,"
            "       created_at, modified_at"
            " FROM skill_snapshots"
            " WHERE user_id = %s AND skill_id = %s AND type = %s"
            " ORDER BY version_number DESC",
            (user_id, skill_id, SnapshotType.PUBLISHED),
        )
        result = []
        for row in rows:
            result.append(await self._with_agents(row))
        return result

    async def get_by_id(self, snapshot_id: str) -> Optional[SkillSnapshot]:
        """Return any snapshot by UUID, with its agents loaded, or None."""
        row = await self._fetchone(
            "SELECT id, user_id, skill_id, version_number, type, conversation_id,"
            "       created_at, modified_at"
            " FROM skill_snapshots WHERE id = %s",
            (snapshot_id,),
        )
        return await self._with_agents(row) if row else None

    async def get_execution_snapshot(
        self, conversation_id: str, skill_id: str
    ) -> Optional[SkillSnapshot]:
        """
        Return the execution snapshot for a specific conversation+skill pair, or None.

        There is at most one execution snapshot per (conversation_id, skill_id).
        """
        row = await self._fetchone(
            "SELECT id, user_id, skill_id, version_number, type, conversation_id,"
            "       created_at, modified_at"
            " FROM skill_snapshots"
            " WHERE conversation_id = %s AND skill_id = %s AND type = %s LIMIT 1",
            (conversation_id, skill_id, SnapshotType.EXECUTION),
        )
        return await self._with_agents(row) if row else None

    async def list_for_conversation(
        self, conversation_id: str
    ) -> list[SkillSnapshot]:
        """Return all execution snapshots for a conversation, ordered by creation time."""
        rows = await self._fetchall(
            "SELECT id, user_id, skill_id, version_number, type, conversation_id,"
            "       created_at, modified_at"
            " FROM skill_snapshots"
            " WHERE conversation_id = %s AND type = %s ORDER BY created_at",
            (conversation_id, SnapshotType.EXECUTION),
        )
        result = []
        for row in rows:
            result.append(await self._with_agents(row))
        return result

    # ── Mutations ─────────────────────────────────────────────────────────────

    async def create_draft(
        self,
        user_id:     str,
        skill_id:    str,
        base_agents: list[SkillSnapshotAgent],
    ) -> SkillSnapshot:
        """
        Create a new draft snapshot, copying agent content from base_agents.

        Assigns the next version_number (MAX + 1 across all types for this user+skill).
        Returns the created snapshot with agents loaded.
        """
        now            = self._now()
        next_version   = await self._next_version_number(user_id, skill_id)
        row = await self._fetchone(
            "INSERT INTO skill_snapshots"
            "  (user_id, skill_id, version_number, type, created_at, modified_at)"
            " VALUES (%s, %s, %s, %s, %s, %s)"
            " RETURNING id, user_id, skill_id, version_number, type, conversation_id,"
            "           created_at, modified_at",
            (user_id, skill_id, next_version, SnapshotType.DRAFT, now, now),
        )
        snapshot_id = str(row[0])
        for agent in base_agents:
            await self._insert_agent(snapshot_id, agent.skill_agent_id, agent.content, agent.model_id)
        return await self._with_agents(row)

    async def upsert_draft_agent(
        self,
        snapshot_id:    str,
        skill_agent_id: str,
        content:        str,
        model_id:       Optional[str],
    ) -> None:
        """
        Update the content and model_id for a single agent within a draft snapshot.

        Also updates modified_at on the agent row. The snapshot's own modified_at
        is updated separately via touch_snapshot.
        """
        now = self._now()
        await self._exec(
            "UPDATE skill_snapshot_agents"
            " SET content = %s, model_id = %s, modified_at = %s"
            " WHERE snapshot_id = %s AND skill_agent_id = %s",
            (content, model_id, now, snapshot_id, skill_agent_id),
        )
        # Keep the parent snapshot's modified_at in sync
        await self._exec(
            "UPDATE skill_snapshots SET modified_at = %s WHERE id = %s",
            (now, snapshot_id),
        )

    async def publish_draft(self, snapshot_id: str) -> SkillSnapshot:
        """
        Promote a draft snapshot to published by changing its type in place.

        Publishing is one-way — a published snapshot cannot be reverted to draft.
        Returns the updated snapshot.
        """
        now = self._now()
        row = await self._fetchone(
            "UPDATE skill_snapshots SET type = %s, modified_at = %s WHERE id = %s"
            " RETURNING id, user_id, skill_id, version_number, type, conversation_id,"
            "           created_at, modified_at",
            (SnapshotType.PUBLISHED, now, snapshot_id),
        )
        return await self._with_agents(row)

    async def discard_draft(self, user_id: str, skill_id: str) -> None:
        """
        Delete the draft snapshot for a user+skill.

        Cascades automatically to skill_snapshot_agents via FK ON DELETE CASCADE.
        """
        await self._exec(
            "DELETE FROM skill_snapshots WHERE user_id = %s AND skill_id = %s AND type = %s",
            (user_id, skill_id, SnapshotType.DRAFT),
        )

    async def create_execution_snapshot(
        self,
        user_id:         str,
        skill_id:        str,
        conversation_id: str,
        base_agents:     list[SkillSnapshotAgent],
    ) -> SkillSnapshot:
        """
        Create a frozen execution snapshot linked to a conversation.

        Content is copied from base_agents and must not change after creation.
        Only model_id can be updated mid-execution for provider fallback.
        Returns the created snapshot with agents loaded.
        """
        now          = self._now()
        next_version = await self._next_version_number(user_id, skill_id)
        row = await self._fetchone(
            "INSERT INTO skill_snapshots"
            "  (user_id, skill_id, version_number, type, conversation_id, created_at, modified_at)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s)"
            " RETURNING id, user_id, skill_id, version_number, type, conversation_id,"
            "           created_at, modified_at",
            (user_id, skill_id, next_version, SnapshotType.EXECUTION, conversation_id, now, now),
        )
        snapshot_id = str(row[0])
        for agent in base_agents:
            await self._insert_agent(snapshot_id, agent.skill_agent_id, agent.content, agent.model_id)
        return await self._with_agents(row)

    async def update_agent_model(
        self,
        snapshot_id:    str,
        skill_agent_id: str,
        model_id:       Optional[str],
    ) -> None:
        """
        Update the model_id on a single agent row within any snapshot type.

        The only mutation allowed on execution snapshots — used for provider
        fallback when the originally configured model becomes unavailable.
        """
        await self._exec(
            "UPDATE skill_snapshot_agents SET model_id = %s, modified_at = %s"
            " WHERE snapshot_id = %s AND skill_agent_id = %s",
            (model_id, self._now(), snapshot_id, skill_agent_id),
        )

    async def uninstall(self, user_id: str, skill_id: str) -> None:
        """
        Delete all draft and published snapshots for a user+skill.

        Execution snapshots are deliberately preserved as the permanent audit record
        of what prompt content ran in each conversation.
        """
        await self._exec(
            "DELETE FROM skill_snapshots"
            " WHERE user_id = %s AND skill_id = %s AND type IN (%s, %s)",
            (user_id, skill_id, SnapshotType.DRAFT, SnapshotType.PUBLISHED),
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _next_version_number(self, user_id: str, skill_id: str) -> int:
        """
        Calculate the next sequential version number for a user+skill.

        Counts across all snapshot types so version numbers are globally unique
        per user+skill regardless of type.
        """
        row = await self._fetchone(
            "SELECT COALESCE(MAX(version_number), 0) + 1"
            " FROM skill_snapshots WHERE user_id = %s AND skill_id = %s",
            (user_id, skill_id),
        )
        return int(row[0])

    async def _insert_agent(
        self,
        snapshot_id:    str,
        skill_agent_id: str,
        content:        str,
        model_id:       Optional[str],
    ) -> None:
        """Insert one agent row into skill_snapshot_agents."""
        now = self._now()
        await self._exec(
            "INSERT INTO skill_snapshot_agents"
            "  (snapshot_id, skill_agent_id, content, model_id, created_at, modified_at)"
            " VALUES (%s, %s, %s, %s, %s, %s)",
            (snapshot_id, skill_agent_id, content, model_id, now, now),
        )

    async def _get_agents(self, snapshot_id: str) -> list[SkillSnapshotAgent]:
        """Return all agent rows for a snapshot, ordered by skill_agent_id."""
        rows = await self._fetchall(
            "SELECT id, snapshot_id, skill_agent_id, content, model_id, created_at, modified_at"
            " FROM skill_snapshot_agents WHERE snapshot_id = %s ORDER BY skill_agent_id",
            (snapshot_id,),
        )
        return [self._row_agent(r) for r in rows]

    async def _with_agents(self, row) -> SkillSnapshot:
        """Load agents for a snapshot row and return a fully populated SkillSnapshot."""
        agents = await self._get_agents(str(row[0]))
        return self._row_snapshot(row, agents)

    @staticmethod
    def _row_snapshot(row, agents: list[SkillSnapshotAgent]) -> SkillSnapshot:
        """Map a raw DB row and pre-loaded agents to a SkillSnapshot dataclass."""
        return SkillSnapshot(
            id=str(row[0]), user_id=row[1], skill_id=str(row[2]),
            version_number=int(row[3]), type=row[4],
            conversation_id=str(row[5]) if row[5] else None,
            created_at=str(row[6]), modified_at=str(row[7]),
            agents=agents,
        )

    @staticmethod
    def _row_agent(row) -> SkillSnapshotAgent:
        """Map a raw DB row to a SkillSnapshotAgent dataclass."""
        return SkillSnapshotAgent(
            id=str(row[0]), snapshot_id=str(row[1]), skill_agent_id=str(row[2]),
            content=row[3], model_id=str(row[4]) if row[4] else None,
            created_at=str(row[5]), modified_at=str(row[6]),
        )
