from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone

from repositories.base import BaseRepository
from utils.pricing import cost_usd


@dataclass
class UsageStats:
    input_tokens:  int
    output_tokens: int
    cost_usd:      float
    breakdown:     list[dict]   # [{provider, model, input, output, cost}]


class UsageRepository(BaseRepository):

    async def record(
        self,
        conversation_id: str,
        provider:        str,
        model:           str,
        input_tokens:    int,
        output_tokens:   int,
    ) -> None:
        now   = datetime.now(timezone.utc).isoformat()
        cost  = cost_usd(model, input_tokens, output_tokens)
        await self._exec(
            "INSERT INTO token_usage"
            " (conversation_id, provider, model, input_tokens, output_tokens, cost_usd, created_at)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (conversation_id, provider, model, input_tokens, output_tokens, cost, now),
        )

    async def get_by_conversation(self, conversation_id: str) -> UsageStats:
        rows = await self._fetchall(
            "SELECT provider, model, SUM(input_tokens), SUM(output_tokens), SUM(cost_usd)"
            " FROM token_usage WHERE conversation_id = %s"
            " GROUP BY provider, model ORDER BY SUM(cost_usd) DESC",
            (conversation_id,),
        )
        breakdown = [
            {
                "provider":      r[0],
                "model":         r[1],
                "input_tokens":  r[2],
                "output_tokens": r[3],
                "cost_usd":      round(r[4], 6),
            }
            for r in rows
        ]
        return UsageStats(
            input_tokens  = sum(r["input_tokens"]  for r in breakdown),
            output_tokens = sum(r["output_tokens"] for r in breakdown),
            cost_usd      = round(sum(r["cost_usd"] for r in breakdown), 6),
            breakdown     = breakdown,
        )
