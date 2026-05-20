"""
UsageService — record token usage with cost calculation.

Bridges PricingService (cost calculation) and UsageRepository (persistence).
Routes and the SSE emitter call this service to record usage after each LLM call.
"""

from __future__ import annotations

import logging

from repositories.usage_repository import UsageRepository, UsageStats
from services.pricing_service import PricingService

log = logging.getLogger(__name__)


class UsageService:
    """
    Handles all token usage recording for LLM calls.

    Computes the USD cost for each call using PricingService and persists
    the record via UsageRepository.
    """

    def __init__(self, usage_repo: UsageRepository, pricing: PricingService) -> None:
        """
        Initialise with injected repository and pricing service instances.

        Args:
            usage_repo: Repository that owns the user_token_usage table.
            pricing:    Loaded pricing service for cost calculation.
        """
        self._usage  = usage_repo
        self._pricing = pricing

    async def record(
        self,
        conversation_id: str,
        provider:        str,
        model:           str,
        input_tokens:    int,
        output_tokens:   int,
    ) -> None:
        """
        Compute the cost for a model call and persist the usage record.

        Errors during persistence are logged and swallowed — a usage recording
        failure must never surface to the user or abort an active pipeline run.

        Args:
            conversation_id: The conversation this call belongs to.
            provider:        Provider name, e.g. 'anthropic'.
            model:           Model name, e.g. 'claude-sonnet-4-6'.
            input_tokens:    Number of prompt tokens consumed.
            output_tokens:   Number of completion tokens produced.
        """
        cost = self._pricing.cost_usd(model, input_tokens, output_tokens)
        try:
            await self._usage.create(
                conversation_id = conversation_id,
                provider        = provider,
                model           = model,
                input_tokens    = input_tokens,
                output_tokens   = output_tokens,
                cost_usd        = cost,
            )
        except Exception as exc:
            log.warning(
                "Failed to record usage for conv=%s provider=%s model=%s: %s",
                conversation_id, provider, model, exc,
            )

    async def get_stats(self, conversation_id: str) -> UsageStats:
        """
        Return aggregated token usage and cost for a conversation.

        Args:
            conversation_id: The conversation to aggregate usage for.

        Returns:
            UsageStats with total tokens, total cost, and per-model breakdown.
        """
        return await self._usage.get_stats_for_conversation(conversation_id)
