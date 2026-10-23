"""Fail-closed bearer-token gate for the Render pilot (`ION_PILOT_API_TOKEN`).

No web framework is imported here, so this module stays unit-testable exactly
like `service.py`. It reads the expected token from the environment per call
(a rotated token takes effect without a rebuild) and returns None when the
request may proceed, else a (status_code, error_body) tuple.

Fail closed: an unset, empty, or too-short `ION_PILOT_API_TOKEN` refuses every
gated request (503); it never lets a request through. Comparison is constant
time over fixed-length digests, so neither content nor length is timed. Neither
the expected nor the presented token ever appears in a payload or a log line.
"""

from __future__ import annotations

import hashlib
import hmac
import os

TOKEN_ENV = "ION_PILOT_API_TOKEN"

# A short shared secret is a configuration error, not a weaker mode: 32
# characters is the floor (`openssl rand -hex 32` yields 64).
MIN_TOKEN_LENGTH = 32


def _digest(value: str) -> bytes:
    return hashlib.sha256(value.encode("utf-8")).digest()


def check_bearer(authorization: str | None, env: dict[str, str] | None = None):
    """Return None if `authorization` carries the configured token, else a
    (status_code, error_body) tuple. Messages are fixed text only."""
    e = env if env is not None else os.environ
    expected = (e.get(TOKEN_ENV) or "").strip()
    if len(expected) < MIN_TOKEN_LENGTH:
        return (503, {
            "status": "error",
            "error_stage": "not_ready",
            "message": "API authentication is not configured; requests are refused.",
        })

    scheme, _, presented = (authorization or "").strip().partition(" ")
    presented = presented.strip()
    if scheme.lower() != "bearer" or not presented:
        return _unauthorized()
    if not hmac.compare_digest(_digest(presented), _digest(expected)):
        return _unauthorized()
    return None


def _unauthorized():
    return (401, {
        "status": "error",
        "error_stage": "unauthorized",
        "message": "A valid bearer token is required.",
    })
