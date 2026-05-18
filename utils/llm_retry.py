"""
LLM call retry wrapper using tenacity.

All three providers (Claude, Perplexity, Gemini) share the same retry policy:
  - Retry on rate limits (429), 500/503 errors, timeouts, and transient network errors
  - Exponential backoff: 2s → 4s → 8s → 16s → 32s (max 5 attempts)
  - Raises the original exception after all retries are exhausted

Usage:
    from utils.llm_retry import invoke_with_retry
    result = invoke_with_retry(llm, messages)
"""

import logging
from typing import Any

from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

logger = logging.getLogger(__name__)


def _is_retryable(exc: BaseException) -> bool:
    """Return True for transient errors worth retrying."""
    msg = str(exc).lower()
    retryable_signals = [
        "rate limit",
        "429",
        "500",
        "503",
        "timeout",
        "connection",
        "overloaded",
        "temporarily unavailable",
        "resource exhausted",
        "internal server error",
        "api_error",
    ]
    return any(signal in msg for signal in retryable_signals)


@retry(
    retry=retry_if_exception(_is_retryable),
    wait=wait_exponential(multiplier=1, min=2, max=32),
    stop=stop_after_attempt(5),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def invoke_with_retry(llm: Any, messages: list) -> Any:
    """Invoke an LLM with automatic retry on transient failures."""
    return llm.invoke(messages)
