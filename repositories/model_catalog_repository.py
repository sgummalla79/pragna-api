from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone

from repositories.base import BaseRepository


@dataclass
class CatalogModel:
    provider:     str
    model_id:     str
    display_name: str


class ModelCatalogRepository(BaseRepository):

    async def get_by_provider(self, provider: str) -> list[CatalogModel]:
        rows = await self._fetchall(
            "SELECT provider, model_id, display_name FROM provider_catalog"
            " WHERE provider = %s ORDER BY model_id",
            (provider,),
        )
        return [CatalogModel(r[0], r[1], r[2]) for r in rows]

    async def upsert(self, provider: str, model_id: str, display_name: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await self._exec(
            """
            INSERT INTO provider_catalog (provider, model_id, display_name, updated_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (provider, model_id) DO UPDATE
                SET display_name = EXCLUDED.display_name,
                    updated_at   = EXCLUDED.updated_at
            """,
            (provider, model_id, display_name, now),
        )

    async def delete(self, provider: str, model_id: str) -> None:
        await self._exec(
            "DELETE FROM provider_catalog WHERE provider = %s AND model_id = %s",
            (provider, model_id),
        )
