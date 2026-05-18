from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from repositories.base import BaseRepository


@dataclass
class LLMProvider:
    id:          str
    name:        str
    created_at:  str
    modified_at: str


class LLMProviderRepository(BaseRepository):

    async def create(self, name: str) -> LLMProvider:
        row = await self._fetchone(
            "INSERT INTO llm_providers (name)"
            " VALUES (%s)"
            " RETURNING id, name, created_at, modified_at",
            (name,),
        )
        return self._row(row)

    async def get_by_id(self, provider_id: str) -> Optional[LLMProvider]:
        row = await self._fetchone(
            "SELECT id, name, created_at, modified_at"
            " FROM llm_providers WHERE id = %s",
            (provider_id,),
        )
        return self._row(row) if row else None

    async def get_by_name(self, name: str) -> Optional[LLMProvider]:
        row = await self._fetchone(
            "SELECT id, name, created_at, modified_at"
            " FROM llm_providers WHERE name = %s",
            (name,),
        )
        return self._row(row) if row else None

    async def list_all(self) -> list[LLMProvider]:
        rows = await self._fetchall(
            "SELECT id, name, created_at, modified_at"
            " FROM llm_providers ORDER BY name"
        )
        return [self._row(r) for r in rows]

    async def update(self, provider_id: str, name: str) -> Optional[LLMProvider]:
        row = await self._fetchone(
            "UPDATE llm_providers SET name = %s"
            " WHERE id = %s"
            " RETURNING id, name, created_at, modified_at",
            (name, provider_id),
        )
        return self._row(row) if row else None

    async def delete(self, provider_id: str) -> bool:
        row = await self._fetchone(
            "DELETE FROM llm_providers WHERE id = %s RETURNING id",
            (provider_id,),
        )
        return row is not None

    @staticmethod
    def _row(row) -> LLMProvider:
        return LLMProvider(
            id=str(row[0]), name=row[1],
            created_at=str(row[2]), modified_at=str(row[3]),
        )
