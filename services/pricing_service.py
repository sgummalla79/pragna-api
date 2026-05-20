"""
PricingService — LLM cost calculation from the llm_models catalog.

Replaces the former utils/pricing.py. Pricing data is loaded once at application
startup from the llm_models table (input_usd_per_1m_tokens / output_usd_per_1m_tokens)
and cached in memory for the lifetime of the process.

Updating prices requires a restart or an explicit reload — prices are not
expected to change during a running session.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


class PricingService:
    """
    Manages an in-memory pricing cache loaded from the llm_models catalog.

    The cache maps model name (e.g. 'claude-sonnet-4-6') to its input and
    output costs per 1M tokens. All cost calculations use this cache.
    """

    def __init__(self) -> None:
        """Initialise with an empty cache. Call load_cache() before use."""
        # {model_name: {"input": float, "output": float}}
        self._cache: dict[str, dict[str, float]] = {}

    async def load_cache(self, llm_model_repo) -> None:
        """
        Load pricing for all models from the llm_models catalog into memory.

        Should be called once during application startup after the DB connection
        is established. Clears any previously loaded data before reloading.

        Args:
            llm_model_repo: An instance of LLMModelRepository.
        """
        models = await llm_model_repo.list_all()
        self._cache.clear()
        for m in models:
            self._cache[m.name] = {
                "input":  float(m.input_usd_per_1m_tokens),
                "output": float(m.output_usd_per_1m_tokens),
            }
        log.info("Pricing cache loaded — %d models", len(self._cache))

    def cost_usd(self, model_name: str, input_tokens: int, output_tokens: int) -> float:
        """
        Calculate the cost in USD for a model call using cached pricing.

        Returns 0.0 if the model name is not in the cache — callers should not
        treat a zero-cost result as a pricing error; some models may genuinely
        be free or may not yet be priced in the catalog.

        Args:
            model_name:    The model identifier, e.g. 'claude-sonnet-4-6'.
            input_tokens:  Number of input (prompt) tokens consumed.
            output_tokens: Number of output (completion) tokens produced.

        Returns:
            Cost in USD rounded to 6 decimal places.
        """
        pricing = self._cache.get(model_name, {"input": 0.0, "output": 0.0})
        raw = (
            input_tokens  * pricing["input"] +
            output_tokens * pricing["output"]
        ) / 1_000_000
        return round(raw, 6)

    def get_all_pricing(self) -> dict[str, dict[str, float]]:
        """
        Return a copy of the full pricing cache.

        Useful for exposing pricing data via an admin or debugging endpoint.
        """
        return dict(self._cache)
