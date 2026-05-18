from __future__ import annotations
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from repositories.base import BaseRepository


@dataclass
class Execution:
    id:                    str   # = LangGraph thread_id
    conversation_skill_id: str
    status:                str   # running | complete | halted
    started_at:            str
    completed_at:          Optional[str]


@dataclass
class ExecutionStage:
    id:           str
    execution_id: str
    agent_key:    str
    provider:     Optional[str]
    model:        Optional[str]
    status:       str   # success | failed
    ran_at:       str


class ExecutionRepository(BaseRepository):

    async def create(self, conversation_skill_id: str) -> Execution:
        """Create a new execution. The id becomes the LangGraph thread_id."""
        execution_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        await self._exec(
            "INSERT INTO conversation_skill_executions"
            " (id, conversation_skill_id, status, started_at)"
            " VALUES (%s, %s, 'running', %s)",
            (execution_id, conversation_skill_id, now),
        )
        return Execution(
            id=execution_id,
            conversation_skill_id=conversation_skill_id,
            status="running",
            started_at=now,
            completed_at=None,
        )

    async def get_by_id(self, execution_id: str) -> Optional[Execution]:
        row = await self._fetchone(
            "SELECT id, conversation_skill_id, status, started_at, completed_at"
            " FROM conversation_skill_executions WHERE id = %s",
            (execution_id,),
        )
        return self._row_to_exec(row) if row else None

    async def complete(self, execution_id: str, status: str) -> None:
        """Mark execution as complete or halted."""
        now = datetime.now(timezone.utc).isoformat()
        await self._exec(
            "UPDATE conversation_skill_executions"
            " SET status = %s, completed_at = %s WHERE id = %s",
            (status, now, execution_id),
        )

    async def get_latest_for_conversation(self, conversation_id: str) -> Optional[Execution]:
        """Return the most recent execution for any skill in a conversation."""
        row = await self._fetchone(
            "SELECT cse.id, cse.conversation_skill_id, cse.status, cse.started_at, cse.completed_at"
            " FROM conversation_skill_executions cse"
            " JOIN conversation_skills cs ON cs.id = cse.conversation_skill_id"
            " WHERE cs.conversation_id = %s"
            " ORDER BY cse.started_at DESC LIMIT 1",
            (conversation_id,),
        )
        return self._row_to_exec(row) if row else None

    async def get_running(self, conversation_id: str) -> Optional[Execution]:
        """Return the running execution for any skill in a conversation, if any."""
        row = await self._fetchone(
            "SELECT cse.id, cse.conversation_skill_id, cse.status, cse.started_at, cse.completed_at"
            " FROM conversation_skill_executions cse"
            " JOIN conversation_skills cs ON cs.id = cse.conversation_skill_id"
            " WHERE cs.conversation_id = %s AND cse.status = 'running'"
            " LIMIT 1",
            (conversation_id,),
        )
        return self._row_to_exec(row) if row else None

    async def list_for_skill(self, conversation_skill_id: str) -> list[Execution]:
        rows = await self._fetchall(
            "SELECT id, conversation_skill_id, status, started_at, completed_at"
            " FROM conversation_skill_executions WHERE conversation_skill_id = %s"
            " ORDER BY started_at DESC",
            (conversation_skill_id,),
        )
        return [self._row_to_exec(r) for r in rows]

    async def record_stage(
        self,
        execution_id: str,
        agent_key:    str,
        provider:     Optional[str],
        model:        Optional[str],
        status:       str,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await self._exec(
            "INSERT INTO conversation_skill_execution_stages"
            " (execution_id, agent_key, provider, model, status, ran_at)"
            " VALUES (%s, %s, %s, %s, %s, %s)",
            (execution_id, agent_key, provider, model, status, now),
        )

    async def get_stages(self, execution_id: str) -> list[ExecutionStage]:
        rows = await self._fetchall(
            "SELECT id, execution_id, agent_key, provider, model, status, ran_at"
            " FROM conversation_skill_execution_stages WHERE execution_id = %s ORDER BY ran_at",
            (execution_id,),
        )
        return [
            ExecutionStage(
                id=str(r[0]), execution_id=str(r[1]), agent_key=r[2],
                provider=r[3], model=r[4], status=r[5], ran_at=str(r[6]),
            )
            for r in rows
        ]

    @staticmethod
    def _row_to_exec(row) -> Execution:
        return Execution(
            id=str(row[0]), conversation_skill_id=str(row[1]),
            status=row[2], started_at=str(row[3]),
            completed_at=str(row[4]) if row[4] else None,
        )
