"""
Unit tests for utils/pricing.py — cost calculation.
"""

import pytest
import utils.pricing as pricing_module
from utils.pricing import cost_usd, usage_record


@pytest.fixture(autouse=True)
def seed_pricing_cache():
    """Seed the in-memory pricing cache for all tests in this module."""
    pricing_module._cache.update({
        "claude-sonnet-4-6":         {"input": 3.00,  "output": 15.00},
        "claude-haiku-4-5-20251001": {"input": 0.80,  "output":  4.00},
        "gemini-2.5-pro":            {"input": 1.25,  "output": 10.00},
        "sonar-pro":                 {"input": 3.00,  "output": 15.00},
    })
    yield
    pricing_module._cache.clear()


def test_cost_usd_sonnet():
    cost = cost_usd("claude-sonnet-4-6", input_tokens=1_000_000, output_tokens=1_000_000)
    assert cost == pytest.approx(18.0, rel=1e-3)


def test_cost_usd_zero_tokens():
    assert cost_usd("claude-sonnet-4-6", 0, 0) == 0.0


def test_cost_usd_unknown_model_returns_zero():
    assert cost_usd("unknown-model-xyz", 1_000_000, 1_000_000) == 0.0


def test_usage_record_structure():
    rec = usage_record("research", "claude-sonnet-4-6", {"input_tokens": 500, "output_tokens": 200})
    assert rec["agent"]         == "research"
    assert rec["model"]         == "claude-sonnet-4-6"
    assert rec["input_tokens"]  == 500
    assert rec["output_tokens"] == 200
    assert rec["cost_usd"]      >= 0
    assert "created_at" in rec


def test_usage_record_none_metadata():
    rec = usage_record("review", "gemini-2.5-pro", None)
    assert rec["input_tokens"]  == 0
    assert rec["output_tokens"] == 0
