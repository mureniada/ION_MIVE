"""Content Engine (v0.1) — public package surface.

Transforms a closed canonical Content Pack, plus a runtime `source_root` and a
binding of each declared `source_id` to a relative POSIX path beneath it, into a
verified, provenance-carrying derived record set — and stops there.

    BUILD  !=  VERIFY  !=  ACTIVATE

    SOURCE ORIGIN != SOURCE IDENTITY
    SOURCE ROOT   != CONTENT PACK IDENTITY

This package must never embed, call a provider, write to Qdrant, mint an index
identity, record an activation, or read a clock. It must never modify the
Content Pack it is given, never treat a filesystem path as identity, and never
let an absolute machine path reach a record, a fingerprint or a provenance
origin. Pack-to-derived-index identity belongs to E2.3; verify / activate /
rollback belong to E3.

See `resolver.py` for the declared-source resolution and raw-byte verification
gate, `engine.py` for the build flow, and `models.py` for the contract objects.
"""

from __future__ import annotations

from .engine import (
    DEFAULT_CHUNK_CHARS,
    DEFAULT_OVERLAP,
    build_content,
    source_origin_for,
)
from .models import (
    CONTENT_ENGINE_CONTRACT_ID,
    CONTENT_ENGINE_CONTRACT_VERSION,
    CONTENT_ENGINE_VERSION,
    PROHIBITED_IDENTITY_FIELDS,
    RECORD_KEYS,
    SUPPORTED_CONTRACT_VERSIONS,
    ContentBuildResult,
    ContentEngineError,
    VerifiedSource,
)
from .resolver import (
    measure_source_bytes,
    normalize_relative_source_path,
    resolve_and_verify,
)

__all__ = [
    "CONTENT_ENGINE_CONTRACT_ID",
    "CONTENT_ENGINE_CONTRACT_VERSION",
    "CONTENT_ENGINE_VERSION",
    "ContentBuildResult",
    "ContentEngineError",
    "DEFAULT_CHUNK_CHARS",
    "DEFAULT_OVERLAP",
    "PROHIBITED_IDENTITY_FIELDS",
    "RECORD_KEYS",
    "SUPPORTED_CONTRACT_VERSIONS",
    "VerifiedSource",
    "build_content",
    "measure_source_bytes",
    "normalize_relative_source_path",
    "resolve_and_verify",
    "source_origin_for",
]
