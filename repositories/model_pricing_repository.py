from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone

from repositories.base import BaseRepository


@dataclass
class ModelPrice:
    model_id:          str
    provider:          str
    input_usd_per_1m:  float
    output_usd_per_1m: float
    updated_at:        str


class ModelPricingRepository(BaseRepository):

    async def get_all(self) -> list[ModelPrice]:
        rows = await self._fetchall(
            "SELECT model_id, provider, input_usd_per_1m, output_usd_per_1m, updated_at"
            " FROM model_pricing ORDER BY provider, model_id"
        )
        return [self._row(r) for r in rows]

    async def upsert(
        self,
        model_id:          str,
        provider:          str,
        input_usd_per_1m:  float,
        output_usd_per_1m: float,
    ) -> ModelPrice:
        now = datetime.now(timezone.utc).isoformat()
        await self._exec(
            """
            INSERT INTO model_pricing (model_id, provider, input_usd_per_1m, output_usd_per_1m, updated_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (model_id) DO UPDATE
                SET provider          = EXCLUDED.provider,
                    input_usd_per_1m  = EXCLUDED.input_usd_per_1m,
                    output_usd_per_1m = EXCLUDED.output_usd_per_1m,
                    updated_at        = EXCLUDED.updated_at
            """,
            (model_id, provider, input_usd_per_1m, output_usd_per_1m, now),
        )
        return ModelPrice(model_id, provider, input_usd_per_1m, output_usd_per_1m, now)

    @staticmethod
    def _row(r) -> ModelPrice:
        return ModelPrice(
            model_id          = r[0],
            provider          = r[1],
            input_usd_per_1m  = float(r[2]),
            output_usd_per_1m = float(r[3]),
            updated_at        = str(r[4]),
        )
