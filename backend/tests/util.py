"""Tiny stdlib test helpers (usable with or without pytest)."""

from __future__ import annotations

import os
from contextlib import contextmanager

# A fixed, non-secret token for transport tests (Render pilot auth gate).
PILOT_TEST_TOKEN = "pilot-test-token-not-a-secret-0123456789"


def pilot_auth_headers() -> dict[str, str]:
    """Configure `ION_PILOT_API_TOKEN` for this process and return the matching
    `Authorization` header, so transport tests reach the code they exercise."""
    os.environ["ION_PILOT_API_TOKEN"] = PILOT_TEST_TOKEN
    return {"Authorization": f"Bearer {PILOT_TEST_TOKEN}"}


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
