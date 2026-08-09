"""Exact money — integer units with an explicit scale (§4.6, I13).

No binary floating point reaches a stored amount. A rate written ``0.20`` in the
pricing table is read as the decimal it was written as, not as the double that
approximates it, because the table's literals are decimal prices and the double is
an artefact of how Python stores them.

No rounding exists in this module. A known exact value the domain cannot hold
raises :class:`DomainViolation`, which the emitter turns into a terminal write
refusal (§4.6 rule 4, T77) — never a rounded figure and never a reclassification
to "unavailable".
"""

from __future__ import annotations

from . import jcs

__all__ = [
    "DomainViolation",
    "Rate",
    "add",
    "amount",
    "cost_of_tokens",
    "rate_from_price",
    "value_text",
]

MAX_SCALE = 9
PER_CALL_VALUE_BOUND = 1_000
AGGREGATE_VALUE_BOUND = 1_024_000
TOKENS_PER_PRICE_UNIT = 1_000_000  # the pricing table is USD per 1,000,000 tokens
_PRICE_UNIT_SCALE = 6             # 1_000_000 == 10**6


class DomainViolation(Exception):
    """An exact value the §4.9 domain cannot hold. Never rounded, never relabelled."""


class Rate:
    """A price per 1,000,000 tokens, held exactly as ``units x 10**-scale``."""

    __slots__ = ("units", "scale")

    def __init__(self, units: int, scale: int) -> None:
        self.units, self.scale = units, scale

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"Rate(units={self.units}, scale={self.scale})"


def rate_from_price(price: float) -> Rate:
    """Read a pricing-table literal as the decimal it was written as.

    The canonical ES6 text of the double is the shortest decimal that round-trips
    to it, which for a price literal is the literal: ``0.20`` stores as the double
    nearest 0.2 and prints as ``0.2``. Exponent forms are outside the pricing
    table's domain and are refused rather than guessed at.
    """
    text = jcs.to_canonical_text(float(price))
    if "e" in text or "E" in text:
        raise DomainViolation(f"price {text} is not a plain decimal")
    if text.startswith("-"):
        raise DomainViolation(f"price {text} is negative")
    integer_part, _, fraction = text.partition(".")
    return Rate(int(integer_part + fraction), len(fraction))


def amount(units: int, scale: int, *, bound: int = PER_CALL_VALUE_BOUND) -> dict:
    """A monetary amount, checked against its role's domain."""
    if scale < 0 or scale > MAX_SCALE:
        raise DomainViolation(f"scale {scale} is outside 0..{MAX_SCALE}")
    if units < 0:
        raise DomainViolation(f"units {units} is negative")
    if units > bound * 10 ** scale:
        raise DomainViolation(
            f"value {value_text(units, scale)} exceeds the role bound of {bound}"
        )
    return {"scale": scale, "units": units}


def cost_of_tokens(tokens: int, rate: Rate, *, bound: int = PER_CALL_VALUE_BOUND) -> dict:
    """``tokens x rate / 1_000_000``, exactly.

    An integer times a scale-``r`` decimal has scale at most ``r``; dividing by
    ``10**6`` adds exactly six. Both steps are exact integer operations, so the
    result is the value and not an approximation of it.
    """
    return amount(tokens * rate.units, rate.scale + _PRICE_UNIT_SCALE, bound=bound)


def add(amounts, *, bound: int = AGGREGATE_VALUE_BOUND) -> dict:
    """Exact aligned addition, in one canonical derived form (§4.6 rule 2).

    Aligns to the maximum scale by exact integer multiplication and sums. A
    numerically equal result at any other scale is a different, non-canonical form.
    """
    amounts = list(amounts)
    if not amounts:
        raise DomainViolation("no amounts to add")
    scale = max(a["scale"] for a in amounts)
    total = sum(a["units"] * 10 ** (scale - a["scale"]) for a in amounts)
    return amount(total, scale, bound=bound)


def value_text(units: int, scale: int) -> str:
    """The decimal the pair denotes. For reporting and diagnostics only."""
    if scale == 0:
        return str(units)
    digits = str(units).rjust(scale + 1, "0")
    return f"{digits[:-scale]}.{digits[-scale:]}"
