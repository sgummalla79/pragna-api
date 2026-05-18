"""
LLM pricing — costs are loaded from the model_pricing DB table at startup.
Call load_pricing_cache(db) once during app lifespan before any cost calculations.
Update prices via the API without redeploying.
"""

import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)

# In-memory cache: {model_id: {"input": float, "output": float}}
# Populated at startup from DB — sync-safe for LangGraph threads.
_cache: dict[str, dict[str, float]] = {}


async def load_pricing_cache(db) -> None:
    """Load all model prices from DB into memory. Called once at app startup."""
    rows = await db.model_pricing.get_all()
    _cache.clear()
    for row in rows:
        _cache[row.model_id] = {
            "input":  row.input_usd_per_1m,
            "output": row.output_usd_per_1m,
        }
    log.info("Pricing cache loaded — %d models", len(_cache))


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """Compute cost in USD from cached pricing. Returns 0.0 if model not in cache."""
    p = _cache.get(model, {"input": 0.0, "output": 0.0})
    return round((input_tokens * p["input"] + output_tokens * p["output"]) / 1_000_000, 6)


def usage_record(agent: str, model: str, metadata: dict | None) -> dict:
    """Build a usage record dict from LangChain usage_metadata."""
    m   = metadata or {}
    inp = m.get("input_tokens", 0)
    out = m.get("output_tokens", 0)
    return {
        "agent":         agent,
        "model":         model,
        "input_tokens":  inp,
        "output_tokens": out,
        "cost_usd":      cost_usd(model, inp, out),
        "created_at":    datetime.now(timezone.utc).isoformat(),
    }
