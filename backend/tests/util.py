"""Tiny stdlib test helpers (usable with or without pytest)."""

from __future__ import annotations

from contextlib import contextmanager


@contextmanager
def raises(exc_type):
    """Assert the wrapped block raises `exc_type` (or a subclass)."""
    try:
        yield
    except exc_type:
        return
    except Exception as other:  # pragma: no cover
        raise AssertionError(
            f"expected {exc_type.__name__}, got {type(other).__name__}: {other}"
        )
    raise AssertionError(f"expected {exc_type.__name__}, nothing was raised")
