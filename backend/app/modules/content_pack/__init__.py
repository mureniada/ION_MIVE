"""Canonical generic Content Pack identity (v0.1) — public package surface.

Pure declared-content identity only. See `models.py` for the contract and
`identity.py` for the canonical byte rule and fingerprint.

This package accepts an explicit, validated source inventory and measures its
identity. It must never scan a directory, read the local material registry,
open a source file, invoke ingestion, or import retrieval, Qdrant, evidence
provenance, the Context Pack, Core, the container, Settings, the Model Gateway,
Session or the Turn Record. A Content Pack is identifiable with none of them in
existence, and that independence is the point of the object.
"""

from __future__ import annotations

from .identity import (
    CANONICALIZATION_IMPLEMENTATION,
    CANONICALIZATION_PROFILE,
    CANONICALIZATION_PROFILE_ID,
    FINGERPRINT_ALGORITHM,
    PAYLOAD_KEYS,
    SOURCE_ENTRY_KEYS,
    ContentPackIdentityError,
    canonical_bytes,
    canonical_payload,
    canonical_source_order,
    compute_canonical_fingerprint,
)
from .models import (
    CONTENT_PACK_CONTRACT_ID,
    CONTENT_PACK_CONTRACT_VERSION,
    SOURCE_ID_PATTERN,
    SOURCE_SHA256_ALGORITHM,
    SOURCE_SHA256_BASIS,
    SUPPORTED_CONTRACT_VERSIONS,
    UNGOVERNED_SOURCE_ID,
    ContentPack,
    ContentPackError,
    SourceEntry,
)

__all__ = [
    "CANONICALIZATION_IMPLEMENTATION",
    "CANONICALIZATION_PROFILE",
    "CANONICALIZATION_PROFILE_ID",
    "CONTENT_PACK_CONTRACT_ID",
    "CONTENT_PACK_CONTRACT_VERSION",
    "ContentPack",
    "ContentPackError",
    "ContentPackIdentityError",
    "FINGERPRINT_ALGORITHM",
    "PAYLOAD_KEYS",
    "SOURCE_ENTRY_KEYS",
    "SOURCE_ID_PATTERN",
    "SOURCE_SHA256_ALGORITHM",
    "SOURCE_SHA256_BASIS",
    "SUPPORTED_CONTRACT_VERSIONS",
    "SourceEntry",
    "UNGOVERNED_SOURCE_ID",
    "canonical_bytes",
    "canonical_payload",
    "canonical_source_order",
    "compute_canonical_fingerprint",
]
