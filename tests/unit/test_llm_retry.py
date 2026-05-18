"""
Unit tests for utils/llm_retry.py — tenacity retry wrapper.
"""

import pytest
from unittest.mock import MagicMock, call


def test_succeeds_on_first_call():
    from utils.llm_retry import invoke_with_retry
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content="Response")
    result = invoke_with_retry(llm, ["msg"])
    assert llm.invoke.call_count == 1


def test_retries_on_rate_limit():
    from utils.llm_retry import invoke_with_retry
    llm      = MagicMock()
    good_resp = MagicMock(content="OK")
    llm.invoke.side_effect = [
        RuntimeError("rate limit exceeded"),
        RuntimeError("rate limit exceeded"),
        good_resp,
    ]
    result = invoke_with_retry(llm, ["msg"])
    assert llm.invoke.call_count == 3
    assert result is good_resp


def test_retries_on_429():
    from utils.llm_retry import invoke_with_retry
    llm = MagicMock()
    llm.invoke.side_effect = [
        Exception("429 Too Many Requests"),
        MagicMock(content="Delayed response"),
    ]
    result = invoke_with_retry(llm, ["msg"])
    assert llm.invoke.call_count == 2


def test_does_not_retry_on_non_retryable_error():
    from utils.llm_retry import invoke_with_retry
    llm = MagicMock()
    llm.invoke.side_effect = ValueError("Invalid parameter — not retryable")
    with pytest.raises(ValueError, match="Invalid parameter"):
        invoke_with_retry(llm, ["msg"])
    assert llm.invoke.call_count == 1


def test_is_retryable_signals():
    from utils.llm_retry import _is_retryable
    assert _is_retryable(Exception("rate limit"))          is True
    assert _is_retryable(Exception("429"))                 is True
    assert _is_retryable(Exception("500"))                 is True
    assert _is_retryable(Exception("503"))                 is True
    assert _is_retryable(Exception("timeout"))             is True
    assert _is_retryable(Exception("connection refused"))  is True
    assert _is_retryable(Exception("overloaded"))          is True
    assert _is_retryable(Exception("resource exhausted"))  is True
    assert _is_retryable(Exception("api_error"))           is True
    assert _is_retryable(ValueError("bad input"))          is False
    assert _is_retryable(Exception("authentication"))      is False
