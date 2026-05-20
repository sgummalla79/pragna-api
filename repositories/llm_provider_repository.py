"""
LLMProviderRepository — CRUD for the `llm_providers` table.

Stores the global catalog of supported LLM providers (e.g. anthropic, openai).
Seeded at application startup from configuration; never user-specific.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from repositories.base import BaseRepository


@dataclass
class LLMProvider:
    """Represents one row in the `llm_providers` table."""
    id:          str
    name:        str   # machine identifier, e.g. "anthropic", "openai"
    created_at:  str
    modified_at: str


class LLMProviderRepository(BaseRepository):
    """Pure CRUD repository for the `llm_providers` table."""

    async def upsert(self, name: str) -> LLMProvider:
        """
        Insert a provider by name or return the existing row if name already exists.

        Sets created_at on first insert; updates modified_at on conflict.
        Returns the current provider row.
        """
        now = self._now()
        row = await self._fetchone(
            "INSERT INTO llm_providers (name, created_at, modified_at)"
            " VALUES (%s, %s, %s)"
            " ON CONFLICT (name) DO UPDATE SET modified_at = EXCLUDED.modified_at"
            " RETURNING id, name, created_at, modified_at",
            (name, now, now),
        )
        return self._row(row)

    async def get_by_id(self, provider_id: str) -> Optional[LLMProvider]:
        """Return the provider with the given UUID, or None."""
        row = await self._fetchone(
            "SELECT id, name, created_at, modified_at"
            " FROM llm_providers WHERE id = %s",
            (provider_id,),
        )
        return self._row(row) if row else None

    async def get_by_name(self, name: str) -> Optional[LLMProvider]:
        """Return the provider with the given machine name (e.g. 'openai'), or None."""
        row = await self._fetchone(
            "SELECT id, name, created_at, modified_at"
            " FROM llm_providers WHERE name = %s",
            (name,),
        )
        return self._row(row) if row else None

    async def list_all(self) -> list[LLMProvider]:
        """Return all providers ordered by name."""
        rows = await self._fetchall(
            "SELECT id, name, created_at, modified_at"
            " FROM llm_providers ORDER BY name"
        )
        return [self._row(r) for r in rows]

    async def delete(self, provider_id: str) -> bool:
        """
        Delete the provider with the given UUID.

        Returns True if a row was deleted, False if no matching row was found.
        Cascades to llm_models and user_llm_providers via FK constraints.
        """
        row = await self._fetchone(
            "DELETE FROM llm_providers WHERE id = %s RETURNING id",
            (provider_id,),
        )
        return row is not None

    @staticmethod
    def _row(row) -> LLMProvider:
        """Map a raw DB row to an LLMProvider dataclass."""
        return LLMProvider(
            id=str(row[0]), name=row[1],
            created_at=str(row[2]), modified_at=str(row[3]),
        )
