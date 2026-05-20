"""
LLMModelRepository — CRUD for the `llm_models` table.

Global catalog of LLM models with pricing. Each model belongs to one provider.
Seeded at startup from provider APIs; never user-specific.

Pricing fields (input_usd_per_1m_tokens, output_usd_per_1m_tokens) replace the
former model_pricing table — all pricing data lives here.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from repositories.base import BaseRepository


@dataclass
class LLMModel:
    """Represents one row in the `llm_models` table."""
    id:                       str
    name:                     str   # model identifier, e.g. "claude-sonnet-4-6"
    llm_provider_id:          str   # UUID FK → llm_providers(id)
    input_usd_per_1m_tokens:  Decimal
    output_usd_per_1m_tokens: Decimal
    created_at:               str
    modified_at:              str


class LLMModelRepository(BaseRepository):
    """Pure CRUD repository for the `llm_models` table."""

    async def upsert(
        self,
        name:                     str,
        llm_provider_id:          str,
        input_usd_per_1m_tokens:  Decimal = Decimal("0"),
        output_usd_per_1m_tokens: Decimal = Decimal("0"),
    ) -> LLMModel:
        """
        Insert a model or update its pricing if one with the same name already exists.

        Sets created_at on first insert; updates pricing fields and modified_at on conflict.
        Returns the current model row.
        """
        now = self._now()
        row = await self._fetchone(
            "INSERT INTO llm_models"
            "  (name, llm_provider_id, input_usd_per_1m_tokens, output_usd_per_1m_tokens,"
            "   created_at, modified_at)"
            " VALUES (%s, %s, %s, %s, %s, %s)"
            " ON CONFLICT (name) DO UPDATE SET"
            "   llm_provider_id          = EXCLUDED.llm_provider_id,"
            "   input_usd_per_1m_tokens  = EXCLUDED.input_usd_per_1m_tokens,"
            "   output_usd_per_1m_tokens = EXCLUDED.output_usd_per_1m_tokens,"
            "   modified_at              = EXCLUDED.modified_at"
            " RETURNING id, name, llm_provider_id, input_usd_per_1m_tokens,"
            "           output_usd_per_1m_tokens, created_at, modified_at",
            (name, llm_provider_id, input_usd_per_1m_tokens, output_usd_per_1m_tokens, now, now),
        )
        return self._row(row)

    async def get_by_id(self, model_id: str) -> Optional[LLMModel]:
        """Return the model with the given UUID, or None."""
        row = await self._fetchone(
            "SELECT id, name, llm_provider_id, input_usd_per_1m_tokens,"
            "       output_usd_per_1m_tokens, created_at, modified_at"
            " FROM llm_models WHERE id = %s",
            (model_id,),
        )
        return self._row(row) if row else None

    async def get_by_name(self, name: str) -> Optional[LLMModel]:
        """Return the model with the given name identifier, or None."""
        row = await self._fetchone(
            "SELECT id, name, llm_provider_id, input_usd_per_1m_tokens,"
            "       output_usd_per_1m_tokens, created_at, modified_at"
            " FROM llm_models WHERE name = %s",
            (name,),
        )
        return self._row(row) if row else None

    async def list_all(self) -> list[LLMModel]:
        """Return all models ordered by name."""
        rows = await self._fetchall(
            "SELECT id, name, llm_provider_id, input_usd_per_1m_tokens,"
            "       output_usd_per_1m_tokens, created_at, modified_at"
            " FROM llm_models ORDER BY name"
        )
        return [self._row(r) for r in rows]

    async def list_for_provider(self, llm_provider_id: str) -> list[LLMModel]:
        """Return all models belonging to a specific provider UUID."""
        rows = await self._fetchall(
            "SELECT id, name, llm_provider_id, input_usd_per_1m_tokens,"
            "       output_usd_per_1m_tokens, created_at, modified_at"
            " FROM llm_models WHERE llm_provider_id = %s ORDER BY name",
            (llm_provider_id,),
        )
        return [self._row(r) for r in rows]

    async def update_pricing(
        self,
        model_id:                 str,
        input_usd_per_1m_tokens:  Decimal,
        output_usd_per_1m_tokens: Decimal,
    ) -> None:
        """
        Update the pricing fields for a model and set modified_at.

        Used when re-fetching pricing from provider APIs without changing the model name.
        """
        await self._exec(
            "UPDATE llm_models"
            " SET input_usd_per_1m_tokens = %s,"
            "     output_usd_per_1m_tokens = %s,"
            "     modified_at = %s"
            " WHERE id = %s",
            (input_usd_per_1m_tokens, output_usd_per_1m_tokens, self._now(), model_id),
        )

    async def delete(self, model_id: str) -> bool:
        """
        Delete the model with the given UUID.

        Returns True if a row was deleted, False if not found.
        Cascades to user_llm_models via FK constraint.
        """
        row = await self._fetchone(
            "DELETE FROM llm_models WHERE id = %s RETURNING id",
            (model_id,),
        )
        return row is not None

    @staticmethod
    def _row(row) -> LLMModel:
        """Map a raw DB row to an LLMModel dataclass."""
        return LLMModel(
            id=str(row[0]), name=row[1],
            llm_provider_id=str(row[2]),
            input_usd_per_1m_tokens=Decimal(str(row[3])),
            output_usd_per_1m_tokens=Decimal(str(row[4])),
            created_at=str(row[5]),
            modified_at=str(row[6]),
        )
