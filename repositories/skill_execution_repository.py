from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from repositories.base import BaseRepository


@dataclass
class SkillExecution:
    id:           str
    snapshot_id:  str
    status:       str   # 'running' | 'complete' | 'halted' | 'error' | 'invalid_input'
    started_at:   str
    completed_at: Optional[str]


class SkillExecutionRepository(BaseRepository):

    async def create(self, execution_id: str, snapshot_id: str) -> SkillExecution:
        row = await self._fetchone(
            "INSERT INTO skill_executions (id, snapshot_id, status)"
            " VALUES (%s, %s, 'running')"
            " RETURNING id, snapshot_id, status, started_at, completed_at",
            (execution_id, snapshot_id),
        )
        return self._row(row)

    async def get_by_id(self, execution_id: str) -> Optional[SkillExecution]:
        row = await self._fetchone(
            "SELECT id, snapshot_id, status, started_at, completed_at"
            " FROM skill_executions WHERE id=%s",
            (execution_id,),
        )
        return self._row(row) if row else None

    async def get_running(self, conversation_id: str) -> Optional[SkillExecution]:
        """Return any running execution for any skill in this conversation."""
        row = await self._fetchone(
            "SELECT e.id, e.snapshot_id, e.status, e.started_at, e.completed_at"
            " FROM skill_executions e"
            " JOIN skill_snapshots s ON s.id = e.snapshot_id"
            " WHERE s.conversation_id=%s AND e.status='running'"
            " LIMIT 1",
            (conversation_id,),
        )
        return self._row(row) if row else None

    async def complete(self, execution_id: str, status: str) -> None:
        await self._exec(
            "UPDATE skill_executions SET status=%s, completed_at=now() WHERE id=%s",
            (status, execution_id),
        )

    async def reset_running(self, execution_id: str) -> None:
        """Reset to running for retry."""
        await self._exec(
            "UPDATE skill_executions SET status='running', completed_at=NULL WHERE id=%s",
            (execution_id,),
        )

    async def get_latest_for_conversation(self, conversation_id: str) -> Optional[SkillExecution]:
        """Return the most recent execution for any skill in this conversation."""
        row = await self._fetchone(
            "SELECT e.id, e.snapshot_id, e.status, e.started_at, e.completed_at"
            " FROM skill_executions e"
            " JOIN skill_snapshots s ON s.id = e.snapshot_id"
            " WHERE s.conversation_id=%s"
            " ORDER BY e.started_at DESC LIMIT 1",
            (conversation_id,),
        )
        return self._row(row) if row else None

    async def list_for_snapshot(self, snapshot_id: str) -> list[SkillExecution]:
        rows = await self._fetchall(
            "SELECT id, snapshot_id, status, started_at, completed_at"
            " FROM skill_executions WHERE snapshot_id=%s ORDER BY started_at DESC",
            (snapshot_id,),
        )
        return [self._row(r) for r in rows]

    @staticmethod
    def _row(row) -> SkillExecution:
        return SkillExecution(
            id=str(row[0]), snapshot_id=str(row[1]), status=row[2],
            started_at=str(row[3]),
            completed_at=str(row[4]) if row[4] else None,
        )
