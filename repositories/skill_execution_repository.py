"""
SkillExecutionRepository — CRUD for the `skill_executions` table.

Tracks the lifecycle of a single pipeline run. The execution id doubles as the
LangGraph thread_id — it anchors all checkpoint state for that run.

See docs/SKILL_SNAPSHOT_DESIGN.md for the full execution lifecycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from repositories.base import BaseRepository
from repositories.constants import ExecutionStatus


@dataclass
class SkillExecution:
    """Represents one row in the `skill_executions` table."""
    id:           str   # = LangGraph thread_id
    snapshot_id:  str   # UUID FK → skill_snapshots(id) — always an execution snapshot
    status:       str   # ExecutionStatus constant
    started_at:   str
    completed_at: Optional[str]
    created_at:   str
    modified_at:  str


class SkillExecutionRepository(BaseRepository):
    """Pure CRUD repository for the `skill_executions` table."""

    async def create(self, execution_id: str, snapshot_id: str) -> SkillExecution:
        """
        Insert a new execution row with status 'running'.

        The execution_id is caller-supplied (a new UUID4) because it must also
        be used as the LangGraph thread_id before this method returns.
        Sets created_at, modified_at, and started_at to the current UTC time.
        """
        now = self._now()
        row = await self._fetchone(
            "INSERT INTO skill_executions"
            "  (id, snapshot_id, status, started_at, created_at, modified_at)"
            " VALUES (%s, %s, %s, %s, %s, %s)"
            " RETURNING id, snapshot_id, status, started_at, completed_at,"
            "           created_at, modified_at",
            (execution_id, snapshot_id, ExecutionStatus.RUNNING, now, now, now),
        )
        return self._row(row)

    async def get_by_id(self, execution_id: str) -> Optional[SkillExecution]:
        """Return the execution with the given UUID, or None."""
        row = await self._fetchone(
            "SELECT id, snapshot_id, status, started_at, completed_at,"
            "       created_at, modified_at"
            " FROM skill_executions WHERE id = %s",
            (execution_id,),
        )
        return self._row(row) if row else None

    async def get_running(self, conversation_id: str) -> Optional[SkillExecution]:
        """
        Return any currently running execution for a conversation, or None.

        Used as a concurrent-run guard before starting a new execution.
        Joins to skill_snapshots to filter by conversation_id.
        """
        row = await self._fetchone(
            "SELECT e.id, e.snapshot_id, e.status, e.started_at, e.completed_at,"
            "       e.created_at, e.modified_at"
            " FROM skill_executions e"
            " JOIN skill_snapshots s ON s.id = e.snapshot_id"
            " WHERE s.conversation_id = %s AND e.status = %s"
            " LIMIT 1",
            (conversation_id, ExecutionStatus.RUNNING),
        )
        return self._row(row) if row else None

    async def get_latest_for_conversation(
        self, conversation_id: str
    ) -> Optional[SkillExecution]:
        """
        Return the most recently started execution for any skill in a conversation, or None.

        Used to populate the execution status field in the conversation detail response.
        """
        row = await self._fetchone(
            "SELECT e.id, e.snapshot_id, e.status, e.started_at, e.completed_at,"
            "       e.created_at, e.modified_at"
            " FROM skill_executions e"
            " JOIN skill_snapshots s ON s.id = e.snapshot_id"
            " WHERE s.conversation_id = %s"
            " ORDER BY e.started_at DESC LIMIT 1",
            (conversation_id,),
        )
        return self._row(row) if row else None

    async def complete(self, execution_id: str, status: str) -> None:
        """
        Mark an execution as finished by setting its terminal status and completed_at.

        Also updates modified_at. Status must be one of the non-running
        ExecutionStatus constants (complete, halted, error, invalid_input).
        """
        now = self._now()
        await self._exec(
            "UPDATE skill_executions"
            " SET status = %s, completed_at = %s, modified_at = %s"
            " WHERE id = %s",
            (status, now, now, execution_id),
        )

    async def reset_running(self, execution_id: str) -> None:
        """
        Reset an execution to 'running' and clear completed_at.

        Called when retrying from the last LangGraph checkpoint.
        """
        await self._exec(
            "UPDATE skill_executions"
            " SET status = %s, completed_at = NULL, modified_at = %s"
            " WHERE id = %s",
            (ExecutionStatus.RUNNING, self._now(), execution_id),
        )

    async def list_for_snapshot(self, snapshot_id: str) -> list[SkillExecution]:
        """
        Return all executions for a snapshot in reverse chronological order.

        Useful for displaying the execution history of a skill within a conversation.
        """
        rows = await self._fetchall(
            "SELECT id, snapshot_id, status, started_at, completed_at,"
            "       created_at, modified_at"
            " FROM skill_executions WHERE snapshot_id = %s ORDER BY started_at DESC",
            (snapshot_id,),
        )
        return [self._row(r) for r in rows]

    @staticmethod
    def _row(row) -> SkillExecution:
        """Map a raw DB row to a SkillExecution dataclass."""
        return SkillExecution(
            id=str(row[0]), snapshot_id=str(row[1]), status=row[2],
            started_at=str(row[3]),
            completed_at=str(row[4]) if row[4] else None,
            created_at=str(row[5]),
            modified_at=str(row[6]),
        )
