from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from repositories.base import BaseRepository


@dataclass
class LLMModel:
    id:                       str
    name:                     str
    llm_provider_id:          Optional[str]
    input_usd_per_1m_tokens:  Decimal
    output_usd_per_1m_tokens: Decimal
    created_at:               str
    modified_at:              str


class LLMModelRepository(BaseRepository):

    async def create(
        self,
        name:                     str,
        input_usd_per_1m_tokens:  Decimal,
        output_usd_per_1m_tokens: Decimal,
    ) -> LLMModel:
        row = await self._fetchone(
            "INSERT INTO llm_models (name, input_usd_per_1m_tokens, output_usd_per_1m_tokens)"
            " VALUES (%s, %s, %s)"
            " RETURNING id, name, llm_provider_id, input_usd_per_1m_tokens, output_usd_per_1m_tokens, created_at, modified_at",
            (name, input_usd_per_1m_tokens, output_usd_per_1m_tokens),
        )
        return self._row(row)

    async def get_by_id(self, model_id: str) -> Optional[LLMModel]:
        row = await self._fetchone(
            "SELECT id, name, llm_provider_id, input_usd_per_1m_tokens, output_usd_per_1m_tokens, created_at, modified_at"
            " FROM llm_models WHERE id = %s",
            (model_id,),
        )
        return self._row(row) if row else None

    async def get_by_name(self, name: str) -> Optional[LLMModel]:
        row = await self._fetchone(
            "SELECT id, name, llm_provider_id, input_usd_per_1m_tokens, output_usd_per_1m_tokens, created_at, modified_at"
            " FROM llm_models WHERE name = %s",
            (name,),
        )
        return self._row(row) if row else None

    async def list_all(self) -> list[LLMModel]:
        rows = await self._fetchall(
            "SELECT id, name, llm_provider_id, input_usd_per_1m_tokens, output_usd_per_1m_tokens, created_at, modified_at"
            " FROM llm_models ORDER BY name"
        )
        return [self._row(r) for r in rows]

    async def update(
        self,
        model_id:                 str,
        name:                     Optional[str]    = None,
        input_usd_per_1m_tokens:  Optional[Decimal] = None,
        output_usd_per_1m_tokens: Optional[Decimal] = None,
    ) -> Optional[LLMModel]:
        sets, params = [], []
        if name is not None:
            sets.append("name = %s"); params.append(name)
        if input_usd_per_1m_tokens is not None:
            sets.append("input_usd_per_1m_tokens = %s"); params.append(input_usd_per_1m_tokens)
        if output_usd_per_1m_tokens is not None:
            sets.append("output_usd_per_1m_tokens = %s"); params.append(output_usd_per_1m_tokens)
        if not sets:
            return await self.get_by_id(model_id)
        params.append(model_id)
        row = await self._fetchone(
            f"UPDATE llm_models SET {', '.join(sets)}"
            " WHERE id = %s"
            " RETURNING id, name, input_usd_per_1m_tokens, output_usd_per_1m_tokens, created_at, modified_at",
            tuple(params),
        )
        return self._row(row) if row else None

    async def delete(self, model_id: str) -> bool:
        row = await self._fetchone(
            "DELETE FROM llm_models WHERE id = %s RETURNING id",
            (model_id,),
        )
        return row is not None

    @staticmethod
    def _row(row) -> LLMModel:
        return LLMModel(
            id=str(row[0]), name=row[1],
            llm_provider_id=str(row[2]) if row[2] else None,
            input_usd_per_1m_tokens=Decimal(row[3]),
            output_usd_per_1m_tokens=Decimal(row[4]),
            created_at=str(row[5]), modified_at=str(row[6]),
        )
