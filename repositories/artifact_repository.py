from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from repositories.base import BaseRepository


@dataclass
class Artifact:
    id:              str
    conversation_id: str
    execution_id:    str
    artifact_type:   str
    content:         str
    version:         int
    status:          str
    created_at:      str


class ArtifactRepository(BaseRepository):

    async def create(
        self,
        conversation_id: str,
        execution_id:    str,
        content:         str,
        version:         int,
        status:          str,
        artifact_type:   str = "document",
    ) -> Artifact:
        now = datetime.now(timezone.utc).isoformat()
        row = await self._fetchone(
            "INSERT INTO conversation_artifacts"
            " (conversation_id, execution_id, artifact_type, content, version, status, created_at)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (conversation_id, execution_id, artifact_type, content, version, status, now),
        )
        return Artifact(
            id=str(row[0]), conversation_id=conversation_id,
            execution_id=execution_id, artifact_type=artifact_type,
            content=content, version=version, status=status, created_at=now,
        )

    async def update_status(self, artifact_id: str, status: str) -> None:
        await self._exec(
            "UPDATE conversation_artifacts SET status = %s WHERE id = %s",
            (status, artifact_id),
        )

    async def get_by_id(self, artifact_id: str) -> Optional[Artifact]:
        row = await self._fetchone(
            "SELECT id, conversation_id, execution_id, artifact_type, content, version, status, created_at"
            " FROM conversation_artifacts WHERE id = %s",
            (artifact_id,),
        )
        return self._row_to_artifact(row) if row else None

    async def get_latest(self, execution_id: str) -> Optional[Artifact]:
        row = await self._fetchone(
            "SELECT id, conversation_id, execution_id, artifact_type, content, version, status, created_at"
            " FROM conversation_artifacts WHERE execution_id = %s ORDER BY version DESC LIMIT 1",
            (execution_id,),
        )
        return self._row_to_artifact(row) if row else None

    async def list_for_execution(self, execution_id: str) -> list[Artifact]:
        rows = await self._fetchall(
            "SELECT id, conversation_id, execution_id, artifact_type, content, version, status, created_at"
            " FROM conversation_artifacts WHERE execution_id = %s ORDER BY version ASC",
            (execution_id,),
        )
        return [self._row_to_artifact(r) for r in rows]

    @staticmethod
    def _row_to_artifact(row) -> Artifact:
        return Artifact(
            id=str(row[0]), conversation_id=str(row[1]),
            execution_id=str(row[2]), artifact_type=row[3],
            content=row[4], version=row[5], status=row[6], created_at=str(row[7]),
        )
