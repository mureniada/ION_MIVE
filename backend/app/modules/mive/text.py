"""Small deterministic text utilities for comparison (no external deps)."""

from __future__ import annotations

import re

_WORD = re.compile(r"[a-z0-9]+")

_STOPWORDS = frozenset(
    """a an the of to in on for and or is are was were be been being it its this that
    these those as by with from at into than then so such not no nor can cannot could
    would should may might will shall do does did has have had but if while about over
    under between money""".split()
)

_NEGATIONS = frozenset(
    "not no never without cannot cant dont doesnt isnt arent wasnt werent none neither".split()
)


def content_words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _STOPWORDS and len(w) > 2}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def negation_parity(text: str) -> int:
    """0 = even (assertive), 1 = odd number of negations (negated)."""
    toks = _WORD.findall(text.lower())
    n = sum(1 for t in toks if t in _NEGATIONS)
    return n % 2
