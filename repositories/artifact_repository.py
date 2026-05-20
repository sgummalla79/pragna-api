"""
ArtifactRepository — CRUD for the `conversation_artifacts` table.

Stores versioned artifacts (documents) produced during skill pipeline runs.
Each artifact belongs to one execution and has a monotonically increasing
version number within that execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from repositories.base import BaseRepository
from repositories.constants import ArtifactStatus, ArtifactType


@dataclass
class Artifact:
    """Represents one row in the `conversation_artifacts` table."""
    id:              str
    conversation_id: str
    execution_id:    Optional[str]   # nullable for pre-migration legacy rows
    artifact_type:   str             # ArtifactType constant
    content:         str
    version:         int
    status:          str   # ArtifactStatus constant
    created_at:      str
    modified_at:     str


class ArtifactRepository(BaseRepository):
    """Pure CRUD repository for the `conversation_artifacts` table."""

    async def create(
        self,
        conversation_id: str,
        execution_id:    str,
        content:         str,
        version:         int,
        status:          str,
        artifact_type:   str = ArtifactType.DOCUMENT,
    ) -> Artifact:
        """
        Insert a new artifact row.

        Sets created_at and modified_at to the current UTC time.
        Returns the inserted artifact as a typed dataclass.
        """
        now = self._now()
        row = await self._fetchone(
            "INSERT INTO conversation_artifacts"
            "  (conversation_id, execution_id, artifact_type, content,"
            "   version, status, created_at, modified_at)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
            " RETURNING id, conversation_id, execution_id, artifact_type,"
            "           content, version, status, created_at, modified_at",
            (conversation_id, execution_id, artifact_type, content,
             version, status, now, now),
        )
        return self._row(row)

    async def get_by_id(self, artifact_id: str) -> Optional[Artifact]:
        """Return the artifact with the given UUID, or None."""
        row = await self._fetchone(
            "SELECT id, conversation_id, execution_id, artifact_type,"
            "       content, version, status, created_at, modified_at"
            " FROM conversation_artifacts WHERE id = %s",
            (artifact_id,),
        )
        return self._row(row) if row else None

    async def get_latest_for_execution(self, execution_id: str) -> Optional[Artifact]:
        """
        Return the highest-version artifact for an execution, or None.

        Used after review/approval stages to get the most recent document
        and update its status.
        """
        row = await self._fetchone(
            "SELECT id, conversation_id, execution_id, artifact_type,"
            "       content, version, status, created_at, modified_at"
            " FROM conversation_artifacts"
            " WHERE execution_id = %s"
            " ORDER BY version DESC LIMIT 1",
            (execution_id,),
        )
        return self._row(row) if row else None

    async def list_for_execution(self, execution_id: str) -> list[Artifact]:
        """
        Return all artifacts for an execution in version order (oldest first).

        Useful for displaying the full revision history of a document.
        """
        rows = await self._fetchall(
            "SELECT id, conversation_id, execution_id, artifact_type,"
            "       content, version, status, created_at, modified_at"
            " FROM conversation_artifacts"
            " WHERE execution_id = %s ORDER BY version ASC",
            (execution_id,),
        )
        return [self._row(r) for r in rows]

    async def update_status(self, artifact_id: str, status: str) -> None:
        """
        Update the review/approval status for an artifact and set modified_at.

        Status values are defined in ArtifactStatus constants.
        """
        await self._exec(
            "UPDATE conversation_artifacts SET status = %s, modified_at = %s WHERE id = %s",
            (status, self._now(), artifact_id),
        )

    @staticmethod
    def _row(row) -> Artifact:
        """Map a raw DB row to an Artifact dataclass."""
        return Artifact(
            id=str(row[0]), conversation_id=str(row[1]),
            execution_id=str(row[2]) if row[2] else None, artifact_type=row[3],
            content=row[4], version=int(row[5]), status=row[6],
            created_at=str(row[7]), modified_at=str(row[8]),
        )
