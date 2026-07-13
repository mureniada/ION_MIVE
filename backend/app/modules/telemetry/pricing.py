"""Pricing table (PricingPort) — isolated from runtime logic and dated (docs/08).

Unknown model pricing returns None (never a fabricated estimate). Prices are
USD per 1,000,000 tokens, captured 2026-07-13 from official provider pages
(standard tier, text, short context). Re-verify at live-prep.
"""

from __future__ import annotations

PRICING_AS_OF = "2026-07-13"

# model -> (input_per_1M, output_per_1M) in USD
_PRICES: dict[str, tuple[float, float]] = {
    # OpenAI (standard tier)
    "gpt-5.4-nano": (0.20, 1.25),
    "gpt-5.4-mini": (0.75, 4.50),
    "gpt-5.4": (2.50, 15.00),
    "gpt-5.5": (5.00, 30.00),
    # Gemini
    "gemini-3.1-flash-lite": (0.25, 1.50),
    "gemini-3.5-flash": (1.50, 9.00),
    "gemini-3.1-pro": (2.00, 12.00),
}


class PricingTable:
    def __init__(self, prices: dict[str, tuple[float, float]] | None = None) -> None:
        self._prices = dict(prices) if prices is not None else dict(_PRICES)
        self.as_of = PRICING_AS_OF

    def estimate_cost(
        self, model: str, input_tokens: int | None, output_tokens: int | None
    ) -> float | None:
        rates = self._prices.get(model)
        if rates is None or input_tokens is None or output_tokens is None:
            return None  # never fabricate
        in_rate, out_rate = rates
        cost = (input_tokens / 1_000_000) * in_rate + (output_tokens / 1_000_000) * out_rate
        return round(cost, 8)
