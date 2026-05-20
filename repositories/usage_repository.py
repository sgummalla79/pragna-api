"""
UsageRepository — CRUD for the `user_token_usage` table.

Records token consumption per model call within a conversation. Cost in USD
is pre-computed by the caller (UsageService) and stored directly — no cost
calculation logic lives in this repository.
"""

from __future__ import annotations

from dataclasses import dataclass

from repositories.base import BaseRepository


@dataclass
class UsageRecord:
    """Represents one row in the `user_token_usage` table."""
    id:              str
    conversation_id: str
    provider:        str
    model:           str
    input_tokens:    int
    output_tokens:   int
    cost_usd:        float
    created_at:      str
    modified_at:     str


@dataclass
class UsageStats:
    """Aggregated usage summary for a conversation."""
    input_tokens:  int
    output_tokens: int
    cost_usd:      float
    breakdown:     list[dict]   # [{provider, model, input_tokens, output_tokens, cost_usd}]


class UsageRepository(BaseRepository):
    """Pure CRUD repository for the `user_token_usage` table."""

    async def create(
        self,
        conversation_id: str,
        provider:        str,
        model:           str,
        input_tokens:    int,
        output_tokens:   int,
        cost_usd:        float,
    ) -> UsageRecord:
        """
        Insert a token usage record.

        The cost_usd value must be pre-computed by the caller (UsageService.record()).
        Sets created_at and modified_at to the current UTC time.
        Returns the inserted record.
        """
        now = self._now()
        row = await self._fetchone(
            "INSERT INTO user_token_usage"
            "  (conversation_id, provider, model, input_tokens, output_tokens,"
            "   cost_usd, created_at, modified_at)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
            " RETURNING id, conversation_id, provider, model, input_tokens,"
            "           output_tokens, cost_usd, created_at, modified_at",
            (conversation_id, provider, model, input_tokens, output_tokens,
             cost_usd, now, now),
        )
        return self._row(row)

    async def get_stats_for_conversation(self, conversation_id: str) -> UsageStats:
        """
        Return aggregated token usage and cost for a conversation, grouped by provider+model.

        The breakdown list is sorted by cost descending so the most expensive
        model appears first.
        """
        rows = await self._fetchall(
            "SELECT provider, model,"
            "       SUM(input_tokens), SUM(output_tokens), SUM(cost_usd)"
            " FROM user_token_usage WHERE conversation_id = %s"
            " GROUP BY provider, model ORDER BY SUM(cost_usd) DESC",
            (conversation_id,),
        )
        breakdown = [
            {
                "provider":      r[0],
                "model":         r[1],
                "input_tokens":  int(r[2]),
                "output_tokens": int(r[3]),
                "cost_usd":      round(float(r[4]), 6),
            }
            for r in rows
        ]
        return UsageStats(
            input_tokens  = sum(b["input_tokens"]  for b in breakdown),
            output_tokens = sum(b["output_tokens"] for b in breakdown),
            cost_usd      = round(sum(b["cost_usd"] for b in breakdown), 6),
            breakdown     = breakdown,
        )

    @staticmethod
    def _row(row) -> UsageRecord:
        """Map a raw DB row to a UsageRecord dataclass."""
        return UsageRecord(
            id=str(row[0]), conversation_id=str(row[1]),
            provider=row[2], model=row[3],
            input_tokens=int(row[4]), output_tokens=int(row[5]),
            cost_usd=float(row[6]),
            created_at=str(row[7]), modified_at=str(row[8]),
        )
