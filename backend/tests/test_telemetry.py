from __future__ import annotations

from app.modules.telemetry import PricingTable


def test_known_model_cost_is_computed():
    t = PricingTable()
    # gpt-5.4-mini: 0.75/1M in, 4.50/1M out
    cost = t.estimate_cost("gpt-5.4-mini", 1_000_000, 1_000_000)
    assert abs(cost - (0.75 + 4.50)) < 1e-9


def test_unknown_model_returns_none_not_fabricated():
    assert PricingTable().estimate_cost("mystery-model", 1000, 1000) is None


def test_missing_usage_returns_none():
    assert PricingTable().estimate_cost("gpt-5.4-mini", None, 100) is None
    assert PricingTable().estimate_cost("gpt-5.4-mini", 100, None) is None


def test_pricing_is_dated():
    assert PricingTable().as_of == "2026-07-13"
