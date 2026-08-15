"""SHA-256 exact-byte integrity primitives for ION PEL Phase 1.

The integrity semantic in Phase 1 is exact-byte identity only:

    SHA-256(exact supplied bytes)

No JSON canonicalization is performed or claimed here. No filesystem access.
No imports from `app` or `t4`.
"""

from __future__ import annotations

import hashlib
import re

__all__ = ["is_sha256_hex", "require_sha256_hex", "sha256_bytes"]

_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")


def sha256_bytes(data: bytes) -> str:
    """The SHA-256 hex digest of the exact bytes supplied."""
    return hashlib.sha256(data).hexdigest()


def is_sha256_hex(value: str) -> bool:
    """True only for exactly 64 lowercase hexadecimal characters."""
    return isinstance(value, str) and bool(_SHA256_HEX_RE.fullmatch(value))


def require_sha256_hex(value: str, *, field_name: str) -> str:
    """Return ``value`` unchanged if it is a valid SHA-256 hex digest.

    Raises ``ValueError`` naming ``field_name`` otherwise.
    """
    if not is_sha256_hex(value):
        raise ValueError(
            f"{field_name}: expected a lowercase 64-character hex SHA-256 digest, "
            f"got {value!r}"
        )
    return value
